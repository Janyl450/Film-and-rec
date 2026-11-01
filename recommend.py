"""ФТ-1.2. Персональный подбор фильмов (п. 4.3.3 ТЗ)."""
import time

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from dbutil import db_cursor
from helpers import decorate_film, login_required
from matching import prefs_from_user, rank_films, has_disliked

rec_bp = Blueprint("recommendations", __name__)

PAGE = 24


@rec_bp.route("/recommendations")
@login_required
def index():
    user_id = session["user"]["id"]
    try:
        limit = max(PAGE, min(int(request.args.get("limit", PAGE)), 240))
    except ValueError:
        limit = PAGE

    started = time.perf_counter()
    with db_cursor() as cur:
        cur.execute("SELECT favorite_genres, disliked_genres, year_from, year_to "
                    "FROM users WHERE id = %s;", (user_id,))
        prefs = prefs_from_user(cur.fetchone())
        cur.execute(
            "SELECT id, title, genres, year, country, duration, poster_url FROM films "
            "WHERE id NOT IN (SELECT film_id FROM hidden_films WHERE user_id = %s);",
            (user_id,))
        films = cur.fetchall()
        cur.execute("SELECT COUNT(*) AS n FROM hidden_films WHERE user_id = %s;", (user_id,))
        hidden_count = cur.fetchone()["n"]

    if prefs.has_criteria:
        mode = "personal"
        ranked = rank_films(prefs, films)
    else:
        # Предпочтения не заданы: показываем новинки каталога (без нежелательных жанров)
        mode = "fallback"
        ranked = [dict(f, match=None) for f in films if not has_disliked(prefs, f)]
        ranked.sort(key=lambda f: (-(f.get("year") or 0), -f["id"]))

    total = len(ranked)
    items = [decorate_film(f) for f in ranked[:limit]]
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return render_template("recommendations.html", items=items, mode=mode, prefs=prefs,
                           total=total, limit=limit, page=PAGE, hidden_count=hidden_count,
                           elapsed_ms=elapsed_ms, films_total=len(films))


@rec_bp.route("/recommendations/hide/<int:film_id>", methods=["POST"])
@login_required
def hide(film_id):
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT 1 FROM films WHERE id = %s;", (film_id,))
        if cur.fetchone():
            cur.execute("INSERT INTO hidden_films (user_id, film_id) VALUES (%s, %s) "
                        "ON CONFLICT DO NOTHING;", (session["user"]["id"], film_id))
            flash("Фильм скрыт из рекомендаций. Вернуть его можно в разделе «Скрытые».", "success")
        else:
            flash("Такого фильма нет.", "error")
    return redirect(url_for("recommendations.index"))


@rec_bp.route("/recommendations/hidden")
@login_required
def hidden():
    with db_cursor() as cur:
        cur.execute(
            "SELECT f.id, f.title, f.genres, f.year, f.country, f.duration, f.poster_url "
            "FROM hidden_films h JOIN films f ON f.id = h.film_id "
            "WHERE h.user_id = %s ORDER BY h.created_at DESC;", (session["user"]["id"],))
        films = [decorate_film(f) for f in cur.fetchall()]
    return render_template("hidden.html", films=films)


@rec_bp.route("/recommendations/unhide/<int:film_id>", methods=["POST"])
@login_required
def unhide(film_id):
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM hidden_films WHERE user_id = %s AND film_id = %s;",
                    (session["user"]["id"], film_id))
    flash("Фильм снова будет появляться в рекомендациях.", "success")
    return redirect(url_for("recommendations.hidden"))
