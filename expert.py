"""Рецензии авторов с проверкой администратором (пп. 3, 4.8.2, 4.10.1 и 4.10.2 ТЗ).

Подтверждённый автор (кинокритик) пишет развёрнутую рецензию на фильм. Рецензия сначала попадает
к администратору (раздел «Рецензии авторов» в админке), и только после одобрения её видят
все на странице фильма. Отклонённую рецензию автор может исправить и отправить ещё раз.
"""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from admin import log_action
from dbutil import db_cursor
from helpers import admin_required, decorate_film, forbidden, login_required

expert_bp = Blueprint("expert", __name__)

MIN_TITLE, MAX_TITLE = 5, 150
MIN_TEXT, MAX_TEXT = 100, 5000
MIN_REASON = 5
STATUS_TITLES = {"pending": "На проверке", "approved": "Опубликована", "rejected": "Отклонена"}
ADMIN_FILTERS = {"pending": "Ожидают проверки", "approved": "Одобрены", "rejected": "Отклонены", "all": "Все"}


def author_required(view):
    from functools import wraps

    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if session["user"].get("role") != "author":
            return forbidden("Рецензии могут писать только подтверждённые авторы. "
                             "Подайте заявку на статус автора в профиле.")
        return view(*args, **kwargs)
    return wrapper


@expert_bp.route("/expert")
@author_required
def mine():
    q = request.args.get("q", "").strip()[:100]
    with db_cursor() as cur:
        cur.execute("SELECT e.*, f.title AS film_title FROM expert_reviews e JOIN films f ON f.id = e.film_id "
                    "WHERE e.author_id = %s ORDER BY e.updated_at DESC;", (session["user"]["id"],))
        items = cur.fetchall()
        sql = "SELECT id, title, year FROM films "
        params = []
        if q:
            sql += "WHERE title ILIKE %s "
            params.append(f"%{q}%")
        sql += "ORDER BY created_at DESC, id DESC LIMIT 30;"
        cur.execute(sql, params)
        films = cur.fetchall()
    return render_template("expert/mine.html", items=items, films=films, q=q, titles=STATUS_TITLES)


@expert_bp.route("/expert/film/<int:film_id>", methods=["GET", "POST"])
@author_required
def write(film_id):
    user = session["user"]
    with db_cursor() as cur:
        cur.execute("SELECT id, title, genres, year, country, director, actors, duration, description, poster_url "
                    "FROM films WHERE id = %s;", (film_id,))
        film = cur.fetchone()
        if film is None:
            flash("Такого фильма нет. Выберите фильм из списка.", "error")
            return redirect(url_for("expert.mine"))
        decorate_film(film)
        cur.execute("SELECT * FROM expert_reviews WHERE film_id = %s AND author_id = %s;", (film_id, user["id"]))
        mine_row = cur.fetchone()

    def page(values, code=200):
        return render_template("expert/form.html", film=film, mine=mine_row, values=values,
                               titles=STATUS_TITLES, min_title=MIN_TITLE, max_title=MAX_TITLE,
                               min_text=MIN_TEXT, max_text=MAX_TEXT), code

    if request.method == "GET":
        return page(mine_row or {})

    title = request.form.get("title", "").strip()
    text = request.form.get("text", "").strip()
    errors = []
    if not MIN_TITLE <= len(title) <= MAX_TITLE:
        errors.append(f"Заголовок рецензии: от {MIN_TITLE} до {MAX_TITLE} символов.")
    if len(text) < MIN_TEXT:
        errors.append(f"Рецензия слишком короткая: не короче {MIN_TEXT} символов. "
                      "Расскажите, что удалось в фильме, а что нет, и почему.")
    elif len(text) > MAX_TEXT:
        errors.append(f"Рецензия слишком длинная: не больше {MAX_TEXT} символов.")
    if errors:
        for message in errors:
            flash(message, "error")
        return page({"title": title, "text": text}, 200)

    with db_cursor(commit=True) as cur:
        # одна рецензия автора на один фильм: повторная отправка обновляет её, а не дублирует (п. 5.3.2)
        cur.execute("INSERT INTO expert_reviews (film_id, author_id, title, text) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (film_id, author_id) DO UPDATE SET title = EXCLUDED.title, "
                    "text = EXCLUDED.text, status = 'pending', comment = NULL, reviewed_by = NULL, "
                    "reviewed_at = NULL, updated_at = CURRENT_TIMESTAMP;",
                    (film_id, user["id"], title, text))
    flash("Рецензия отправлена администратору на проверку. Решение появится в разделе «Мои рецензии».", "success")
    return redirect(url_for("expert.mine"))


@expert_bp.route("/expert/<int:expert_id>/delete", methods=["POST"])
@author_required
def delete(expert_id):
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM expert_reviews WHERE id = %s AND author_id = %s;",
                    (expert_id, session["user"]["id"]))
        if cur.rowcount:
            flash("Рецензия удалена.", "success")
    return redirect(url_for("expert.mine"))


# ---------- проверка администратором ----------
@expert_bp.route("/admin/expert")
@admin_required
def admin_list():
    status = request.args.get("status", "pending")
    if status not in ADMIN_FILTERS:
        status = "pending"
    with db_cursor() as cur:
        cur.execute("SELECT status, COUNT(*) AS n FROM expert_reviews GROUP BY status;")
        counts = {row["status"]: row["n"] for row in cur.fetchall()}
        counts["all"] = sum(counts.values())
        sql = ("SELECT e.*, f.title AS film_title, u.name, u.email FROM expert_reviews e "
               "JOIN films f ON f.id = e.film_id JOIN users u ON u.id = e.author_id ")
        params = []
        if status != "all":
            sql += "WHERE e.status = %s "
            params.append(status)
        sql += "ORDER BY (e.status = 'pending') DESC, e.updated_at DESC LIMIT 100;"
        cur.execute(sql, params)
        items = cur.fetchall()
    return render_template("admin/expert.html", items=items, status=status, counts=counts,
                           filters=ADMIN_FILTERS, titles=STATUS_TITLES, min_reason=MIN_REASON)


@expert_bp.route("/admin/expert/<int:expert_id>/decide", methods=["POST"])
@admin_required
def admin_decide(expert_id):
    action = request.form.get("action")
    comment = request.form.get("comment", "").strip()
    if action not in ("approve", "reject"):
        flash("Неизвестное действие.", "error")
        return redirect(url_for("expert.admin_list"))
    if action == "reject" and len(comment) < MIN_REASON:
        flash(f"Укажите причину отказа (не короче {MIN_REASON} символов): её увидит автор.", "error")
        return redirect(url_for("expert.admin_list"))
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT e.id, e.status, f.title FROM expert_reviews e JOIN films f ON f.id = e.film_id "
                    "WHERE e.id = %s FOR UPDATE OF e;", (expert_id,))
        row = cur.fetchone()
        if not row:
            flash("Такой рецензии нет.", "error")
        elif row["status"] != "pending":
            flash("Эта рецензия уже обработана.", "error")
        else:
            new_status = "approved" if action == "approve" else "rejected"
            cur.execute("UPDATE expert_reviews SET status = %s, comment = %s, reviewed_by = %s, "
                        "reviewed_at = CURRENT_TIMESTAMP WHERE id = %s;",
                        (new_status, comment or None, session["user"]["id"], expert_id))
            log_action(cur, "expert_" + new_status, row["title"], comment or None)
            flash("Рецензия опубликована." if action == "approve" else "Рецензия отклонена.", "success")
    return redirect(url_for("expert.admin_list", status=request.form.get("back", "pending")))
