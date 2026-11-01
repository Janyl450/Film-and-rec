"""Общие мелочи для страниц подбора, отзывов и админки."""
import os
from functools import wraps

from flask import current_app, flash, redirect, render_template, session, url_for


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Войдите в аккаунт, чтобы открыть эту страницу.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def forbidden(text="У вас нет доступа к этой странице."):
    return render_template("error.html", code=403, text=text), 403


def admin_required(view):
    """Только администратор. Роль берётся из базы при каждом запросе (см. features.py)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Войдите в аккаунт, чтобы открыть эту страницу.", "error")
            return redirect(url_for("login"))
        if session["user"].get("role") != "admin":
            return forbidden("Эта страница доступна только администратору.")
        return view(*args, **kwargs)
    return wrapper


def safe_url(value):
    """Ссылку показываем как ссылку, только если она начинается с http(s)://"""
    value = (value or "").strip()
    return value if value.lower().startswith(("http://", "https://")) else None


def hue_for(text):
    """Цвет заглушки постера: одинаковый для одного названия."""
    return sum(ord(c) for c in (text or "?")) * 7 % 360


def film_meta(film):
    parts = []
    if film.get("year"):
        parts.append(str(film["year"]))
    if film.get("country"):
        parts.append(film["country"])
    if film.get("duration"):
        parts.append(f"{film['duration']} мин")
    return " · ".join(parts)


def decorate_film(film):
    """Добавляет к строке фильма поля для шаблонов."""
    from matching import split_genres
    film["genre_list"] = split_genres(film.get("genres"))
    film["meta"] = film_meta(film)
    film["hue"] = hue_for(film.get("title"))
    film["poster_url"] = safe_url(film.get("poster_url"))
    return film


def video_url_for(film_id):
    """Если Жанылай загрузила видео (static/videos/<id>.mp4), даём ссылку на него."""
    path = os.path.join(current_app.static_folder, "videos", f"{film_id}.mp4")
    if os.path.isfile(path):
        return url_for("static", filename=f"videos/{film_id}.mp4")
    return None


def fmt_dt(value):
    return value.strftime("%d.%m.%Y %H:%M") if value else ""
