"""ФТ-2.3. Расчёт взвешенного рейтинга фильмов (п. 4.6.2 и 5.1.2 ТЗ).

Формула (как у IMDb):   R = v / (v + m) * A + m / (v + m) * C
    A — средний балл фильма по одобренным отзывам (overall_score),
    v — число одобренных отзывов фильма,
    m — минимальный порог числа отзывов (MIN_VOTES),
    C — средний балл по всем одобренным отзывам сайта.

Смысл: у фильма с одной оценкой «10» рейтинг остаётся близким к среднему по сайту и
подходит к реальному среднему только по мере появления отзывов. Случайные завышения
и занижения рейтинг не ломают (п. 4.6.2).

Отзывы со статусом «pending» (на проверке) в расчёт не входят — подозрительные оценки
временно не влияют на рейтинг (п. 4.6.1). Рейтинг считается при каждом открытии страницы,
поэтому после одобрения отзыва он обновляется мгновенно (п. 5.1.2).

Как пользоваться:
    from rating import ratings_for, film_rating
    film_rating(film_id)           -> {"value": 7.4, "votes": 12, "average": 7.9}
    ratings_for([id1, id2, ...])   -> {id1: {...}, id2: {...}}   (одним запросом)
value = None, если у фильма ещё нет одобренных отзывов.
"""
from dbutil import db_cursor

MIN_VOTES = 5  # порог m: сколько отзывов нужно, чтобы фильм «перевесил» среднее по сайту

# Куски SQL: пригодятся для каталога (ФТ-2.2), чтобы сортировать по рейтингу.
# Запрос: RATING_CTE + "SELECT f.*, " + RATING_COLUMNS + " FROM films f " + RATING_JOIN
RATING_CTE = """
WITH stats AS (
    SELECT film_id, COUNT(*) AS votes, AVG(overall_score) AS avg_score
    FROM reviews WHERE status = 'approved' GROUP BY film_id
), g AS (
    SELECT COALESCE(AVG(overall_score), 0) AS c FROM reviews WHERE status = 'approved'
)
"""
RATING_JOIN = "LEFT JOIN stats s ON s.film_id = f.id CROSS JOIN g"
RATING_COLUMNS = f"""
    COALESCE(s.votes, 0) AS votes, s.avg_score AS average,
    CASE WHEN s.votes IS NULL THEN NULL
         ELSE ROUND((s.votes::numeric / (s.votes + {MIN_VOTES})) * s.avg_score
                    + ({MIN_VOTES}::numeric / (s.votes + {MIN_VOTES})) * g.c, 1)
    END AS value
"""


def weighted_rating(average, votes, global_average, min_votes=MIN_VOTES):
    """Формула на чистом Python. None, если одобренных отзывов нет."""
    if not votes or average is None:
        return None
    v, m = float(votes), float(min_votes)
    return round(v / (v + m) * float(average) + m / (v + m) * float(global_average), 1)


def _clean(row):
    return {"value": None if row["value"] is None else float(row["value"]),
            "votes": int(row["votes"]),
            "average": None if row["average"] is None else round(float(row["average"]), 1)}


def ratings_for(film_ids):
    """Рейтинги нескольких фильмов одним запросом. Ключ — id фильма.
    Для фильма без отзывов вернётся {"value": None, "votes": 0, "average": None}."""
    ids = list(film_ids)
    result = {i: {"value": None, "votes": 0, "average": None} for i in ids}
    if not ids:
        return result
    with db_cursor() as cur:
        cur.execute(f"{RATING_CTE} SELECT f.id, {RATING_COLUMNS} "
                    f"FROM films f {RATING_JOIN} WHERE f.id = ANY(%s);", (ids,))
        for row in cur.fetchall():
            result[row["id"]] = _clean(row)
    return result


def film_rating(film_id):
    """Рейтинг одного фильма."""
    return ratings_for([film_id])[film_id]
