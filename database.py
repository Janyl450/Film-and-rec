import psycopg2
from psycopg2 import Error

def connect_to_database():
    """Подключение к базе данных PostgreSQL для веб-системы КиноРекоменд."""
    try:
        connection = psycopg2.connect(
            dbname="kinorekomend_db",
            user="postgres",
            password="ваш_пароль",  # Укажите ваш реальный пароль от PostgreSQL
            host="127.0.0.1",
            port="5432"
        )
        return connection
    except (Exception, Error) as error:
        print("Ошибка подключения к PostgreSQL:", error)
        return None