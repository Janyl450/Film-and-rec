import os

import psycopg2
from psycopg2 import Error
from dotenv import load_dotenv

# Читаем настройки из файла .env (он не попадает в git)
load_dotenv()


def _settings(dbname=None):
    return {
        "dbname": dbname or os.getenv("DB_NAME", "kinorekomend_db"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": os.getenv("DB_PORT", "5432"),
    }


def connect_to_database():
    """Подключение к базе данных PostgreSQL для веб-системы КиноРекоменд."""
    try:
        return psycopg2.connect(**_settings())
    except (Exception, Error) as error:
        print("Ошибка подключения к PostgreSQL:", error)
        return None


def ensure_database_exists():
    """Создаёт базу kinorekomend_db, если её ещё нет."""
    name = os.getenv("DB_NAME", "kinorekomend_db")
    try:
        conn = psycopg2.connect(**_settings(dbname="postgres"))
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (name,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{name}";')
            print(f"База данных {name} создана.")
        cur.close()
        conn.close()
        return True
    except (Exception, Error) as error:
        print("Не удалось создать базу данных:", error)
        return False
