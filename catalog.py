"""ФТ-2.2. Каталог фильмов: просмотр, поиск и фильтры (пп. 4.3.1 и 4.3.2 ТЗ).

Страница /catalog открыта всем, в том числе гостям.
  * поиск: по названию и актёрам;
  * фильтры: жанры (хотя бы один из выбранных), годы выпуска «от» и «до», страна;
  * постраничный вывод по 12 фильмов, чтобы страница открывалась быстро (п. 5.1.1 ТЗ).
Таблицу films эта страница только читает.
"""
import math

from flask import Blueprint, flash, render_template, request

from dbutil import db_cursor
from films import GENRES
from helpers import decorate_film

catalog_bp = Blueprint("catalog", __name__)

PAGE_SIZE = 12
MIN_YEAR, MAX_YEAR = 1888, 2100

# Название для списка и кусок SQL для сортировки. Берутся только из этого словаря,
# поэтому из адреса страницы в запрос ничего «чужого» попасть не может.
SORTS = {
    "new": ("Сначала новые в каталоге", "created_at DESC, id DESC"),
    "year": ("По году выпуска", "year DESC NULLS LAST, id DESC"),
    "title": ("По названию", "title ASC, id ASC"),
}


def _like(text):
    """Подготавливает слово для поиска: символы % и _ ищутся как обычные."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _year_arg(name, label, errors):
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    if raw.isascii() and raw.isdigit() and MIN_YEAR <= int(raw) <= MAX_YEAR:
        return int(raw)
    errors.append(f"Год «{label}» должен быть числом от {MIN_YEAR} до {MAX_YEAR}.")
    return None


def _ratings_for(film_ids):
    """Взвешенные рейтинги из rating.py (ФТ-2.3). Пока файла нет, рейтинг не показывается."""
    try:
        from rating import get_ratings_for
    except ImportError:
        return {}
    return get_ratings_for(film_ids)


@catalog_bp.route("/catalog")
def index():
    errors = []
    q = request.args.get("q", "").strip()[:100]
    genres = [g for g in GENRES if g in request.args.getlist("genre")]
    country = request.args.get("country", "").strip()[:100]
    year_from = _year_arg("year_from", "от", errors)
    year_to = _year_arg("year_to", "до", errors)
    if year_from and year_to and year_from > year_to:
        errors.append("Год «от» не может быть больше года «до». Поменяйте их местами.")
        year_from = year_to = None
    sort = request.args.get("sort", "new")
    if sort not in SORTS:
        sort = "new"
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    for message in errors:
        flash(message, "error")

    where, params = [], []
    if q:
        where.append("(title ILIKE %s OR actors ILIKE %s)")
        params += [_like(q), _like(q)]
    if genres:
        # Жанры хранятся строкой «Драма, Триллер». Режем её на части и ищем совпадение целиком:
        # так «Драма» не находит «Мелодрама».
        where.append(r"regexp_split_to_array(COALESCE(genres, ''), '\s*,\s*') && %s::text[]")
        params.append(genres)
    if country:
        where.append("country = %s")
        params.append(country)
    if year_from:
        where.append("year >= %s")
        params.append(year_from)
    if year_to:
        where.append("year <= %s")
        params.append(year_to)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM films" + where_sql + ";", params)
        total = cur.fetchone()["n"]
        pages = max(1, math.ceil(total / PAGE_SIZE))
        page = min(page, pages)
        cur.execute(
            "SELECT id, title, genres, year, country, duration, poster_url FROM films"
            + where_sql + " ORDER BY " + SORTS[sort][1] + " LIMIT %s OFFSET %s;",
            params + [PAGE_SIZE, (page - 1) * PAGE_SIZE])
        rows = cur.fetchall()
        cur.execute("SELECT DISTINCT country FROM films "
                    "WHERE country IS NOT NULL AND country <> '' ORDER BY country;")
        countries = [r["country"] for r in cur.fetchall()]

    ratings = _ratings_for([r["id"] for r in rows])
    items = []
    for row in rows:
        film = decorate_film(row)
        film["rating_info"] = ratings.get(film["id"])
        items.append(film)

    # Параметры для ссылок «Назад» и «Дальше»: фильтры сохраняются при переходе по страницам
    args = {"q": q, "genre": genres, "country": country, "year_from": year_from,
            "year_to": year_to, "sort": sort if sort != "new" else ""}
    args = {key: value for key, value in args.items() if value}

    return render_template(
        "catalog/index.html", items=items, total=total, page=page, pages=pages, args=args,
        genres=GENRES, countries=countries, sorts=SORTS,
        form={"q": q, "genre": genres, "country": country, "sort": sort,
              "year_from": year_from or "", "year_to": year_to or ""},
        filtered=bool(where))
