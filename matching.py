"""Расчёт процента совпадения фильма с предпочтениями пользователя.

ФТ-1.2, п. 4.3.3 ТЗ: «сопоставлять параметры фильмов с личными предпочтениями пользователя,
рассчитывать процент совпадения и выводить ранжированный список с пояснениями».

Как считаем:
  * жанры (вес 70%): доля жанров фильма, которые есть среди любимых;
  * годы выпуска (вес 30%): 100%, если год в выбранном диапазоне, дальше падает до 0% за 15 лет;
  * если задано только что-то одно, оно получает все 100%;
  * фильм с нежелательным жанром в подборку не попадает.
"""
from dataclasses import dataclass, field

GENRE_WEIGHT = 70
YEAR_WEIGHT = 30
YEAR_FADE = 15  # за сколько лет оценка года падает от 100% до 0%


def split_genres(value):
    """'Драма, Триллер' -> ['Драма', 'Триллер']"""
    return [g.strip() for g in (value or "").split(",") if g.strip()]


@dataclass
class Prefs:
    favorite: list = field(default_factory=list)
    disliked: list = field(default_factory=list)
    year_from: int = None
    year_to: int = None

    @property
    def has_years(self):
        return bool(self.year_from or self.year_to)

    @property
    def has_criteria(self):
        """Есть ли по чему считать процент."""
        return bool(self.favorite or self.has_years)

    def year_text(self):
        if self.year_from and self.year_to:
            return f"{self.year_from}–{self.year_to}"
        if self.year_from:
            return f"с {self.year_from}"
        if self.year_to:
            return f"до {self.year_to}"
        return ""


def prefs_from_user(row):
    """row — словарь из таблицы users."""
    row = row or {}
    return Prefs(
        favorite=split_genres(row.get("favorite_genres")),
        disliked=split_genres(row.get("disliked_genres")),
        year_from=row.get("year_from"),
        year_to=row.get("year_to"),
    )


def has_disliked(prefs, film):
    film_genres = {g.lower() for g in split_genres(film.get("genres"))}
    return any(g.lower() in film_genres for g in prefs.disliked)


def score_film(prefs, film):
    """Возвращает словарь {percent, parts, reasons} или None, если фильм исключён."""
    film_genres = split_genres(film.get("genres"))
    if has_disliked(prefs, film):
        return None

    use_genres = bool(prefs.favorite)
    use_years = prefs.has_years
    if not (use_genres or use_years):
        return {"percent": 0, "parts": [], "reasons": []}

    genre_w = (GENRE_WEIGHT if use_years else 100) if use_genres else 0
    year_w = (YEAR_WEIGHT if use_genres else 100) if use_years else 0

    parts, reasons = [], []

    if use_genres:
        fav = {g.lower() for g in prefs.favorite}
        hits = [g for g in film_genres if g.lower() in fav]
        s = len(hits) / len(film_genres) if film_genres else 0.0
        reason = ("Совпали жанры: " + ", ".join(hits)) if hits else "Жанры фильма не совпали с любимыми"
        parts.append({"name": "Жанры", "weight": genre_w, "percent": round(s * 100), "score": s})
        reasons.append(reason)

    if use_years:
        year = film.get("year")
        lo = prefs.year_from if prefs.year_from else None
        hi = prefs.year_to if prefs.year_to else None
        if year is None:
            s, reason = 0.0, "Год выпуска фильма не указан"
        elif (lo is None or year >= lo) and (hi is None or year <= hi):
            s, reason = 1.0, f"Год выпуска {year} входит в ваш диапазон {prefs.year_text()}"
        else:
            dist = (lo - year) if (lo is not None and year < lo) else (year - hi)
            s = max(0.0, 1 - dist / YEAR_FADE)
            reason = f"Год выпуска {year} вне диапазона {prefs.year_text()} (на {dist} л.)"
        parts.append({"name": "Годы выпуска", "weight": year_w, "percent": round(s * 100), "score": s})
        reasons.append(reason)

    if prefs.disliked:
        reasons.append("Нет нежелательных жанров")

    total = sum(p["weight"] * p["score"] for p in parts) / sum(p["weight"] for p in parts)
    return {"percent": round(total * 100), "parts": parts, "reasons": reasons}


def rank_films(prefs, films, limit=None):
    """Возвращает отсортированный список фильмов с полями match (результат score_film)."""
    ranked = []
    for film in films:
        result = score_film(prefs, film)
        if result is None:
            continue
        item = dict(film)
        item["match"] = result
        ranked.append(item)
    ranked.sort(key=lambda f: (-f["match"]["percent"], -(f.get("year") or 0), f.get("title") or ""))
    return ranked[:limit] if limit else ranked
