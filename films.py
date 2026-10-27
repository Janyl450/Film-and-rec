"""ФТ-2.1. Добавление и управление карточкой фильма (роль «Автор»).

Страницы:
  /films/my              — список «Мои фильмы»
  /films/new             — форма «Добавить фильм»
  /films/<id>/edit       — изменение своей карточки
"""
import os
from functools import wraps

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, session, url_for)

from database import connect_to_database

films_bp = Blueprint("films", __name__)

# Этот список должен совпадать с GENRES в app.py буква в букву.
# Из app.py его не импортируем, чтобы не было циклического импорта.
GENRES = [
    "Драма", "Комедия", "Триллер", "Боевик", "Фантастика", "Фэнтези",
    "Ужасы", "Детектив", "Мелодрама", "Приключения", "Анимация",
    "Криминал", "Исторический", "Документальный",
]

MIN_YEAR, MAX_YEAR = 1888, 2100
MAX_DURATION = 10000  # минут, защита от случайных опечаток
MAX_VIDEO_BYTES = 500 * 1024 * 1024  # видео не больше 500 МБ

FILM_FIELDS = (
    "id, title, genres, year, country, director, actors, duration, "
    "description, trailer_url, poster_url, author_id, created_at"
)


# ---------- база данных ----------
def _row_to_dict(row):
    keys = [k.strip() for k in FILM_FIELDS.split(",")]
    return dict(zip(keys, row))


def init_films_storage():
    """Создаёт таблицу films, если её ещё нет. Таблицу users не трогает."""
    connection = connect_to_database()
    if not connection:
        return False
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS films (
                id SERIAL PRIMARY KEY,
                title VARCHAR NOT NULL,
                genres TEXT,
                year INTEGER,
                country VARCHAR,
                director VARCHAR,
                actors TEXT,
                duration INTEGER,
                description TEXT,
                trailer_url VARCHAR,
                poster_url VARCHAR,
                author_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.commit()
        return True
    except Exception as error:
        connection.rollback()
        print("Ошибка создания таблицы films:", error)
        return False
    finally:
        cursor.close()
        connection.close()


def _values(data):
    return (data["title"], data["genres"], data["year"], data["country"],
            data["director"], data["actors"], data["duration"],
            data["description"], data["trailer_url"], data["poster_url"])


def create_film(author_id, data):
    """Добавляет фильм. Возвращает id нового фильма или None при ошибке."""
    connection = connect_to_database()
    if not connection:
        return None
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO films (title, genres, year, country, director, actors, "
            "duration, description, trailer_url, poster_url, author_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;",
            _values(data) + (author_id,),
        )
        film_id = cursor.fetchone()[0]
        connection.commit()
        return film_id
    except Exception as error:
        connection.rollback()
        print("Ошибка добавления фильма:", error)
        return None
    finally:
        cursor.close()
        connection.close()


def get_film(film_id):
    """Возвращает фильм словарём или None, если его нет."""
    connection = connect_to_database()
    if not connection:
        return None
    cursor = connection.cursor()
    try:
        cursor.execute(f"SELECT {FILM_FIELDS} FROM films WHERE id = %s;", (film_id,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    except Exception as error:
        print("Ошибка чтения фильма:", error)
        return None
    finally:
        cursor.close()
        connection.close()


def list_films_by_author(author_id):
    """Фильмы автора, новые сверху. При ошибке базы возвращает None."""
    connection = connect_to_database()
    if not connection:
        return None
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"SELECT {FILM_FIELDS} FROM films WHERE author_id = %s "
            "ORDER BY created_at DESC, id DESC;",
            (author_id,),
        )
        return [_row_to_dict(row) for row in cursor.fetchall()]
    except Exception as error:
        print("Ошибка чтения списка фильмов:", error)
        return None
    finally:
        cursor.close()
        connection.close()


def update_film(film_id, author_id, data):
    """Изменяет фильм, только если он принадлежит этому автору."""
    connection = connect_to_database()
    if not connection:
        return False
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE films SET title = %s, genres = %s, year = %s, country = %s, "
            "director = %s, actors = %s, duration = %s, description = %s, "
            "trailer_url = %s, poster_url = %s WHERE id = %s AND author_id = %s;",
            _values(data) + (film_id, author_id),
        )
        changed = cursor.rowcount == 1
        connection.commit()
        return changed
    except Exception as error:
        connection.rollback()
        print("Ошибка изменения фильма:", error)
        return False
    finally:
        cursor.close()
        connection.close()


# ---------- проверка данных формы ----------
def _to_int(raw, low, high):
    raw = raw.strip()
    if raw.isascii() and raw.isdigit():
        number = int(raw)
        if low <= number <= high:
            return number
    return None


def _text(form, name, limit, label, errors):
    value = form.get(name, "").strip()
    if len(value) > limit:
        errors.append(f"Поле «{label}» слишком длинное: не больше {limit} символов. Сократите текст.")
    return value or None


def _url(form, name, label, errors):
    value = form.get(name, "").strip()
    if not value:
        return None
    if (not value.lower().startswith(("http://", "https://"))
            or " " in value or len(value) > 500):
        errors.append(f"{label} должна начинаться с http:// или https://. "
                      "Скопируйте адрес целиком из браузера.")
    return value


def validate_film_form(form):
    """Проверяет форму. Возвращает (данные, список_ошибок)."""
    errors = []

    title = form.get("title", "").strip()
    if not title:
        errors.append("Укажите название фильма.")
    elif len(title) > 255:
        errors.append("Название слишком длинное: не больше 255 символов.")

    chosen = form.getlist("genres")
    genres = [g for g in GENRES if g in chosen]

    year = None
    year_raw = form.get("year", "").strip()
    if year_raw:
        year = _to_int(year_raw, MIN_YEAR, MAX_YEAR)
        if year is None:
            errors.append(f"Год выпуска должен быть числом от {MIN_YEAR} до {MAX_YEAR}.")

    duration = None
    duration_raw = form.get("duration", "").strip()
    if duration_raw:
        duration = _to_int(duration_raw, 1, MAX_DURATION)
        if duration is None:
            errors.append("Длительность должна быть положительным числом минут, например 120.")

    data = {
        "title": title,
        "genres": ", ".join(genres) or None,
        "year": year,
        "country": _text(form, "country", 255, "Страна", errors),
        "director": _text(form, "director", 255, "Режиссёр", errors),
        "actors": _text(form, "actors", 2000, "Актёрский состав", errors),
        "duration": duration,
        "description": _text(form, "description", 5000, "Описание", errors),
        "trailer_url": _url(form, "trailer_url", "Ссылка на трейлер", errors),
        "poster_url": _url(form, "poster_url", "Ссылка на постер", errors),
    }
    return data, errors


# ---------- видеофайл фильма ----------
# Видео лежит в папке static/videos/<номер фильма>.mp4.
# В таблицу films ничего не добавляется: страница сама проверяет, есть ли файл.
def _video_paths(film_id):
    folder = os.path.join(current_app.static_folder, "videos")
    return folder, os.path.join(folder, f"{film_id}.mp4")


def film_has_video(film_id):
    return os.path.isfile(_video_paths(film_id)[1])


def check_video(file):
    """Проверяет загруженный файл. Возвращает текст ошибки или None."""
    if not file or not file.filename:
        return None  # видео не выбрано — это нормально
    if not file.filename.lower().endswith(".mp4"):
        return "Видео должно быть в формате MP4. Выберите файл с расширением .mp4."
    head = file.stream.read(12)
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if head[4:8] != b"ftyp":
        return "Этот файл не похож на видео MP4. Выберите другой файл."
    if size > MAX_VIDEO_BYTES:
        return "Видео слишком большое: не больше 500 МБ. Возьмите короткий ролик."
    return None


def _store_video(film_id, file):
    """Сохраняет видео, если оно выбрано. Возвращает False при ошибке записи."""
    if not file or not file.filename:
        return True
    try:
        folder, path = _video_paths(film_id)
        os.makedirs(folder, exist_ok=True)
        file.save(path)
        return True
    except OSError as error:
        print("Ошибка сохранения видео:", error)
        return False


@films_bp.record_once
def _set_upload_limit(state):
    # запас на остальные поля формы
    state.app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_BYTES + 5 * 1024 * 1024


@films_bp.app_errorhandler(413)
def file_too_large(_):
    return render_template("error.html", code=413,
                           text="Файл слишком большой. Загрузите видео не больше 500 МБ."), 413


# ---------- права доступа ----------
def author_required(view):
    """Пускает только вошедшего пользователя с ролью «автор»."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = session.get("user")
        if not user:
            flash("Войдите в аккаунт, чтобы открыть эту страницу.", "error")
            return redirect(url_for("login"))
        if user.get("role") != "author":
            flash("Добавлять и изменять фильмы могут только авторы. "
                  "Зарегистрируйтесь с ролью «Автор».", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


# ---------- вспомогательное для страниц ----------
def _split_genres(value):
    return [g.strip() for g in (value or "").split(",") if g.strip()]


def _film_meta(film):
    parts = []
    if film["year"]:
        parts.append(str(film["year"]))
    if film["country"]:
        parts.append(film["country"])
    if film["duration"]:
        parts.append(f"{film['duration']} мин")
    return " · ".join(parts)


def _film_to_form(film):
    """Превращает фильм из базы в значения для полей формы."""
    return {key: ("" if film[key] is None else str(film[key]))
            for key in ("title", "year", "country", "director", "actors",
                        "duration", "description", "trailer_url", "poster_url")}


def _render_form(form, selected, film_id=None):
    return render_template("films/form.html", form=form, selected=selected,
                           genres=GENRES, film_id=film_id,
                           has_video=bool(film_id) and film_has_video(film_id))


def _load_own_film(film_id):
    """Возвращает (фильм, None) или (None, редирект с сообщением)."""
    film = get_film(film_id)
    if film is None:
        flash("Такой карточки нет. Выберите фильм из списка.", "error")
        return None, redirect(url_for("films.my_films"))
    if film["author_id"] != session["user"]["id"]:
        flash("Эту карточку создал другой автор. Выберите свой фильм из списка.", "error")
        return None, redirect(url_for("films.my_films"))
    return film, None


# Таблица films создаётся при первом открытии любой страницы сайта
# (к этому моменту app.py уже создал базу и таблицу users).
_storage_ready = False


@films_bp.before_app_request
def ensure_films_storage():
    global _storage_ready
    if not _storage_ready:
        _storage_ready = init_films_storage()


# ---------- страницы ----------
@films_bp.route("/films/my")
@author_required
def my_films():
    films = list_films_by_author(session["user"]["id"])
    if films is None:
        flash("Не удалось загрузить фильмы. Проверьте, что PostgreSQL запущен, "
              "и обновите страницу.", "error")
        films = []
    for film in films:
        film["genre_list"] = _split_genres(film["genres"])
        film["meta"] = _film_meta(film)
    return render_template("films/my_films.html", films=films)


@films_bp.route("/films/<int:film_id>")
@author_required
def view_film(film_id):
    film, redirect_response = _load_own_film(film_id)
    if redirect_response:
        return redirect_response
    film["genre_list"] = _split_genres(film["genres"])
    film["meta"] = _film_meta(film)
    video_url = None
    if film_has_video(film_id):
        video_url = url_for("static", filename=f"videos/{film_id}.mp4")
    return render_template("films/view.html", film=film, video_url=video_url)


@films_bp.route("/films/new", methods=["GET", "POST"])
@author_required
def add_film():
    if request.method == "POST":
        data, errors = validate_film_form(request.form)
        video = request.files.get("video")
        video_error = check_video(video)
        if video_error:
            errors.append(video_error)
        if errors:
            for message in errors:
                flash(message, "error")
        else:
            film_id = create_film(session["user"]["id"], data)
            if film_id:
                flash(f"Фильм «{data['title']}» добавлен.", "success")
                if not _store_video(film_id, video):
                    flash("Карточка сохранена, но видео загрузить не удалось. "
                          "Откройте «Изменить» и попробуйте ещё раз.", "error")
                return redirect(url_for("films.my_films"))
            flash("Не удалось сохранить фильм. Проверьте, что PostgreSQL запущен, "
                  "и попробуйте ещё раз.", "error")
        return _render_form(request.form, request.form.getlist("genres"))
    return _render_form({}, [])


@films_bp.route("/films/<int:film_id>/edit", methods=["GET", "POST"])
@author_required
def edit_film(film_id):
    film, redirect_response = _load_own_film(film_id)
    if redirect_response:
        return redirect_response

    if request.method == "POST":
        data, errors = validate_film_form(request.form)
        video = request.files.get("video")
        video_error = check_video(video)
        if video_error:
            errors.append(video_error)
        if errors:
            for message in errors:
                flash(message, "error")
        elif update_film(film_id, session["user"]["id"], data):
            flash(f"Изменения в фильме «{data['title']}» сохранены.", "success")
            if not _store_video(film_id, video):
                flash("Данные сохранены, но видео загрузить не удалось. "
                      "Попробуйте ещё раз.", "error")
            return redirect(url_for("films.my_films"))
        else:
            flash("Не удалось сохранить изменения. Попробуйте ещё раз.", "error")
        return _render_form(request.form, request.form.getlist("genres"), film_id)

    return _render_form(_film_to_form(film), _split_genres(film["genres"]), film_id)
