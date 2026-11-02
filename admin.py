"""ФТ-1.6. Проверка заявок авторов администратором (п. 4.10.1 ТЗ) и модерация аккаунтов (п. 4.10.2)."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from dbutil import db_cursor
from helpers import admin_required, safe_url

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

STATUS_TITLES = {"pending": "Ожидают проверки", "approved": "Одобрены",
                 "rejected": "Отклонены", "all": "Все"}
MIN_REASON = 5


def log_action(cur, action, target, details=None):
    """Записывает действие администратора в журнал."""
    cur.execute("INSERT INTO admin_log (admin_id, action, target, details) VALUES (%s, %s, %s, %s);",
                (session["user"]["id"], action, target, details))


@admin_bp.route("/")
@admin_required
def home():
    return redirect(url_for("admin.applications"))


@admin_bp.route("/applications")
@admin_required
def applications():
    status = request.args.get("status", "pending")
    if status not in STATUS_TITLES:
        status = "pending"
    with db_cursor() as cur:
        cur.execute("SELECT status, COUNT(*) AS n FROM author_applications GROUP BY status;")
        counts = {row["status"]: row["n"] for row in cur.fetchall()}
        counts["all"] = sum(counts.values())
        sql = ("SELECT a.*, u.email, u.name, u.role, rv.email AS reviewer_email "
               "FROM author_applications a JOIN users u ON u.id = a.user_id "
               "LEFT JOIN users rv ON rv.id = a.reviewed_by ")
        params = []
        if status != "all":
            sql += "WHERE a.status = %s "
            params.append(status)
        sql += "ORDER BY (a.status = 'pending') DESC, a.created_at DESC LIMIT 100;"
        cur.execute(sql, params)
        items = cur.fetchall()
    for item in items:
        item["portfolio"] = safe_url(item["portfolio_url"])
    return render_template("admin/applications.html", items=items, status=status,
                           counts=counts, titles=STATUS_TITLES, min_reason=MIN_REASON)


@admin_bp.route("/applications/<int:app_id>/decide", methods=["POST"])
@admin_required
def decide(app_id):
    action = request.form.get("action")
    comment = request.form.get("comment", "").strip()
    if action not in ("approve", "reject"):
        flash("Неизвестное действие.", "error")
        return redirect(url_for("admin.applications"))
    if action == "reject" and len(comment) < MIN_REASON:
        flash(f"Укажите причину отказа (не короче {MIN_REASON} символов): её увидит пользователь.", "error")
        return redirect(url_for("admin.applications"))

    with db_cursor(commit=True) as cur:
        cur.execute("SELECT a.id, a.user_id, a.status, u.email FROM author_applications a "
                    "JOIN users u ON u.id = a.user_id WHERE a.id = %s FOR UPDATE OF a;", (app_id,))
        app = cur.fetchone()
        if not app:
            flash("Такой заявки нет.", "error")
        elif app["status"] != "pending":
            flash("Эта заявка уже обработана.", "error")
        else:
            new_status = "approved" if action == "approve" else "rejected"
            cur.execute("UPDATE author_applications SET status = %s, comment = %s, "
                        "reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP WHERE id = %s;",
                        (new_status, comment or None, session["user"]["id"], app_id))
            if action == "approve":
                cur.execute("UPDATE users SET role = 'author' WHERE id = %s AND role = 'viewer';",
                            (app["user_id"],))
                flash(f"Заявка одобрена: {app['email']} теперь автор.", "success")
            else:
                flash(f"Заявка отклонена: {app['email']}.", "success")
            log_action(cur, "application_" + new_status, app["email"], comment or None)
    return redirect(url_for("admin.applications", status=request.form.get("back", "pending")))


@admin_bp.route("/users")
@admin_required
def users():
    q = request.args.get("q", "").strip()[:100]
    with db_cursor() as cur:
        sql = "SELECT id, email, name, role, is_blocked, created_at FROM users "
        params = []
        if q:
            sql += "WHERE email ILIKE %s OR name ILIKE %s "
            params += [f"%{q}%", f"%{q}%"]
        sql += "ORDER BY created_at DESC, id DESC LIMIT 100;"
        cur.execute(sql, params)
        items = cur.fetchall()
    return render_template("admin/users.html", items=items, q=q, me=session["user"]["id"])


@admin_bp.route("/users/<int:user_id>/toggle-block", methods=["POST"])
@admin_required
def toggle_block(user_id):
    if user_id == session["user"]["id"]:
        flash("Свой аккаунт заблокировать нельзя.", "error")
        return redirect(url_for("admin.users"))
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT email, role, is_blocked FROM users WHERE id = %s FOR UPDATE;", (user_id,))
        user = cur.fetchone()
        if not user:
            flash("Такого пользователя нет.", "error")
        elif user["role"] == "admin":
            flash("Аккаунт администратора заблокировать нельзя.", "error")
        else:
            blocked = not user["is_blocked"]
            cur.execute("UPDATE users SET is_blocked = %s WHERE id = %s;", (blocked, user_id))
            log_action(cur, "user_blocked" if blocked else "user_unblocked", user["email"])
            flash(f"{user['email']}: аккаунт {'заблокирован' if blocked else 'разблокирован'}.", "success")
    return redirect(url_for("admin.users", q=request.form.get("q", "")))


@admin_bp.route("/log")
@admin_required
def log():
    with db_cursor() as cur:
        cur.execute("SELECT l.*, u.email AS admin_email FROM admin_log l "
                    "LEFT JOIN users u ON u.id = l.admin_id ORDER BY l.created_at DESC, l.id DESC LIMIT 100;")
        items = cur.fetchall()
    return render_template("admin/log.html", items=items)
