"""Быстрая проверка ФТ-1.1. Запуск: python test_auth.py"""
import uuid

from database import connect_to_database
from models import AuthAndPreferencesModule as Auth, init_user_storage

assert init_user_storage(), "Не удалось инициализировать БД — проверьте .env"

email = f"test_{uuid.uuid4().hex[:8]}@example.com"
pwd = "secret123"

ok, msg = Auth.register(email, pwd, name="Тест")
assert ok, msg
print("1. Регистрация:", msg)

ok, msg = Auth.register(email, pwd)
assert not ok
print("2. Повторная почта отклонена:", msg)

ok, msg = Auth.register("не-почта", pwd)
assert not ok
print("3. Неверная почта отклонена:", msg)

ok, msg = Auth.register("short@example.com", "123")
assert not ok
print("4. Короткий пароль отклонён:", msg)

assert Auth.login(email, "неверный") is None
print("5. Вход с неверным паролем отклонён")

user = Auth.login(email, pwd)
assert user and user["email"] == email
print("6. Вход выполнен, роль:", user["role"])

assert Auth.setup_preferences(user["id"], "Драма, Триллер", "Ужасы", 1990, 2020, "16+")
profile = Auth.get_profile(user["id"])
assert profile["favorite_genres"] == "Драма, Триллер" and profile["year_from"] == 1990
print("7. Предпочтения сохранены:", profile["favorite_genres"], profile["year_from"], "-", profile["year_to"])

assert Auth.update_profile(user["id"], "Новое имя", "+996 700 000 000")
ok, msg = Auth.change_password(user["id"], pwd, "newsecret456")
assert ok, msg
assert Auth.login(email, "newsecret456")
print("8. Профиль и пароль изменены")

# уборка тестового пользователя
conn = connect_to_database()
cur = conn.cursor()
cur.execute("DELETE FROM users WHERE email = %s;", (email,))
conn.commit()
cur.close()
conn.close()
print("\nВсе проверки ФТ-1.1 пройдены ✔")
