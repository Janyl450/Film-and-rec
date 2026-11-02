"""ФТ-2.6. Заявка автора на подтверждение статуса (пп. 4.2.2 и 4.10.1 ТЗ).

Автор указывает ссылку на блог или портфолио и коротко рассказывает о себе. Заявка попадает в таблицу
author_applications (её создала Айтунук в schema.py), где её видит и обрабатывает администратор
(admin.py, ФТ-1.6). Статусы те же, что в админке: pending, approved, rejected.

Подтверждённый автор: у пользователя есть заявка со статусом approved. Только такие авторы могут
добавлять и изменять фильмы (п. 4.4.1 ТЗ): проверка в films.py вызывает is_confirmed_author().
"""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from dbutil import db_cursor
from helpers import forbidden, login_required, safe_url

author_app_bp = Blueprint("author_application", __name__)

MIN_ABOUT, MAX_ABOUT = 20, 2000
MAX_URL = 500
STATUS_TITLES = {"pending": "На проверке", "approved": "Подтверждена", "rejected": "Отклонена"}


def is_confirmed_author(user_id):
    """True, если администратор одобрил заявку этого пользователя."""
    with db_cursor() as cur:
        cur.execute("SELECT 1 FROM author_applications WHERE user_id = %s AND status = 'approved' LIMIT 1;",
                    (user_id,))
        return cur.fetchone() is not None


def _latest_application(cur, user_id):
    cur.execute("SELECT id, portfolio_url, about, status, comment, created_at, reviewed_at "
                "FROM author_applications WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT 1;",
                (user_id,))
    return cur.fetchone()


def _render_page(values=None):
    user_id = session["user"]["id"]
    with db_cursor() as cur:
        latest = _latest_application(cur, user_id)
    if latest:
        latest["portfolio"] = safe_url(latest["portfolio_url"])
    show_form = latest is None or latest["status"] == "rejected"
    if values is None:
        # после отказа подставляем прошлую заявку, чтобы её можно было поправить
        values = {"portfolio_url": latest["portfolio_url"] or "", "about": latest["about"] or ""} \
            if latest and latest["status"] == "rejected" else {}
    return render_template("author/apply.html", latest=latest, show_form=show_form, values=values,
                           titles=STATUS_TITLES, min_about=MIN_ABOUT, max_about=MAX_ABOUT)


@author_app_bp.route("/author/application", methods=["GET", "POST"])
@login_required
def apply():
    user = session["user"]
    if user.get("role") == "admin":
        return forbidden("Администратору заявка не нужна: у него и так есть доступ ко всему.")

    if request.method == "GET":
        return _render_page()

    portfolio = request.form.get("portfolio_url", "").strip()
    about = request.form.get("about", "").strip()
    errors = []
    if not safe_url(portfolio) or " " in portfolio or len(portfolio) > MAX_URL:
        errors.append("Укажите ссылку на ваш блог или портфолио. Она должна начинаться с "
                      "http:// или https:// (скопируйте адрес целиком из браузера).")
    if len(about) < MIN_ABOUT:
        errors.append(f"Расскажите о себе подробнее: не короче {MIN_ABOUT} символов. "
                      "Например, о чём вы пишете и сколько времени занимаетесь кино.")
    elif len(about) > MAX_ABOUT:
        errors.append(f"Рассказ о себе слишком длинный: не больше {MAX_ABOUT} символов. Сократите текст.")
    if errors:
        for message in errors:
            flash(message, "error")
        return _render_page({"portfolio_url": portfolio, "about": about})

    with db_cursor(commit=True) as cur:
        # блокируем строку пользователя: две одновременные отправки не создадут две заявки
        cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE;", (user["id"],))
        latest = _latest_application(cur, user["id"])
        if latest and latest["status"] == "pending":
            flash("Ваша заявка уже отправлена и ждёт проверки. Дождитесь решения администратора.", "error")
        elif latest and latest["status"] == "approved":
            flash("Ваш профиль уже подтверждён. Можно добавлять фильмы.", "error")
        else:
            cur.execute("INSERT INTO author_applications (user_id, portfolio_url, about) VALUES (%s, %s, %s);",
                        (user["id"], portfolio, about))
            flash("Заявка отправлена. Администратор проверит её, а решение появится на этой странице.",
                  "success")
    return redirect(url_for("author_application.apply"))
