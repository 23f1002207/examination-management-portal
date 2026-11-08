from functools import wraps

from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User

auth_bp = Blueprint("auth", __name__)

ROLE_BY_LETTER = {"A": "Admin", "E": "Examiner", "S": "Student"}
DASHBOARD = {"Admin": "admin.dashboard", "Examiner": "examiner.dashboard",
             "Student": "student.dashboard"}


# ---------- helpers used by every route file ----------

def load_user():
    """Return the logged-in, active User (or None). Uses only session['user_id']."""
    uid = session.get("user_id")
    user = db.session.get(User, uid) if uid else None
    if user is None or user.status != "Active":
        return None
    if user.profile is None or user.profile.status != "Active":
        return None
    return user


def role_required(role):
    """Decorator: user must be logged in, active and have the given role."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = load_user()
            if user is None or user.role != role:
                session.clear()
                flash("Please log in to continue.", "warning")
                return redirect(url_for("auth.login"))
            g.user = user
            return view(*args, **kwargs)
        return wrapper
    return decorator


def next_username(role):
    prefix = role[0]
    numbers = [int(u.username[1:]) for u in User.query.filter_by(role=role).all()]
    return f"{prefix}{max(numbers, default=0) + 1}"


def create_user(role):
    """Create a Users row (password = username, hashed). Caller adds profile and commits."""
    username = next_username(role)
    user = User(username=username, password_hash=generate_password_hash(username),
                role=role, status="Active")
    db.session.add(user)
    db.session.flush()
    return user


# ---------- routes ----------

@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().upper()
        password = request.form.get("password", "")
        role = ROLE_BY_LETTER.get(username[:1])
        user = User.query.filter_by(username=username, role=role).first() if role else None
        if user is None or not check_password_hash(user.password_hash, password):
            error = "Invalid username or password."
        elif user.status != "Active" or user.profile is None or user.profile.status != "Active":
            error = "This account is inactive."
        else:
            session.clear()
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for(DASHBOARD[user.role]))
    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    user = load_user()
    if user is None:
        session.clear()
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not check_password_hash(user.password_hash, current):
            flash("Current password is incorrect.", "danger")
        elif not new:
            flash("New password cannot be empty.", "danger")
        elif new != confirm:
            flash("New password and confirmation do not match.", "danger")
        else:
            user.password_hash = generate_password_hash(new)   # only users table changes
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("auth.change_password"))
    return render_template(f"{user.role.lower()}/change_password.html")
