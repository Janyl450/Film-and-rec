"""Проверка ФТ-1.2, ФТ-1.3 и ФТ-1.6.  Запуск:  python test_features.py
Нужен запущенный PostgreSQL и верный пароль в .env. Тестовые данные в конце удаляются.
"""
import time
import uuid

from app import app
from dbutil import db_cursor
from matching import Prefs, rank_films, score_film
from models import AuthAndPreferencesModule as Auth, init_user_storage
from schema import init_extra_tables

TAG = uuid.uuid4().hex[:6]
PASSWORD = "password123"


def ok(text):
    print("OK:", text)


# ---------- ФТ-1.2: расчёт без базы ----------
def test_matching():
    prefs = Prefs(favorite=["Драма", "Триллер"], disliked=["Ужасы"], year_from=1990, year_to=2020)
    perfect = {"genres": "Драма, Триллер", "year": 2000}
    half = {"genres": "Драма, Комедия", "year": 2000}
    old = {"genres": "Драма, Триллер", "year": 1960}
    horror = {"genres": "Ужасы, Триллер", "year": 2000}
    assert score_film(prefs, perfect)["percent"] == 100
    assert score_film(prefs, half)["percent"] == round(0.7 * 0.5 * 100 + 30)  # 65
    assert score_film(prefs, old)["percent"] == 70, score_film(prefs, old)["percent"]
    assert score_film(prefs, horror) is None, "нежелательный жанр должен исключать фильм"
    assert any("Совпали жанры" in r for r in score_film(prefs, perfect)["reasons"])
    only_genres = Prefs(favorite=["Драма"])
    assert score_film(only_genres, {"genres": "Драма", "year": None})["percent"] == 100
    only_years = Prefs(year_from=2000)
    assert score_film(only_years, {"genres": "Комедия", "year": 2010})["percent"] == 100
    assert score_film(only_years, {"genres": "Комедия", "year": 1985})["percent"] == 0
    ranked = rank_films(prefs, [half, old, perfect, horror])
    assert [f["match"]["percent"] for f in ranked] == [100, 70, 65]
    ok("процент совпадения и исключение нежелательных жанров")

    films = [{"genres": "Драма, Триллер, Боевик", "year": 1950 + i % 70} for i in range(5000)]
    started = time.perf_counter()
    rank_films(prefs, films)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5, elapsed
    ok(f"подбор среди 5000 фильмов занял {elapsed * 1000:.0f} мс (требование ТЗ: не более 500 мс)")


# ---------- вспомогательное ----------
def csrf(client):
    client.get("/")
    with client.session_transaction() as s:
        return s["_csrf"]


def post(client, url, **data):
    data["_csrf"] = csrf(client)
    return client.post(url, data=data)


def login(client, email):
    r = post(client, "/login", email=email, password=PASSWORD)
    assert r.status_code == 302, "вход не удался"


def make_user(role="viewer"):
    email = f"t{TAG}_{uuid.uuid4().hex[:5]}@example.com"
    good, message = Auth.register(email, PASSWORD, "Тест " + role, "viewer")
    assert good, message
    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET role = %s WHERE email = %s RETURNING id;", (role, email))
        return cur.fetchone()["id"], email


def make_film(title, genres, year):
    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO films (title, genres, year, country, duration) VALUES (%s, %s, %s, 'США', 100) RETURNING id;",
                    (f"[тест{TAG}] {title}", genres, year))
        return cur.fetchone()["id"]


def cleanup():
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM films WHERE title LIKE %s;", (f"[тест{TAG}]%",))
        cur.execute("DELETE FROM users WHERE email LIKE %s;", (f"t{TAG}\\_%",))


# ---------- ФТ-1.2, ФТ-1.3, ФТ-1.6 через сайт ----------
def test_site():
    app.config["TESTING"] = True
    viewer_id, viewer = make_user()
    viewer2_id, viewer2 = make_user()
    admin_id, admin = make_user("admin")
    perfect = make_film("Идеальный", "Драма, Триллер", 2000)
    weak = make_film("Слабый", "Комедия", 1960)
    horror = make_film("Страшный", "Ужасы, Триллер", 2000)
    assert Auth.setup_preferences(viewer_id, "Драма, Триллер", "Ужасы", 1990, 2020, "")

    c = app.test_client()
    assert c.get("/recommendations?limit=240").status_code == 302
    ok("страницы закрыты для гостей")

    # --- ФТ-1.2 ---
    login(c, viewer)
    html = c.get("/recommendations?limit=240").get_data(as_text=True)
    assert f"[тест{TAG}] Идеальный" in html and "100%" in html
    assert f"[тест{TAG}] Страшный" not in html, "фильм с нежелательным жанром показан"
    assert html.index(f"[тест{TAG}] Идеальный") < html.index(f"[тест{TAG}] Слабый")
    assert "Совпали жанры: Драма, Триллер" in html
    ok("рекомендации: порядок, проценты, пояснения, исключение нежелательных жанров")

    post(c, f"/recommendations/hide/{perfect}")
    assert f"[тест{TAG}] Идеальный" not in c.get("/recommendations?limit=240").get_data(as_text=True)
    assert f"[тест{TAG}] Идеальный" in c.get("/recommendations/hidden").get_data(as_text=True)
    post(c, f"/recommendations/unhide/{perfect}")
    assert f"[тест{TAG}] Идеальный" in c.get("/recommendations?limit=240").get_data(as_text=True)
    ok("«Не интересно» скрывает фильм, «Вернуть» возвращает")

    c2 = app.test_client()
    login(c2, viewer2)
    assert "Укажите свои предпочтения" in c2.get("/recommendations").get_data(as_text=True)
    ok("без предпочтений показывается подсказка и новинки")

    # --- ФТ-1.3 ---
    good = dict(plot_score=8, acting_score=9, visual_score=10, text="Отличный фильм, смотрел на одном дыхании")
    r = post(c, f"/reviews/{perfect}", **good)
    assert r.status_code == 302
    r = post(c, f"/reviews/{perfect}", **dict(good, plot_score=6))
    with db_cursor() as cur:
        cur.execute("SELECT plot_score, overall_score FROM reviews WHERE film_id = %s AND user_id = %s;", (perfect, viewer_id))
        rows = cur.fetchall()
    assert len(rows) == 1, "повторная отправка создала дубликат"
    assert rows[0]["plot_score"] == 6 and float(rows[0]["overall_score"]) == round((6 + 9 + 10) / 3, 1)
    ok("отзыв сохраняется, повторная отправка обновляет, а не дублирует (п. 5.3.2)")

    page = c.get(f"/reviews/{perfect}").get_data(as_text=True)
    assert "Оценки зрителей" in page and "Ваш отзыв" in page
    r = post(c, f"/reviews/{perfect}", **dict(good, plot_score=11))
    assert "Поставьте оценку от 1 до 10" in r.get_data(as_text=True)
    r = post(c, f"/reviews/{perfect}", **dict(good, text="коротко"))
    assert "не короче" in r.get_data(as_text=True)
    ok("неверные оценки и короткий текст отклоняются с понятным сообщением")

    page2 = c2.get(f"/reviews/{perfect}").get_data(as_text=True)
    assert "Тест viewer" in page2 and "Сюжет 6" in page2
    ok("опубликованный отзыв виден другим зрителям")

    import reviews as reviews_module
    original = reviews_module.precheck_review
    reviews_module.precheck_review = lambda review: "pending"
    post(c2, f"/reviews/{perfect}", **good)
    reviews_module.precheck_review = original
    with db_cursor() as cur:
        cur.execute("SELECT status FROM reviews WHERE film_id = %s AND user_id = %s;", (perfect, viewer2_id))
        assert cur.fetchone()["status"] == "pending"
        cur.execute("SELECT COUNT(*) AS n FROM reviews WHERE film_id = %s AND status = 'approved';", (perfect,))
        assert cur.fetchone()["n"] == 1
    ok("подозрительный отзыв (pending) не попадает в рейтинг")

    ca = app.test_client()
    login(ca, admin)
    assert post(ca, f"/reviews/{perfect}", **good).status_code == 403
    r = post(c, f"/reviews/{perfect}/delete")
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM reviews WHERE film_id = %s AND user_id = %s;", (perfect, viewer_id))
        assert cur.fetchone()["n"] == 0
    ok("отзыв можно удалить; администратор отзывы не оставляет")

    # --- ФТ-1.6 ---
    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO author_applications (user_id, portfolio_url, about) VALUES (%s, 'https://example.com/me', 'Пишу рецензии') RETURNING id;", (viewer2_id,))
        app_id = cur.fetchone()["id"]
    assert c.get("/admin/applications").status_code == 403
    assert app.test_client().get("/admin/applications").status_code == 302
    html = ca.get("/admin/applications").get_data(as_text=True)
    assert viewer2 in html and "https://example.com/me" in html
    ok("админка закрыта для зрителей и гостей, администратор видит заявки")

    post(ca, f"/admin/applications/{app_id}/decide", action="reject", comment="")
    with db_cursor() as cur:
        cur.execute("SELECT status FROM author_applications WHERE id = %s;", (app_id,))
        assert cur.fetchone()["status"] == "pending"
    ok("отказ без причины не принимается")

    post(ca, f"/admin/applications/{app_id}/decide", action="approve")
    with db_cursor() as cur:
        cur.execute("SELECT status, reviewed_by FROM author_applications WHERE id = %s;", (app_id,))
        row = cur.fetchone()
        assert row["status"] == "approved" and row["reviewed_by"] == admin_id
        cur.execute("SELECT role FROM users WHERE id = %s;", (viewer2_id,))
        assert cur.fetchone()["role"] == "author"
    r = post(ca, f"/admin/applications/{app_id}/decide", action="reject", comment="передумала совсем")
    with db_cursor() as cur:
        cur.execute("SELECT status FROM author_applications WHERE id = %s;", (app_id,))
        assert cur.fetchone()["status"] == "approved", "обработанную заявку изменить нельзя"
    c2.get("/")
    with c2.session_transaction() as s:
        assert s["user"]["role"] == "author", "роль в сессии не обновилась"
    ok("одобрение делает пользователя автором, повторно заявку не обработать, роль обновляется сразу")

    post(ca, f"/admin/users/{viewer2_id}/toggle-block")
    assert c2.get("/recommendations").status_code == 302, "заблокированного не выкинуло"
    c3 = app.test_client()
    assert Auth.login(viewer2, PASSWORD) is None
    post(ca, f"/admin/users/{viewer2_id}/toggle-block")
    assert Auth.login(viewer2, PASSWORD) is not None
    post(ca, f"/admin/users/{admin_id}/toggle-block")
    with db_cursor() as cur:
        cur.execute("SELECT is_blocked FROM users WHERE id = %s;", (admin_id,))
        assert cur.fetchone()["is_blocked"] is False
        cur.execute("SELECT action FROM admin_log WHERE admin_id = %s ORDER BY id;", (admin_id,))
        actions = [r["action"] for r in cur.fetchall()]
    assert actions == ["application_approved", "user_blocked", "user_unblocked"], actions
    assert "Заявка одобрена" in ca.get("/admin/log").get_data(as_text=True)
    ok("блокировка и разблокировка работают, все действия записаны в журнал")


def main():
    assert init_user_storage(), "Не удалось подключиться к базе. Проверьте .env и PostgreSQL."
    init_extra_tables()
    test_matching()
    try:
        test_site()
    finally:
        cleanup()
    print("\nВсе проверки ФТ-1.2, ФТ-1.3 и ФТ-1.6 пройдены ✔")


if __name__ == "__main__":
    main()
