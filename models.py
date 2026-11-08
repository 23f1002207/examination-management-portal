import sqlite3
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_conn, _record):
    if isinstance(dbapi_conn, sqlite3.Connection):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False)      # Admin / Examiner / Student
    status = db.Column(db.String(10), nullable=False, default="Active")

    @property
    def profile(self):
        return {"Admin": self.admin, "Examiner": self.examiner,
                "Student": self.student}[self.role]


class Admin(db.Model):
    __tablename__ = "admin"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(30))
    status = db.Column(db.String(10), nullable=False, default="Active")
    user = db.relationship("User", backref=db.backref("admin", uselist=False))


class Course(db.Model):
    __tablename__ = "course"
    code = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(10), nullable=False, default="Current")  # Current / Removed


class Examiner(db.Model):
    __tablename__ = "examiner"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    contact_no = db.Column(db.String(30))
    department = db.Column(db.String(100))
    status = db.Column(db.String(10), nullable=False, default="Active")
    user = db.relationship("User", backref=db.backref("examiner", uselist=False))


class Student(db.Model):
    __tablename__ = "student"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    class_name = db.Column(db.String(50))
    section = db.Column(db.String(20))
    academic_year = db.Column(db.String(20))
    status = db.Column(db.String(10), nullable=False, default="Active")
    user = db.relationship("User", backref=db.backref("student", uselist=False))


class Exam(db.Model):
    __tablename__ = "exam"
    id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(20), db.ForeignKey("course.code"), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey("examiner.id"), nullable=True)
    name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    duration = db.Column(db.Integer, nullable=False)     # minutes
    marks = db.Column(db.Integer, nullable=False)        # maximum marks
    status = db.Column(db.String(20), nullable=False, default="Not Completed")
    slot_creation_start_date = db.Column(db.Date)
    slot_creation_end_date = db.Column(db.Date)
    slot_booking_start_date = db.Column(db.Date)
    slot_booking_end_date = db.Column(db.Date)
    course = db.relationship("Course", backref="exams")
    examiner = db.relationship("Examiner", backref="exams")


class ExaminerRequest(db.Model):
    __tablename__ = "examiner_request"
    id = db.Column(db.Integer, primary_key=True)
    examiner_id = db.Column(db.Integer, db.ForeignKey("examiner.id"), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    request_date = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(10), nullable=False, default="Pending")
    decision_date = db.Column(db.DateTime)
    examiner = db.relationship("Examiner", backref="requests")
    exam = db.relationship("Exam", backref="requests")


class ExamSlot(db.Model):
    __tablename__ = "exam_slot"
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey("examiner.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    available_seats = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(15), nullable=False, default="Yet to Open")


class Booking(db.Model):
    __tablename__ = "booking"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey("exam_slot.id"), nullable=False)
    booking_date = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(10), nullable=False, default="Booked")


class Rubric(db.Model):
    __tablename__ = "rubric"
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    weightage = db.Column(db.Float, nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(10), nullable=False, default="Active")
    exam = db.relationship("Exam", backref="rubrics")


class Marks(db.Model):
    __tablename__ = "marks"
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), unique=True, nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    marks_secured = db.Column(db.Float)
    total_marks = db.Column(db.Float)
    remarks = db.Column(db.Text)
    evaluated_by = db.Column(db.Integer, db.ForeignKey("examiner.id"))
    status = db.Column(db.String(10), nullable=False, default="Pending")
    evaluation_date = db.Column(db.DateTime)


class RubricMark(db.Model):
    __tablename__ = "rubric_mark"
    id = db.Column(db.Integer, primary_key=True)
    marks_id = db.Column(db.Integer, db.ForeignKey("marks.id"), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey("rubric.id"), nullable=False)
    marks_obtained = db.Column(db.Float, nullable=False)
    remarks = db.Column(db.Text)
    status = db.Column(db.String(10), nullable=False, default="Active")
