"""ФТ-1.3. Оформление отзыва и критериальной оценки (пп. 4.5.1, 4.5.2, 5.3.2 ТЗ)."""
from flask import (Blueprint, flash, redirect, render_template, request, session, url_for)

from dbutil import db_cursor
from helpers import decorate_film, forbidden, login_required, video_url_for
from moderation import precheck_review

reviews_bp = Blueprint("reviews", __name__)

CRITERIA = (("plot_score", "Сюжет"), ("acting_score", "Актёрская игра"),
            ("visual_score", "Музыка и визуал"))
MIN_TEXT, MAX_TEXT = 10, 2000
STATUS_TITLES = {"approved": "Опубликован", "pending": "На проверке"}


def _load_film(cur, film_id):
    cur.execute("SELECT id, title, genres, year, country, director, actors, duration, "
                "description, poster_url FROM films WHERE id = %s;", (film_id,))
    film = cur.fetchone()
    return decorate_film(film) if film else None


@reviews_bp.route("/reviews")
@login_required
def index():
    q = request.args.get("q", "").strip()[:100]
    with db_cursor() as cur:
        sql = ("SELECT f.id, f.title, f.genres, f.year, f.country, f.duration, f.poster_url, "
               "(SELECT COUNT(*) FROM reviews r WHERE r.film_id = f.id AND r.status = 'approved') AS reviews_count, "
               "(SELECT overall_score FROM reviews r WHERE r.film_id = f.id AND r.user_id = %s) AS my_score "
               "FROM films f ")
        params = [session["user"]["id"]]
        if q:
            sql += "WHERE f.title ILIKE %s "
            params.append(f"%{q}%")
        sql += "ORDER BY f.created_at DESC, f.id DESC LIMIT 60;"
        cur.execute(sql, params)
        films = [decorate_film(f) for f in cur.fetchall()]
    return render_template("reviews/index.html", films=films, q=q)


def _render_film_page(film_id, form=None, status=200):
    user = session["user"]
    with db_cursor() as cur:
        film = _load_film(cur, film_id)
        if film is None:
            flash("Такого фильма нет. Выберите фильм из списка.", "error")
            return redirect(url_for("reviews.index"))
        cur.execute("SELECT COUNT(*) AS n, AVG(plot_score) AS plot, AVG(acting_score) AS acting, "
                    "AVG(visual_score) AS visual, AVG(overall_score) AS overall "
                    "FROM reviews WHERE film_id = %s AND status = 'approved';", (film_id,))
        agg = cur.fetchone()
        cur.execute("SELECT * FROM reviews WHERE film_id = %s AND user_id = %s;", (film_id, user["id"]))
        mine = cur.fetchone()
        cur.execute("SELECT r.*, u.name, u.email FROM reviews r JOIN users u ON u.id = r.user_id "
                    "WHERE r.film_id = %s AND r.status = 'approved' AND r.user_id <> %s "
                    "ORDER BY r.updated_at DESC LIMIT 50;", (film_id, user["id"]))
        others = cur.fetchall()
        cur.execute("SELECT e.id, e.title, e.text, e.updated_at, u.name, u.email FROM expert_reviews e "
                    "JOIN users u ON u.id = e.author_id WHERE e.film_id = %s AND e.status = 'approved' "
                    "ORDER BY e.updated_at DESC LIMIT 20;", (film_id,))
        experts = cur.fetchall()
    for r in others:
        r["author_name"] = r["name"] or r["email"].split("@")[0]
    values = form if form is not None else (mine or {})
    return render_template("reviews/film.html", film=film, agg=agg, mine=mine, others=others,
                           values=values, experts=experts, criteria=CRITERIA, min_text=MIN_TEXT,
                           max_text=MAX_TEXT, status_titles=STATUS_TITLES,
                           video_url=video_url_for(film_id)), status


@reviews_bp.route("/reviews/<int:film_id>", methods=["GET", "POST"])
@login_required
def film_page(film_id):
    if request.method == "GET":
        return _render_film_page(film_id)

    if session["user"].get("role") == "admin":
        return forbidden("Администратор модерирует отзывы, но не оставляет их.")

    # --- проверка формы ---
    errors, scores = [], {}
    for field, label in CRITERIA:
        raw = request.form.get(field, "").strip()
        if raw.isascii() and raw.isdigit() and 1 <= int(raw) <= 10:
            scores[field] = int(raw)
        else:
            errors.append(f"Поставьте оценку от 1 до 10 за критерий «{label}».")
    text = request.form.get("text", "").strip()
    if len(text) < MIN_TEXT:
        errors.append(f"Напишите отзыв: не короче {MIN_TEXT} символов. Расскажите, что понравилось или нет.")
    elif len(text) > MAX_TEXT:
        errors.append(f"Отзыв слишком длинный: не больше {MAX_TEXT} символов. Сократите текст.")
    if errors:
        for message in errors:
            flash(message, "error")
        form = dict(scores, text=text)
        return _render_film_page(film_id, form=form, status=200)

    overall = round(sum(scores.values()) / len(scores), 1)
    review = dict(scores, text=text, film_id=film_id, user_id=session["user"]["id"])
    status = precheck_review(review)  # п. 4.5.2: отзыв уходит на предварительную проверку

    with db_cursor(commit=True) as cur:
        if _load_film(cur, film_id) is None:
            flash("Такого фильма нет. Выберите фильм из списка.", "error")
            return redirect(url_for("reviews.index"))
        # Один отзыв на пару «пользователь + фильм»: повторная отправка не создаёт дубликат (п. 5.3.2)
        cur.execute(
            "INSERT INTO reviews (film_id, user_id, plot_score, acting_score, visual_score, "
            "overall_score, text, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (film_id, user_id) DO UPDATE SET plot_score = EXCLUDED.plot_score, "
            "acting_score = EXCLUDED.acting_score, visual_score = EXCLUDED.visual_score, "
            "overall_score = EXCLUDED.overall_score, text = EXCLUDED.text, "
            "status = EXCLUDED.status, updated_at = CURRENT_TIMESTAMP "
            "RETURNING (xmax = 0) AS inserted;",
            (film_id, review["user_id"], scores["plot_score"], scores["acting_score"],
             scores["visual_score"], overall, text, status))
        inserted = cur.fetchone()["inserted"]

    if status == "approved":
        flash("Спасибо! Отзыв опубликован." if inserted else "Отзыв обновлён.", "success")
    else:
        flash("Отзыв отправлен на проверку. После неё он появится на странице фильма.", "success")
    return redirect(url_for("reviews.film_page", film_id=film_id))


@reviews_bp.route("/reviews/<int:film_id>/delete", methods=["POST"])
@login_required
def delete(film_id):
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM reviews WHERE film_id = %s AND user_id = %s;",
                    (film_id, session["user"]["id"]))
        deleted = cur.rowcount
    flash("Отзыв удалён." if deleted else "У вас нет отзыва на этот фильм.",
          "success" if deleted else "error")
    return redirect(url_for("reviews.film_page", film_id=film_id))
