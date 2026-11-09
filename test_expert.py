"""Проверка рецензий авторов.  Запуск:  python test_expert.py
Нужны PostgreSQL и верный пароль в .env. Тестовые данные удаляются.
"""
from app import app
from dbutil import db_cursor
from models import init_user_storage
from schema import init_extra_tables
from test_features import TAG, cleanup, login, make_film, make_user, ok, post

TEXT = "Фильм держит в напряжении до конца: сильная режиссура, точный монтаж и работа актёров. " * 2


def test_expert():
    app.config["TESTING"] = True
    viewer_id, viewer = make_user()
    author_id, author = make_user("author")
    admin_id, admin = make_user("admin")
    film = make_film("Рецензируемый", "Драма", 2010)

    guest = app.test_client()
    assert guest.get("/expert").status_code == 302
    cv = app.test_client(); login(cv, viewer)
    assert cv.get("/expert").status_code == 403
    assert post(cv, f"/expert/film/{film}", title="Заголовок рецензии", text=TEXT).status_code == 403
    ok("рецензии недоступны гостям и зрителям")

    ca = app.test_client(); login(ca, author)
    assert "Выбрать фильм" in ca.get("/expert").get_data(as_text=True)
    assert "Рецензируемый" in ca.get(f"/expert?q={'Рецензируемый'}").get_data(as_text=True)
    r = post(ca, f"/expert/film/{film}", title="abc", text="коротко")
    page = r.get_data(as_text=True)
    assert "от 5 до 150" in page and "не короче 100" in page
    ok("автор видит список фильмов; короткие заголовок и текст отклоняются")

    assert post(ca, f"/expert/film/{film}", title="Сильная драма", text=TEXT).status_code == 302
    post(ca, f"/expert/film/{film}", title="Сильная драма (правка)", text=TEXT)
    with db_cursor() as cur:
        cur.execute("SELECT id, title, status FROM expert_reviews WHERE film_id = %s AND author_id = %s;", (film, author_id))
        rows = cur.fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "pending" and "правка" in rows[0]["title"], rows
    exp_id = rows[0]["id"]
    ok("рецензия уходит на проверку, повторная отправка обновляет, а не дублирует")

    cvs = app.test_client(); login(cvs, viewer)
    assert "Сильная драма" not in cvs.get(f"/reviews/{film}").get_data(as_text=True)
    ok("пока рецензию не проверили, зрители её не видят")

    cadm = app.test_client(); login(cadm, admin)
    assert ca.get("/admin/expert").status_code == 403
    html = cadm.get("/admin/expert").get_data(as_text=True)
    assert "Сильная драма" in html and "Рецензируемый" in html
    post(cadm, f"/admin/expert/{exp_id}/decide", action="reject", comment="")
    with db_cursor() as cur:
        cur.execute("SELECT status FROM expert_reviews WHERE id = %s;", (exp_id,))
        assert cur.fetchone()["status"] == "pending"
    post(cadm, f"/admin/expert/{exp_id}/decide", action="reject", comment="Слишком мало аргументов")
    assert "Слишком мало аргументов" in ca.get("/expert").get_data(as_text=True)
    ok("админ видит рецензию; отказ без причины не принимается; причина видна автору")

    post(ca, f"/expert/film/{film}", title="Сильная драма", text=TEXT + " Добавила аргументов.")
    with db_cursor() as cur:
        cur.execute("SELECT status, comment FROM expert_reviews WHERE id = %s;", (exp_id,))
        row = cur.fetchone()
    assert row["status"] == "pending" and row["comment"] is None
    post(cadm, f"/admin/expert/{exp_id}/decide", action="approve")
    page = cvs.get(f"/reviews/{film}").get_data(as_text=True)
    assert "Сильная драма" in page and "Рецензия автора" in page
    post(cadm, f"/admin/expert/{exp_id}/decide", action="reject", comment="передумали совсем")
    with db_cursor() as cur:
        cur.execute("SELECT status FROM expert_reviews WHERE id = %s;", (exp_id,))
        assert cur.fetchone()["status"] == "approved"
        cur.execute("SELECT action FROM admin_log WHERE admin_id = %s ORDER BY id;", (admin_id,))
        assert [r["action"] for r in cur.fetchall()] == ["expert_rejected", "expert_approved"]
    ok("после исправления рецензия одобряется и видна всем с пометкой «Рецензия автора»; всё в журнале")

    assert "Написать рецензию автора" in ca.get(f"/reviews/{film}").get_data(as_text=True)
    assert "Написать рецензию автора" not in cvs.get(f"/reviews/{film}").get_data(as_text=True)
    post(ca, f"/expert/{exp_id}/delete")
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM expert_reviews WHERE id = %s;", (exp_id,))
        assert cur.fetchone()["n"] == 0
    ok("кнопка рецензии только у авторов; автор может удалить свою рецензию")


def main():
    assert init_user_storage(), "Не удалось подключиться к базе. Проверьте .env и PostgreSQL."
    init_extra_tables()
    try:
        test_expert()
    finally:
        cleanup()
    print("\nВсе проверки рецензий авторов пройдены ✔")


if __name__ == "__main__":
    main()
