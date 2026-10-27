"""Проверка ФТ-2.1: создание, чтение и изменение фильма.

Запуск:  python test_films.py
Нужно, чтобы PostgreSQL был запущен, а в .env был верный пароль.
Скрипт создаёт тестового автора и фильм, а в конце удаляет их.
"""
import io
import uuid

from werkzeug.datastructures import FileStorage, MultiDict

from database import connect_to_database
from films import (check_video, create_film, get_film, init_films_storage,
                   list_films_by_author, update_film, validate_film_form)
from models import AuthAndPreferencesModule as Auth, init_user_storage


def cleanup(author_id):
    """Удаляет тестовые данные."""
    connection = connect_to_database()
    if not connection:
        return
    cursor = connection.cursor()
    cursor.execute("DELETE FROM films WHERE author_id = %s;", (author_id,))
    cursor.execute("DELETE FROM users WHERE id = %s;", (author_id,))
    connection.commit()
    cursor.close()
    connection.close()


def main():
    assert init_user_storage(), "Не удалось подключиться к базе. Проверьте .env и PostgreSQL."
    assert init_films_storage(), "Не удалось создать таблицу films."

    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    ok, message = Auth.register(email, "password123", "Тестовый автор", "author")
    assert ok, message
    author_id = Auth.login(email, "password123")["id"]

    try:
        # 1. Проверка данных формы
        good = MultiDict([("title", "Тестовый фильм"), ("genres", "Триллер"),
                          ("genres", "Драма"), ("year", "1999"), ("duration", "120"),
                          ("trailer_url", "https://example.com/trailer")])
        data, errors = validate_film_form(good)
        assert not errors, errors
        assert data["genres"] == "Драма, Триллер", data["genres"]

        bad = MultiDict([("title", ""), ("year", "1800"), ("duration", "0"),
                         ("trailer_url", "ftp://example.com")])
        _, errors = validate_film_form(bad)
        assert len(errors) == 4, errors
        print("OK: проверка формы работает")

        # 1а. Проверка видеофайла
        mp4 = FileStorage(io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"0" * 100), filename="a.mp4")
        assert check_video(mp4) is None
        fake = FileStorage(io.BytesIO(b"this is not a video, just text"), filename="a.mp4")
        assert check_video(fake)
        wrong = FileStorage(io.BytesIO(b"\x00\x00\x00\x18ftypmp42"), filename="a.avi")
        assert check_video(wrong)
        print("OK: проверка видеофайла работает")

        # 2. Создание и чтение
        film_id = create_film(author_id, data)
        assert film_id, "Фильм не создался"
        film = get_film(film_id)
        assert film["title"] == "Тестовый фильм"
        assert film["author_id"] == author_id
        assert film["year"] == 1999 and film["duration"] == 120
        print("OK: фильм создан и прочитан, id =", film_id)

        # 3. Изменение
        data["title"] = "Тестовый фильм (изменён)"
        data["year"] = 2001
        assert update_film(film_id, author_id, data), "Фильм не изменился"
        film = get_film(film_id)
        assert film["title"] == "Тестовый фильм (изменён)" and film["year"] == 2001
        print("OK: фильм изменён")

        # 4. Чужой автор не может менять карточку
        assert not update_film(film_id, author_id + 999999, data)
        assert get_film(film_id)["title"] == "Тестовый фильм (изменён)"
        print("OK: чужую карточку изменить нельзя")

        # 5. Список «Мои фильмы»
        films = list_films_by_author(author_id)
        assert [f["id"] for f in films] == [film_id]
        print("OK: список «Мои фильмы» работает")
    finally:
        cleanup(author_id)

    print("Все проверки пройдены.")


if __name__ == "__main__":
    main()
