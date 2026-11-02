"""Проверка ФТ-2.6: заявка автора на подтверждение статуса.  Запуск:  python test_author_application.py
Нужен запущенный PostgreSQL и верный пароль в .env. Тестовые данные в конце удаляются.
"""
import uuid

from app import app
from author_applications import is_confirmed_author
from dbutil import db_cursor
from models import AuthAndPreferencesModule as Auth, init_user_storage
from schema import init_extra_tables

TAG = uuid.uuid4().hex[:6]
PASSWORD = "password123"
URL = "https://example.com/my-blog"
ABOUT = "Пишу рецензии на авторское кино уже три года."


def ok(text):
    print("OK:", text)


def csrf(client):
    client.get("/")
    with client.session_transaction() as s:
        return s["_csrf"]


def post(client, url, **data):
    data["_csrf"] = csrf(client)
    return client.post(url, data=data)


def login(client, email):
    assert post(client, "/login", email=email, password=PASSWORD).status_code == 302, "вход не удался"


def make_user(role="viewer"):
    email = f"t{TAG}_{uuid.uuid4().hex[:5]}@example.com"
    good, message = Auth.register(email, PASSWORD, "Тест " + role, "viewer")
    assert good, message
    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET role = %s WHERE email = %s RETURNING id;", (role, email))
        return cur.fetchone()["id"], email


def count_apps(user_id, status=None):
    with db_cursor() as cur:
        if status:
            cur.execute("SELECT COUNT(*) AS n FROM author_applications WHERE user_id = %s AND status = %s;",
                        (user_id, status))
        else:
            cur.execute("SELECT COUNT(*) AS n FROM author_applications WHERE user_id = %s;", (user_id,))
        return cur.fetchone()["n"]


def cleanup():
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM admin_log WHERE target LIKE %s;", (f"t{TAG}\\_%",))
        cur.execute("DELETE FROM users WHERE email LIKE %s;", (f"t{TAG}\\_%",))


def test_applications():
    app.config["TESTING"] = True
    viewer_id, viewer = make_user("viewer")
    author_id, author = make_user("author")
    admin_id, admin = make_user("admin")

    guest = app.test_client()
    assert guest.get("/author/application").status_code == 302
    ok("страница заявки закрыта для гостей")

    ca = app.test_client()
    login(ca, admin)
    assert ca.get("/author/application").status_code == 403
    ok("администратору заявка не нужна")

    cv = app.test_client()
    login(cv, viewer)
    html = cv.get("/author/application").get_data(as_text=True)
    assert "Подать заявку" in html and "Ссылка на блог или портфолио" in html
    ok("зритель видит форму заявки")

    # --- проверка данных ---
    r = post(cv, "/author/application", portfolio_url="не ссылка", about=ABOUT)
    html = r.get_data(as_text=True)
    assert "должна начинаться с" in html and count_apps(viewer_id) == 0
    assert "не ссылка" in html, "введённый текст пропал из формы"
    r = post(cv, "/author/application", portfolio_url="javascript:alert(1)", about=ABOUT)
    assert "должна начинаться с" in r.get_data(as_text=True) and count_apps(viewer_id) == 0
    r = post(cv, "/author/application", portfolio_url=URL, about="коротко")
    assert "не короче" in r.get_data(as_text=True) and count_apps(viewer_id) == 0
    r = post(cv, "/author/application", portfolio_url=URL, about="а" * 2001)
    assert "слишком длинный" in r.get_data(as_text=True) and count_apps(viewer_id) == 0
    ok("неверная ссылка и слишком короткий или длинный рассказ отклоняются с понятным сообщением")

    # --- отправка ---
    r = post(cv, "/author/application", portfolio_url=URL, about=ABOUT)
    assert r.status_code == 302
    assert count_apps(viewer_id, "pending") == 1
    html = cv.get("/author/application").get_data(as_text=True)
    assert "На проверке" in html and URL in html and "Подать заявку" not in html
    ok("заявка отправлена, статус «На проверке», форма скрыта")

    post(cv, "/author/application", portfolio_url=URL, about=ABOUT)
    assert count_apps(viewer_id) == 1, "повторная отправка создала вторую заявку"
    ok("пока заявка на проверке, вторую создать нельзя")

    # --- администратор видит заявку (это страница Айтунук) ---
    html = ca.get("/admin/applications").get_data(as_text=True)
    assert viewer in html
    ok("заявка видна администратору")

    # --- отказ ---
    with db_cursor() as cur:
        cur.execute("SELECT id FROM author_applications WHERE user_id = %s;", (viewer_id,))
        app_id = cur.fetchone()["id"]
    post(ca, f"/admin/applications/{app_id}/decide", action="reject", comment="Нет примеров работ")
    html = cv.get("/author/application").get_data(as_text=True)
    assert "Отклонена" in html and "Нет примеров работ" in html and "Новая заявка" in html
    assert "Пишу рецензии" in html, "прошлая заявка не подставилась в форму"
    ok("после отказа видна причина, форма открыта и заполнена прошлыми данными")

    r = post(cv, "/author/application", portfolio_url="https://example.com/new", about=ABOUT + " Добавила примеры.")
    assert r.status_code == 302 and count_apps(viewer_id) == 2 and count_apps(viewer_id, "pending") == 1
    ok("после отказа можно подать новую заявку")

    # --- до подтверждения фильмы добавлять нельзя ---
    assert not is_confirmed_author(viewer_id)
    ca2 = app.test_client()
    login(ca2, author)
    r = ca2.get("/films/new")
    assert r.status_code == 302 and "/author/application" in r.headers["Location"]
    assert ca2.get("/films/my").status_code == 302
    assert "Подать заявку" in ca2.get("/author/application").get_data(as_text=True)
    ok("автор без подтверждения не может добавлять фильмы: его отправляют на страницу заявки")

    # --- одобрение ---
    with db_cursor() as cur:
        cur.execute("SELECT id FROM author_applications WHERE user_id = %s AND status = 'pending';", (viewer_id,))
        app2 = cur.fetchone()["id"]
    post(ca, f"/admin/applications/{app2}/decide", action="approve")
    assert is_confirmed_author(viewer_id)
    html = cv.get("/author/application").get_data(as_text=True)
    assert "Подтверждена" in html and "профиль подтверждён" in html
    r = cv.get("/films/new")
    assert r.status_code == 200, r.status_code
    assert cv.get("/films/my").status_code == 200
    ok("после одобрения зритель становится автором и может добавлять фильмы")

    post(cv, "/author/application", portfolio_url=URL, about=ABOUT)
    assert count_apps(viewer_id) == 2, "подтверждённый автор отправил ещё одну заявку"
    ok("подтверждённому автору новая заявка не нужна")

    # --- автор, зарегистрированный сразу как «автор», тоже подаёт заявку ---
    r = post(ca2, "/author/application", portfolio_url=URL, about=ABOUT)
    assert r.status_code == 302 and count_apps(author_id, "pending") == 1
    with db_cursor() as cur:
        cur.execute("SELECT id FROM author_applications WHERE user_id = %s;", (author_id,))
        app3 = cur.fetchone()["id"]
    post(ca, f"/admin/applications/{app3}/decide", action="approve")
    assert ca2.get("/films/new").status_code == 200
    ok("автор, зарегистрированный сразу автором, после одобрения тоже получает доступ")

    assert "Статус автора" in cv.get("/catalog").get_data(as_text=True)
    assert "Статус автора" not in ca.get("/catalog").get_data(as_text=True)
    ok("ссылка «Статус автора» есть в меню у зрителей и авторов, у администратора её нет")


def main():
    assert init_user_storage(), "Не удалось подключиться к базе. Проверьте .env и PostgreSQL."
    init_extra_tables()
    try:
        test_applications()
    finally:
        cleanup()
    print("\nВсе проверки ФТ-2.6 пройдены ✔")


if __name__ == "__main__":
    main()
