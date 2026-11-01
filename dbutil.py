"""Небольшой помощник для работы с базой: курсор, который сам закрывает соединение."""
from contextlib import contextmanager

from psycopg2.extras import RealDictCursor

from database import connect_to_database


@contextmanager
def db_cursor(commit=False):
    """with db_cursor(commit=True) as cur: ...  — строки приходят как словари."""
    conn = connect_to_database()
    if conn is None:
        raise RuntimeError("Нет соединения с базой данных")
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
