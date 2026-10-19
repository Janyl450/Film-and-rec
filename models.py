import hashlib
from database import connect_to_database

def hash_password(password: str) -> str:
    """Безопасное хеширование пароля (требование безопасности ТЗ)."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_user_storage():
    """Инициализация хранилища пользователей."""
    connection = connect_to_database()
    if connection:
        cursor = connection.cursor()
        create_table_query = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) DEFAULT 'viewer',
            favorite_genres TEXT,
            disliked_genres TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_query)
        connection.commit()
        cursor.close()
        connection.close()

class AuthAndPreferencesModule:
    """Модуль ФТ-1.1: Регистрация, авторизация и настройка предпочтений."""

    @staticmethod
    def register(email: str, password: str):
        """Регистрация учетной записи пользователя (п. 4.1.1 ТЗ)."""
        connection = connect_to_database()
        if not connection:
            return False, "Нет соединения с базой данных"
        
        cursor = connection.cursor()
        try:
            pwd_hash = hash_password(password)
            query = "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id;"
            cursor.execute(query, (email, pwd_hash))
            user_id = cursor.fetchone()[0]
            connection.commit()
            return True, f"Успешная регистрация пользователя ID: {user_id}"
        except Exception as error:
            return False, f"Ошибка регистрации (возможно, почта уже занята): {error}"
        finally:
            cursor.close()
            connection.close()

    @staticmethod
    def login(email: str, password: str):
        """Вход пользователя в систему по почте и паролю (п. 4.1.2 ТЗ)."""
        connection = connect_to_database()
        if not connection:
            return None
        
        cursor = connection.cursor()
        try:
            pwd_hash = hash_password(password)
            query = "SELECT id, email, role, favorite_genres FROM users WHERE email = %s AND password_hash = %s;"
            cursor.execute(query, (email, pwd_hash))
            user_data = cursor.fetchone()
            return user_data
        except Exception as error:
            print("Ошибка входа:", error)
            return None
        finally:
            cursor.close()
            connection.close()

    @staticmethod
    def setup_preferences(email: str, favorite_genres: str, disliked_genres: str):
        """Настройка кинопредпочтений пользователя (п. 4.2.1 ТЗ)."""
        connection = connect_to_database()
        if not connection:
            return False
        
        cursor = connection.cursor()
        try:
            query = "UPDATE users SET favorite_genres = %s, disliked_genres = %s WHERE email = %s;"
            cursor.execute(query, (favorite_genres, disliked_genres, email))
            connection.commit()
            return True
        except Exception as error:
            print("Ошибка сохранения предпочтений:", error)
            return False
        finally:
            cursor.close()
            connection.close()

if __name__ == "__main__":
    init_user_storage()
    print("Модуль ФТ-1.1 успешно инициализирован.")