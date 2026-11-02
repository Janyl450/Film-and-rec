"""Подключение этапов ФТ-1.2, ФТ-1.3 и ФТ-1.6 к сайту.

В app.py достаточно двух строк (их добавляет install_features.py):
    from features import register_features
    register_features(app)
"""
from flask import flash, render_template, request, session

from dbutil import db_cursor
from helpers import fmt_dt
from schema import init_extra_tables

_tables_ready = False


def register_features(app):
    from admin import admin_bp
    from recommend import rec_bp
    from reviews import reviews_bp

    app.register_blueprint(rec_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(admin_bp)
    app.add_template_filter(fmt_dt, "dt")

    @app.before_request
    def prepare():
        """1) создаёт таблицы при первом запросе; 2) обновляет роль и проверяет блокировку."""
        global _tables_ready
        if request.endpoint == "static":
            return
        if not _tables_ready:
            try:
                init_extra_tables()
                _tables_ready = True
            except Exception as error:
                print("Не удалось создать таблицы:", error)
        user = session.get("user")
        if user:
            try:
                with db_cursor() as cur:
                    cur.execute("SELECT id, email, name, role, is_blocked FROM users WHERE id = %s;",
                                (user["id"],))
                    row = cur.fetchone()
            except Exception:
                return
            if row is None or row["is_blocked"]:
                session.clear()
                flash("Ваш аккаунт недоступен. Обратитесь к администратору.", "error")
            elif row["role"] != user.get("role") or row["name"] != user.get("name"):
                user.update(role=row["role"], name=row["name"])
                session.modified = True

    @app.errorhandler(RuntimeError)
    def database_down(_):
        return render_template("error.html", code=503,
                               text="Нет соединения с базой данных. Проверьте, что PostgreSQL запущен."), 503
