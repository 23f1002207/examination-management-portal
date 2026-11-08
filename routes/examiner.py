from flask import Blueprint, render_template, request, redirect, url_for, flash, g

from models import db, Course, Exam, ExaminerRequest
from routes.auth import role_required

examiner_bp = Blueprint("examiner", __name__, url_prefix="/examiner")
examiner_required = role_required("Examiner")


def open_exams():
    """Exams with no examiner yet that can still be requested."""
    return (Exam.query.join(Course, Exam.course_code == Course.code)
            .filter(Exam.examiner_id.is_(None), Exam.status == "Not Completed",
                    Course.status == "Current"))


@examiner_bp.route("/dashboard")
@examiner_required
def dashboard():
    me = g.user.examiner
    reqs = ExaminerRequest.query.filter_by(examiner_id=me.id)
    stats = {
        "Available Examinations": open_exams().count(),
        "My Requests": reqs.count(),
        "Pending": reqs.filter_by(status="Pending").count(),
        "Approved": reqs.filter_by(status="Approved").count(),
        "Rejected": reqs.filter_by(status="Rejected").count(),
        "Assigned Examinations": Exam.query.filter(Exam.examiner_id == me.id,
                                                   Exam.status != "Removed").count(),
    }
    return render_template("examiner/dashboard.html", me=me, stats=stats)


@examiner_bp.route("/profile", methods=["GET", "POST"])
@examiner_required
def profile():
    me = g.user.examiner
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
        else:
            me.name = name
            me.contact_no = request.form.get("contact_no", "").strip()
            me.department = request.form.get("department", "").strip()
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("examiner.profile"))
    return render_template("examiner/profile.html", me=me)


@examiner_bp.route("/available")
@examiner_required
def available_exams():
    me = g.user.examiner
    pending_ids = {r.exam_id for r in
                   ExaminerRequest.query.filter_by(examiner_id=me.id, status="Pending")}
    return render_template("examiner/available_exams.html",
                           exams=open_exams().order_by(Exam.id).all(), pending_ids=pending_ids)


@examiner_bp.route("/request/<int:exam_id>", methods=["POST"])
@examiner_required
def submit_request(exam_id):
    me = g.user.examiner
    exam = db.session.get(Exam, exam_id)
    if exam is None or exam.status != "Not Completed" or exam.course.status != "Current":
        flash("This examination is not available.", "danger")
    elif exam.examiner_id is not None:
        flash("This examination already has an examiner.", "danger")
    elif ExaminerRequest.query.filter_by(examiner_id=me.id, exam_id=exam_id,
                                         status="Pending").first():
        flash("You already have a pending request for this examination.", "warning")
    else:
        db.session.add(ExaminerRequest(examiner_id=me.id, exam_id=exam_id, status="Pending"))
        db.session.commit()
        flash("Request submitted.", "success")
    return redirect(url_for("examiner.available_exams"))


@examiner_bp.route("/requests")
@examiner_required
def my_requests():
    reqs = (ExaminerRequest.query.filter_by(examiner_id=g.user.examiner.id)
            .order_by(ExaminerRequest.request_date.desc()).all())
    return render_template("examiner/my_requests.html", reqs=reqs)


@examiner_bp.route("/assigned")
@examiner_required
def assigned_exams():
    exams = (Exam.query.filter(Exam.examiner_id == g.user.examiner.id,
                               Exam.status != "Removed").order_by(Exam.id).all())
    return render_template("examiner/assigned_exams.html", exams=exams)
