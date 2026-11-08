from flask import Flask
from werkzeug.security import generate_password_hash

from config import Config
from models import db, User, Admin
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.examiner import examiner_bp
from routes.student import student_bp


def seed_admin():
    """Create the first admin A1/A1 only if no Admin exists."""
    if Admin.query.first() is None:
        user = User(username="A1", password_hash=generate_password_hash("A1"),
                    role="Admin", status="Active")
        db.session.add(user)
        db.session.flush()
        db.session.add(Admin(user_id=user.id, name="Administrator",
                             contact="", status="Active"))
        db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(examiner_bp)
    app.register_blueprint(student_bp)
    with app.app_context():
        db.create_all()
        seed_admin()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)