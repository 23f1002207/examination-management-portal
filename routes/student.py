from flask import Blueprint, render_template, request, redirect, url_for, flash, g

from models import db, Course, Exam
from routes.auth import role_required

student_bp = Blueprint("student", __name__, url_prefix="/student")
student_required = role_required("Student")

EXAM_TYPES = ["Viva", "Practical", "Project Demo", "Assessment"]


def visible_exams():
    return (Exam.query.join(Course, Exam.course_code == Course.code)
            .filter(Exam.status != "Removed", Course.status == "Current"))


def available_filter(query):
    """Available = not completed AND an examiner has been assigned."""
    return query.filter(Exam.status == "Not Completed", Exam.examiner_id.isnot(None))


@student_bp.route("/dashboard")
@student_required
def dashboard():
    base = visible_exams()
    stats = {
        "Available Examinations": available_filter(base).count(),
        "Completed Examinations": base.filter(Exam.status == "Completed").count(),
        "Not Completed Examinations": base.filter(Exam.status == "Not Completed").count(),
    }
    return render_template("student/dashboard.html", me=g.user.student, stats=stats)


@student_bp.route("/profile", methods=["GET", "POST"])
@student_required
def profile():
    me = g.user.student
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
        else:
            me.name = name
            me.class_name = request.form.get("class_name", "").strip()
            me.section = request.form.get("section", "").strip()
            me.academic_year = request.form.get("academic_year", "").strip()
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("student.profile"))
    return render_template("student/profile.html", me=me)


@student_bp.route("/examinations")
@student_required
def examinations():
    view = request.args.get("view", "available")     # available / completed / pending / all
    q = request.args.get("q", "").strip()
    course = request.args.get("course", "")
    etype = request.args.get("type", "")
    status = request.args.get("status", "")
    query = visible_exams()
    if view == "available":
        query = available_filter(query)
    elif view == "completed":
        query = query.filter(Exam.status == "Completed")
    elif view == "pending":
        query = query.filter(Exam.status == "Not Completed")
    elif status:
        query = query.filter(Exam.status == status)
    if q:
        cond = Exam.name.ilike(f"%{q}%")
        if q.isdigit():
            cond = cond | (Exam.id == int(q))
        query = query.filter(cond)
    if course:
        query = query.filter(Exam.course_code == course)
    if etype:
        query = query.filter(Exam.type == etype)
    titles = {"available": "Available Examinations", "completed": "Completed Examinations",
              "pending": "Examinations Not Completed", "all": "All Examinations"}
    return render_template("student/examinations.html", exams=query.order_by(Exam.id).all(),
                           view=view, title=titles.get(view, "Examinations"),
                           courses=Course.query.filter_by(status="Current").all(),
                           types=EXAM_TYPES, q=q, course=course, etype=etype, status=status)


@student_bp.route("/examinations/<int:exam_id>")
@student_required
def exam_details(exam_id):
    exam = visible_exams().filter(Exam.id == exam_id).first_or_404()
    return render_template("student/exam_details.html", exam=exam)
