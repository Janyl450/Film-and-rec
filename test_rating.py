"""Проверка ФТ-2.3 (взвешенный рейтинг).  Запуск:  python test_rating.py
Нужен запущенный PostgreSQL и верный пароль в .env. Тестовые данные в конце удаляются.
"""
import time
import uuid

from app import app
from dbutil import db_cursor
from models import AuthAndPreferencesModule as Auth, init_user_storage
from rating import MIN_VOTES, film_rating, ratings_for, weighted_rating
from schema import init_extra_tables

TAG = uuid.uuid4().hex[:6]
PASSWORD = "password123"


def ok(text):
    print("OK:", text)


# ---------- формула без базы ----------
def test_formula():
    assert weighted_rating(None, 0, 7) is None
    assert weighted_rating(10, 0, 7) is None, "нет отзывов — нет рейтинга"
    one = weighted_rating(10, 1, 7)
    assert one == round(1 / (1 + MIN_VOTES) * 10 + MIN_VOTES / (1 + MIN_VOTES) * 7, 1)
    assert one < 8, f"одна оценка «10» не должна давать почти 10, получили {one}"
    ten = weighted_rating(10, 10, 7)
    assert ten > one, "чем больше отзывов, тем ближе к реальному среднему"
    assert weighted_rating(10, 1000, 7) > 9.9
    assert weighted_rating(7, 3, 7) == 7.0
    ok(f"формула: одна «10» даёт {one}, десять «10» дают {ten}; порог m = {MIN_VOTES}")


# ---------- вспомогательное ----------
def make_user():
    email = f"t{TAG}_{uuid.uuid4().hex[:5]}@example.com"
    good, message = Auth.register(email, PASSWORD, "Тест", "viewer")
    assert good, message
    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s;", (email,))
        return cur.fetchone()["id"]


def make_film(title, author_id=None):
    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO films (title, genres, year, author_id) VALUES (%s, 'Драма', 2000, %s) RETURNING id;",
                    (f"[тест{TAG}] {title}", author_id))
        return cur.fetchone()["id"]


def add_review(film_id, user_id, score, status="approved"):
    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO reviews (film_id, user_id, plot_score, acting_score, visual_score, "
                    "overall_score, text, status) VALUES (%s, %s, %s, %s, %s, %s, 'тестовый отзыв', %s) "
                    "ON CONFLICT (film_id, user_id) DO UPDATE SET overall_score = EXCLUDED.overall_score, "
                    "status = EXCLUDED.status;",
                    (film_id, user_id, score, score, score, score, status))


def global_average():
    with db_cursor() as cur:
        cur.execute("SELECT COALESCE(AVG(overall_score), 0) AS c FROM reviews WHERE status = 'approved';")
        return float(cur.fetchone()["c"])


def cleanup():
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM films WHERE title LIKE %s;", (f"[тест{TAG}]%",))
        cur.execute("DELETE FROM users WHERE email LIKE %s;", (f"t{TAG}\\_%",))


# ---------- расчёт по базе ----------
def test_database():
    users = [make_user() for _ in range(8)]
    empty = make_film("Без отзывов")
    lone = make_film("Одна десятка")
    popular = make_film("Много отзывов")

    # «фон» — оценки других фильмов, чтобы среднее по сайту не равнялось единственной десятке
    background = make_film("Фон")
    for u in users[:3]:
        add_review(background, u, 5)

    assert film_rating(empty) == {"value": None, "votes": 0, "average": None}
    ok("фильм без отзывов: рейтинга нет")

    add_review(lone, users[4], 10)
    r = film_rating(lone)
    assert r["votes"] == 1 and r["average"] == 10.0
    assert r["value"] == weighted_rating(10, 1, global_average()), r
    assert r["value"] < 10
    ok(f"одна оценка «10» не даёт рейтинг 10 (получилось {r['value']})")

    for i, u in enumerate(users):
        add_review(popular, u, 9 if i % 2 == 0 else 8)  # среднее 8.5, 8 отзывов
    r = film_rating(popular)
    assert r["votes"] == 8 and r["average"] == 8.5
    assert r["value"] == weighted_rating(8.5, 8, global_average()), (r, global_average())
    assert abs(r["value"] - 8.5) <= abs(film_rating(lone)["value"] - 10)
    ok(f"8 отзывов, среднее 8.5 → взвешенный рейтинг {r['value']} совпадает с формулой")

    before = film_rating(popular)["value"]
    extra = make_user()
    add_review(popular, extra, 1, status="pending")
    assert film_rating(popular)["value"] == before and film_rating(popular)["votes"] == 8
    ok("отзыв на проверке (pending) в рейтинг не входит")

    add_review(popular, extra, 1, status="approved")  # админ одобрил
    after = film_rating(popular)
    assert after["votes"] == 9 and after["value"] < before
    ok(f"после одобрения рейтинг пересчитался сразу: {before} → {after['value']} (п. 5.1.2)")

    many = ratings_for([empty, lone, popular, 987654321])
    assert set(many) == {empty, lone, popular, 987654321}
    assert many[987654321]["value"] is None and many[popular]["votes"] == 9
    assert ratings_for([]) == {}
    ok("ratings_for: несколько фильмов одним запросом, несуществующий id не ломает")

    # скорость на большом каталоге (п. 5.1.1 — не более 0,5 с)
    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO films (title, genres, year) SELECT %s || g, 'Драма', 2000 "
                    "FROM generate_series(1, 5000) g;", (f"[тест{TAG}] массовый ",))
        cur.execute("SELECT id FROM films WHERE title LIKE %s;", (f"[тест{TAG}] массовый%",))
        ids = [row["id"] for row in cur.fetchall()]
    started = time.perf_counter()
    ratings_for(ids)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5, elapsed
    ok(f"рейтинг для 5000 фильмов посчитан за {elapsed * 1000:.0f} мс (требование ТЗ: не более 500 мс)")
    return empty, lone, popular


# ---------- страницы автора ----------
def csrf(client):
    client.get("/")
    with client.session_transaction() as s:
        return s["_csrf"]


def test_pages():
    app.config["TESTING"] = True
    author_id = make_user()
    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET role = 'author' WHERE id = %s RETURNING email;", (author_id,))
        email = cur.fetchone()["email"]
    mine = make_film("Мой без оценок", author_id)
    rated = make_film("Мой с оценками", author_id)
    for _ in range(3):
        add_review(rated, make_user(), 9)

    from flask import template_rendered
    seen = {}

    def grab(sender, template, context, **extra):
        seen[template.name] = context
    template_rendered.connect(grab, app)

    c = app.test_client()
    r = c.post("/login", data={"email": email, "password": PASSWORD, "_csrf": csrf(c)})
    assert r.status_code == 302
    try:
        assert c.get("/films/my").status_code == 200
        by_id = {f["id"]: f for f in seen["films/my_films.html"]["films"]}
        assert by_id[mine]["rating"]["value"] is None
        expected = film_rating(rated)
        assert expected["votes"] == 3 and by_id[rated]["rating"] == expected, by_id[rated]["rating"]
        assert c.get(f"/films/{rated}").status_code == 200
        assert seen["films/view.html"]["film"]["rating"] == expected
    finally:
        template_rendered.disconnect(grab, app)
    ok("«Мои фильмы» и карточка фильма получают film.rating (value / votes / average)")


def main():
    assert init_user_storage(), "Не удалось подключиться к базе. Проверьте .env и PostgreSQL."
    init_extra_tables()
    test_formula()
    try:
        test_database()
        test_pages()
    finally:
        cleanup()
    print("\nВсе проверки ФТ-2.3 пройдены ✔")


if __name__ == "__main__":
    main()
