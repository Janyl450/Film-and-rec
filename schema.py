"""Таблицы, которые нужны этапам ФТ-1.2, ФТ-1.3 и ФТ-1.6.

films и author_applications общие с напарницей (ФТ-2.1 и ФТ-2.6): структура согласована,
создание безопасно повторять (IF NOT EXISTS).
"""
from dbutil import db_cursor

DDL = """
CREATE TABLE IF NOT EXISTS films (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    genres TEXT,
    year INTEGER,
    country VARCHAR(100),
    director VARCHAR(255),
    actors TEXT,
    duration INTEGER,
    description TEXT,
    trailer_url VARCHAR(500),
    poster_url VARCHAR(500),
    author_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS author_applications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    portfolio_url VARCHAR(500),
    about TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    comment TEXT,
    reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    film_id INTEGER NOT NULL REFERENCES films(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plot_score SMALLINT NOT NULL CHECK (plot_score BETWEEN 1 AND 10),
    acting_score SMALLINT NOT NULL CHECK (acting_score BETWEEN 1 AND 10),
    visual_score SMALLINT NOT NULL CHECK (visual_score BETWEEN 1 AND 10),
    overall_score NUMERIC(3,1) NOT NULL,
    text TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (film_id, user_id)
);

CREATE TABLE IF NOT EXISTS hidden_films (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    film_id INTEGER NOT NULL REFERENCES films(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, film_id)
);

CREATE TABLE IF NOT EXISTS admin_log (
    id SERIAL PRIMARY KEY,
    admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    target VARCHAR(255),
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_extra_tables():
    """Создаёт недостающие таблицы. Таблица users должна уже существовать."""
    with db_cursor(commit=True) as cur:
        cur.execute(DDL)
