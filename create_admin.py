"""Создаёт администратора (или делает им существующего пользователя).

Запуск:  python create_admin.py почта пароль
Пример:  python create_admin.py admin@example.com Admin12345
"""
import sys

from dbutil import db_cursor
from models import EMAIL_RE, MIN_PASSWORD_LEN, hash_password, init_user_storage


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    email, password = sys.argv[1].strip().lower(), sys.argv[2]
    if not EMAIL_RE.match(email):
        print("Некорректная почта.")
        return 1
    if len(password) < MIN_PASSWORD_LEN:
        print(f"Пароль должен содержать не менее {MIN_PASSWORD_LEN} символов.")
        return 1
    if not init_user_storage():
        print("Не удалось подключиться к базе. Проверьте .env и запущен ли PostgreSQL.")
        return 1
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT id FROM users WHERE email = %s;", (email,))
        if cur.fetchone():
            cur.execute("UPDATE users SET role = 'admin', is_blocked = FALSE, password_hash = %s "
                        "WHERE email = %s;", (hash_password(password), email))
            print(f"Пользователь {email} стал администратором (пароль обновлён).")
        else:
            cur.execute("INSERT INTO users (email, password_hash, role, name) VALUES (%s, %s, 'admin', 'Администратор');",
                        (email, hash_password(password)))
            print(f"Администратор {email} создан.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
