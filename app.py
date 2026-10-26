"""Веб-приложение «КиноРекоменд». ФТ-1.1: регистрация, вход, профиль и предпочтения.

Запуск:  python app.py   →  http://127.0.0.1:5000
"""
import os
import secrets
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)

from models import AuthAndPreferencesModule as Auth, init_user_storage
from films import films_bp

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.register_blueprint(films_bp)

GENRES = [
    "Драма", "Комедия", "Триллер", "Боевик", "Фантастика", "Фэнтези",
    "Ужасы", "Детектив", "Мелодрама", "Приключения", "Анимация",
    "Криминал", "Исторический", "Документальный",
]
AGE_LIMITS = ["", "6+", "12+", "16+", "18+"]
ROLE_TITLES = {"viewer": "Зритель", "author": "Автор", "admin": "Администратор"}


# ---------- служебное ----------
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Войдите в аккаунт, чтобы открыть эту страницу.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


@app.before_request
def csrf_protect():
    """Защита форм от подделки запросов."""
    if request.method == "POST":
        token = session.get("_csrf")
        if not token or token != request.form.get("_csrf"):
            abort(400)


@app.context_processor
def inject_globals():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return {
        "csrf_token": session["_csrf"],
        "current_user": session.get("user"),
        "ROLE_TITLES": ROLE_TITLES,
    }


@app.errorhandler(400)
def bad_request(_):
    return render_template("error.html", code=400,
                           text="Форма устарела. Обновите страницу и попробуйте ещё раз."), 400


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, text="Такой страницы нет."), 404


def split_genres(value):
    return [g.strip() for g in (value or "").split(",") if g.strip()]


def to_year(value):
    value = (value or "").strip()
    if not value:
        return None
    if not value.isdigit() or not (1888 <= int(value) <= 2100):
        raise ValueError
    return int(value)


# ---------- страницы ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user" in session:
        return redirect(url_for("profile"))
    form = {}
    if request.method == "POST":
        form = request.form
        email = form.get("email", "")
        password = form.get("password", "")
        if password != form.get("password2", ""):
            flash("Пароли не совпадают.", "error")
        else:
            ok, message = Auth.register(email, password, form.get("name", "").strip() or None,
                                        form.get("role", "viewer"))
            if ok:
                flash("Регистрация прошла успешно. Теперь войдите в аккаунт.", "success")
                return redirect(url_for("login"))
            flash(message, "error")
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("profile"))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "")
        user = Auth.login(email, request.form.get("password", ""))
        if user:
            session.clear()
            session["user"] = {"id": user["id"], "email": user["email"],
                               "name": user["name"], "role": user["role"]}
            flash("Добро пожаловать!", "success")
            return redirect(url_for("profile"))
        flash("Неверная почта или пароль. Проверьте данные и попробуйте снова.", "error")
    return render_template("login.html", email=email)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Вы вышли из аккаунта.", "success")
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = session["user"]["id"]

    if request.method == "POST":
        action = request.form.get("action")

        if action == "info":
            name = request.form.get("name", "").strip() or None
            contact = request.form.get("contact", "").strip() or None
            if Auth.update_profile(user_id, name, contact):
                session["user"]["name"] = name
                session.modified = True
                flash("Личные данные сохранены.", "success")
            else:
                flash("Не удалось сохранить данные. Попробуйте позже.", "error")

        elif action == "prefs":
            favorite = [g for g in request.form.getlist("favorite") if g in GENRES]
            disliked = [g for g in request.form.getlist("disliked") if g in GENRES]
            both = set(favorite) & set(disliked)
            try:
                year_from = to_year(request.form.get("year_from"))
                year_to = to_year(request.form.get("year_to"))
            except ValueError:
                flash("Годы выпуска должны быть числами от 1888 до 2100.", "error")
                return redirect(url_for("profile") + "#prefs")
            restriction = request.form.get("restrictions", "")
            if restriction not in AGE_LIMITS:
                restriction = ""
            if both:
                flash("Жанр не может быть и любимым, и нежелательным: " + ", ".join(sorted(both)), "error")
            elif year_from and year_to and year_from > year_to:
                flash("Год «от» не может быть больше года «до».", "error")
            elif Auth.setup_preferences(user_id, ", ".join(favorite), ", ".join(disliked),
                                        year_from, year_to, restriction):
                flash("Предпочтения сохранены. Скоро по ним появятся рекомендации.", "success")
            else:
                flash("Не удалось сохранить предпочтения.", "error")
            return redirect(url_for("profile") + "#prefs")

        elif action == "password":
            if request.form.get("new_password") != request.form.get("new_password2"):
                flash("Новые пароли не совпадают.", "error")
            else:
                ok, message = Auth.change_password(user_id, request.form.get("old_password", ""),
                                                   request.form.get("new_password", ""))
                flash(message, "success" if ok else "error")
            return redirect(url_for("profile") + "#password")

        return redirect(url_for("profile"))

    data = Auth.get_profile(user_id)
    if not data:
        session.clear()
        return redirect(url_for("login"))
    return render_template(
        "profile.html", p=data, genres=GENRES, age_limits=AGE_LIMITS,
        favorite=split_genres(data["favorite_genres"]),
        disliked=split_genres(data["disliked_genres"]),
    )


if __name__ == "__main__":
    if init_user_storage():
        app.run(debug=True)
    else:
        print("Не удалось подключиться к базе. Проверьте .env и запущен ли PostgreSQL.")
