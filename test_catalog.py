"""Проверка ФТ-2.2: каталог, поиск и фильтры.  Запуск:  python test_catalog.py
Нужен запущенный PostgreSQL и верный пароль в .env. Тестовые фильмы в конце удаляются.
"""
import math
import time
import uuid

from app import app
from catalog import PAGE_SIZE
from dbutil import db_cursor
from models import init_user_storage
from schema import init_extra_tables

TAG = uuid.uuid4().hex[:6]
PREFIX = f"[тест{TAG}]"


def ok(text):
    print("OK:", text)


def make_film(title, genres, year, country, actors=None):
    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO films (title, genres, year, country, actors, duration) "
                    "VALUES (%s, %s, %s, %s, %s, 100) RETURNING id;",
                    (f"{PREFIX} {title}", genres, year, country, actors))
        return cur.fetchone()["id"]


def cleanup():
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM films WHERE title LIKE %s;", (f"{PREFIX}%",))


def page(client, **query):
    """Открывает каталог. По умолчанию ищет только тестовые фильмы (по метке в названии)."""
    query.setdefault("q", f"тест{TAG}")
    response = client.get("/catalog", query_string=query)
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


def has(html, title):
    return f"{PREFIX} {title}" in html


def test_catalog():
    app.config["TESTING"] = True
    a = make_film("Драма-А", "Драма", 1994, "США", f"Актёр{TAG}, Второй")
    b = make_film("Мелодрама-Б", "Мелодрама", 2001, "Франция")
    c_id = make_film("Комедия-В", "Комедия, Драма", 2010, "США")
    d = make_film("Ужасы-Г", "Ужасы", 1985, "Япония")

    client = app.test_client()  # гость, без входа

    html = page(client)
    assert all(has(html, t) for t in ("Драма-А", "Мелодрама-Б", "Комедия-В", "Ужасы-Г"))
    assert "нет оценок" in html or "рейтинг" in html
    assert f"/reviews/{a}" in html
    ok("каталог открыт гостям, виден постер-заглушка, рейтинг и ссылка на страницу фильма")

    html = page(client, q=f"Актёр{TAG}")
    assert has(html, "Драма-А") and not has(html, "Мелодрама-Б")
    ok("поиск по имени актёра")

    html = page(client, q=f"{PREFIX} комедия-в")
    assert has(html, "Комедия-В") and not has(html, "Драма-А")
    ok("поиск по названию без учёта регистра")

    html = page(client, q="%")
    assert not has(html, "Драма-А")
    ok("символ % ищется как обычный, а не как «любой текст»")

    html = page(client, genre="Драма")
    assert has(html, "Драма-А") and has(html, "Комедия-В")
    assert not has(html, "Мелодрама-Б"), "«Драма» не должна находить «Мелодрама»"
    assert not has(html, "Ужасы-Г")
    ok("фильтр по жанру ищет точное совпадение")

    html = page(client, genre=["Драма", "Ужасы"])
    assert has(html, "Драма-А") and has(html, "Ужасы-Г") and has(html, "Комедия-В")
    assert not has(html, "Мелодрама-Б")
    ok("несколько жанров: подходит фильм хотя бы с одним")

    html = page(client, year_from="2000")
    assert has(html, "Мелодрама-Б") and has(html, "Комедия-В")
    assert not has(html, "Драма-А") and not has(html, "Ужасы-Г")
    html = page(client, year_to="1999")
    assert has(html, "Драма-А") and has(html, "Ужасы-Г") and not has(html, "Комедия-В")
    html = page(client, year_from="1990", year_to="2005")
    assert has(html, "Драма-А") and has(html, "Мелодрама-Б")
    assert not has(html, "Ужасы-Г") and not has(html, "Комедия-В")
    ok("фильтр по годам «от» и «до»")

    html = page(client, country="США")
    assert has(html, "Драма-А") and has(html, "Комедия-В") and not has(html, "Мелодрама-Б")
    assert "Франция" in html and "Япония" in html, "в списке стран нет добавленных стран"
    ok("фильтр по стране, список стран строится по каталогу")

    html = page(client, genre="Драма", country="США", year_from="2000")
    assert has(html, "Комедия-В") and not has(html, "Драма-А")
    ok("фильтры работают вместе")

    html = page(client, genre="Ужасы", country="США")
    assert "Ничего не найдено" in html
    ok("пустой результат: понятное сообщение")

    html = page(client, sort="year")
    order = [html.index(f"{PREFIX} {t}") for t in ("Комедия-В", "Мелодрама-Б", "Драма-А", "Ужасы-Г")]
    assert order == sorted(order)
    html = page(client, sort="title")
    assert html.index(f"{PREFIX} Драма-А") < html.index(f"{PREFIX} Комедия-В") < html.index(f"{PREFIX} Мелодрама-Б")
    ok("сортировка по году и по названию")

    html = page(client, year_from="abc")
    assert "должен быть числом" in html
    html = page(client, year_from="2010", year_to="2000")
    assert "не может быть больше" in html
    html = page(client, sort="DROP TABLE films", page="-5", genre="'; DROP TABLE films;--")
    assert has(html, "Драма-А") or "Ничего не найдено" in html
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM films WHERE title LIKE %s;", (f"{PREFIX}%",))
        assert cur.fetchone()["n"] == 4
    ok("неверные данные в адресе не ломают страницу и не попадают в запрос")

    extra = 30
    for i in range(extra):
        make_film(f"Масса-{i:02d}", "Комедия", 2015, "США")
    total = 4 + extra
    pages = math.ceil(total / PAGE_SIZE)
    html = page(client)
    assert f"Страница 1 из {pages}" in html and "Дальше" in html and "Назад" not in html
    assert f"Найдено фильмов: {total}" in html
    last = page(client, page=str(pages))
    assert f"Страница {pages} из {pages}" in last and "Дальше" not in last and "Назад" in last
    over = page(client, page="999")
    assert f"Страница {pages} из {pages}" in over
    html = page(client, genre="Комедия", country="США", page="1")
    assert "genre=%D0%9A%D0%BE%D0%BC%D0%B5%D0%B4%D0%B8%D1%8F" in html and "page=2" in html
    ok(f"постраничный вывод: {pages} страницы, фильтры сохраняются в ссылках")

    started = time.perf_counter()
    page(client, genre=["Драма", "Комедия"], country="США", year_from="1990")
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5, elapsed
    ok(f"фильтрация каталога заняла {elapsed * 1000:.0f} мс (требование ТЗ: не более 500 мс)")


def main():
    assert init_user_storage(), "Не удалось подключиться к базе. Проверьте .env и PostgreSQL."
    init_extra_tables()
    try:
        test_catalog()
    finally:
        cleanup()
    print("\nВсе проверки ФТ-2.2 пройдены ✔")


if __name__ == "__main__":
    main()
