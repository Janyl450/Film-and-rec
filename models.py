import re

import bcrypt

from database import connect_to_database, ensure_database_exists

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8
ALLOWED_ROLES = ("viewer", "author")  # admin создаётся вручную в БД


def hash_password(password: str) -> str:
    """Хеширование пароля с солью через bcrypt (п. 5.2.2 ТЗ)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def init_user_storage():
    """Создание базы (если нет) и таблицы пользователей."""
    if not ensure_database_exists():
        return False
    connection = connect_to_database()
    if not connection:
        return False
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'viewer',
            name VARCHAR(255),
            contact VARCHAR(255),
            favorite_genres TEXT,
            disliked_genres TEXT,
            year_from INTEGER,
            year_to INTEGER,
            restrictions TEXT,
            is_blocked BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    connection.commit()
    cursor.close()
    connection.close()
    return True


PROFILE_FIELDS = (
    "id, email, role, name, contact, favorite_genres, disliked_genres, "
    "year_from, year_to, restrictions, created_at"
)


def _row_to_dict(row):
    keys = [k.strip() for k in PROFILE_FIELDS.split(",")]
    return dict(zip(keys, row))


class AuthAndPreferencesModule:
    """Модуль ФТ-1.1: регистрация, авторизация и настройка предпочтений."""

    @staticmethod
    def register(email: str, password: str, name: str = None, role: str = "viewer"):
        """Регистрация учётной записи (п. 4.1.1 ТЗ). Возвращает (успех, сообщение)."""
        email = (email or "").strip().lower()
        if not EMAIL_RE.match(email):
            return False, "Введите корректный адрес электронной почты"
        if len(password or "") < MIN_PASSWORD_LEN:
            return False, f"Пароль должен содержать не менее {MIN_PASSWORD_LEN} символов"
        if role not in ALLOWED_ROLES:
            return False, "Недопустимая роль: выберите «зритель» или «автор»"

        connection = connect_to_database()
        if not connection:
            return False, "Нет соединения с базой данных"
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT 1 FROM users WHERE email = %s;", (email,))
            if cursor.fetchone():
                return False, "Эта почта уже зарегистрирована. Войдите или используйте другую почту"
            cursor.execute(
                "INSERT INTO users (email, password_hash, role, name) "
                "VALUES (%s, %s, %s, %s) RETURNING id;",
                (email, hash_password(password), role, name),
            )
            user_id = cursor.fetchone()[0]
            connection.commit()
            return True, f"Регистрация прошла успешно (ID: {user_id})"
        except Exception as error:
            connection.rollback()
            return False, f"Ошибка регистрации: {error}"
        finally:
            cursor.close()
            connection.close()

    @staticmethod
    def login(email: str, password: str):
        """Вход по почте и паролю (п. 4.1.2 ТЗ). Возвращает словарь профиля или None."""
        email = (email or "").strip().lower()
        connection = connect_to_database()
        if not connection:
            return None
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"SELECT password_hash, is_blocked, {PROFILE_FIELDS} FROM users WHERE email = %s;",
                (email,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            password_hash, is_blocked = row[0], row[1]
            if is_blocked or not check_password(password or "", password_hash):
                return None
            return _row_to_dict(row[2:])
        except Exception as error:
            print("Ошибка входа:", error)
            return None
        finally:
            cursor.close()
            connection.close()

    @staticmethod
    def get_profile(user_id: int):
        """Просмотр своего профиля (п. 4.2.1 ТЗ)."""
        connection = connect_to_database()
        if not connection:
            return None
        cursor = connection.cursor()
        try:
            cursor.execute(f"SELECT {PROFILE_FIELDS} FROM users WHERE id = %s;", (user_id,))
            row = cursor.fetchone()
            return _row_to_dict(row) if row else None
        finally:
            cursor.close()
            connection.close()

    @staticmethod
    def update_profile(user_id: int, name: str = None, contact: str = None):
        """Изменение имени и контактных данных (п. 4.2.1 ТЗ)."""
        connection = connect_to_database()
        if not connection:
            return False
        cursor = connection.cursor()
        try:
            cursor.execute(
                "UPDATE users SET name = %s, contact = %s WHERE id = %s;",
                (name, contact, user_id),
            )
            connection.commit()
            return True
        except Exception as error:
            connection.rollback()
            print("Ошибка сохранения профиля:", error)
            return False
        finally:
            cursor.close()
            connection.close()

    @staticmethod
    def change_password(user_id: int, old_password: str, new_password: str):
        """Смена пароля (п. 4.2.1 ТЗ). Возвращает (успех, сообщение)."""
        if len(new_password or "") < MIN_PASSWORD_LEN:
            return False, f"Новый пароль должен содержать не менее {MIN_PASSWORD_LEN} символов"
        connection = connect_to_database()
        if not connection:
            return False, "Нет соединения с базой данных"
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT password_hash FROM users WHERE id = %s;", (user_id,))
            row = cursor.fetchone()
            if not row or not check_password(old_password or "", row[0]):
                return False, "Текущий пароль указан неверно"
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s;",
                (hash_password(new_password), user_id),
            )
            connection.commit()
            return True, "Пароль изменён"
        except Exception as error:
            connection.rollback()
            return False, f"Ошибка смены пароля: {error}"
        finally:
            cursor.close()
            connection.close()

    @staticmethod
    def setup_preferences(user_id: int, favorite_genres: str = "", disliked_genres: str = "",
                          year_from: int = None, year_to: int = None, restrictions: str = ""):
        """Настройка кинопредпочтений: жанры, годы выпуска, ограничения (п. 4.2.1 ТЗ)."""
        if year_from and year_to and year_from > year_to:
            return False
        connection = connect_to_database()
        if not connection:
            return False
        cursor = connection.cursor()
        try:
            cursor.execute(
                "UPDATE users SET favorite_genres = %s, disliked_genres = %s, "
                "year_from = %s, year_to = %s, restrictions = %s WHERE id = %s;",
                (favorite_genres, disliked_genres, year_from, year_to, restrictions, user_id),
            )
            connection.commit()
            return True
        except Exception as error:
            connection.rollback()
            print("Ошибка сохранения предпочтений:", error)
            return False
        finally:
            cursor.close()
            connection.close()


if __name__ == "__main__":
    if init_user_storage():
        print("Модуль ФТ-1.1 успешно инициализирован.")
    else:
        print("Не удалось инициализировать модуль. Проверьте .env и запущен ли PostgreSQL.")
