import re
from datetime import datetime

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, g)

from models import (db, Admin, Course, Exam, Examiner, Student,
                    ExaminerRequest, Rubric, User)
from routes.auth import role_required, create_user

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
admin_required = role_required("Admin")

EXAM_TYPES = ["Viva", "Practical", "Project Demo", "Assessment"]
DATE_FIELDS = ["slot_creation_start_date", "slot_creation_end_date",
               "slot_booking_start_date", "slot_booking_end_date"]


def parse_date(text):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def credentials_page(username, role):
    """Show new account details once. The initial password equals the username."""
    return render_template("credentials.html", username=username,
                           password=username, role=role)


# ======================= Dashboard =======================

@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    stats = {
        "Courses": Course.query.filter_by(status="Current").count(),
        "Examinations": Exam.query.filter(Exam.status != "Removed").count(),
        "Examiners": Examiner.query.filter_by(status="Active").count(),
        "Students": Student.query.filter_by(status="Active").count(),
        "Pending Examiner Requests": ExaminerRequest.query.filter_by(status="Pending").count(),
        "Completed Examinations": Exam.query.filter_by(status="Completed").count(),
        "Examinations Not Completed": Exam.query.filter_by(status="Not Completed").count(),
    }
    return render_template("admin/dashboard.html", stats=stats)


# ======================= Own profile / admin replacement =======================

@admin_bp.route("/profile", methods=["GET", "POST"])
@admin_required
def profile():
    me = g.user.admin
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
        else:
            me.name = name
            me.contact = request.form.get("contact", "").strip()
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("admin.profile"))
    return render_template("admin/profile.html", me=me)


@admin_bp.route("/create-admin", methods=["POST"])
@admin_required
def create_admin():
    """Create a new Admin and deactivate the current one (single transaction)."""
    try:
        for old in Admin.query.filter_by(status="Active").all():
            old.status = "Inactive"
            old.user.status = "Inactive"
        user = create_user("Admin")
        name = request.form.get("name", "").strip() or user.username
        db.session.add(Admin(user_id=user.id, name=name,
                             contact=request.form.get("contact", "").strip(),
                             status="Active"))
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not create the new Admin.", "danger")
        return redirect(url_for("admin.profile"))
    username = user.username
    session.clear()   # old admin is now inactive, so log out
    return credentials_page(username, "Admin")


# ======================= Courses =======================

def read_course_form(form, code):
    name = form.get("name", "").strip()
    if not name:
        return None, "Course name is required."
    return {"code": code, "name": name,
            "description": form.get("description", "").strip()}, None


@admin_bp.route("/courses")
@admin_required
def courses():
    q = request.args.get("q", "").strip()
    show_all = request.args.get("all")
    query = Course.query
    if not show_all:
        query = query.filter_by(status="Current")
    if q:
        query = query.filter(Course.code.ilike(f"%{q}%"))
    return render_template("admin/courses.html", courses=query.order_by(Course.code).all(),
                           q=q, show_all=show_all)


@admin_bp.route("/courses/add", methods=["GET", "POST"])
@admin_required
def course_add():
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        data, error = read_course_form(request.form, code)
        if not re.fullmatch(r"[A-Z0-9_-]+", code):
            error = "Course code may contain only letters, digits, - and _."
        elif db.session.get(Course, code):
            error = "A course with this code already exists."
        if error:
            flash(error, "danger")
        else:
            db.session.add(Course(**data, status="Current"))
            db.session.commit()
            flash("Course added.", "success")
            return redirect(url_for("admin.courses"))
    return render_template("admin/course_form.html", course=None)


@admin_bp.route("/courses/<code>")
@admin_required
def course_details(code):
    course = db.get_or_404(Course, code)
    return render_template("admin/course_details.html", course=course)


@admin_bp.route("/courses/<code>/edit", methods=["GET", "POST"])
@admin_required
def course_edit(code):
    course = db.get_or_404(Course, code)
    if request.method == "POST":
        data, error = read_course_form(request.form, code)
        if error:
            flash(error, "danger")
        else:
            course.name, course.description = data["name"], data["description"]
            db.session.commit()
            flash("Course updated.", "success")
            return redirect(url_for("admin.course_details", code=code))
    return render_template("admin/course_form.html", course=course)


@admin_bp.route("/courses/<code>/delete", methods=["POST"])
@admin_required
def course_delete(code):
    course = db.get_or_404(Course, code)
    course.status = "Removed"
    db.session.commit()
    flash("Course removed.", "success")
    return redirect(url_for("admin.courses"))


@admin_bp.route("/courses/<code>/restore", methods=["POST"])
@admin_required
def course_restore(code):
    course = db.get_or_404(Course, code)
    course.status = "Current"
    db.session.commit()
    flash("Course restored.", "success")
    return redirect(url_for("admin.courses", all=1))


# ======================= Examinations =======================

def read_exam_form(form):
    """Validate exam form. Returns (data, error)."""
    course = db.session.get(Course, form.get("course_code", ""))
    if course is None or course.status != "Current":
        return None, "Choose an existing, current course."
    name = form.get("name", "").strip()
    if not name:
        return None, "Examination name is required."
    if form.get("type") not in EXAM_TYPES:
        return None, "Choose a valid examination type."
    try:
        duration, marks = int(form.get("duration", "")), int(form.get("marks", ""))
    except ValueError:
        return None, "Duration and marks must be whole numbers."
    if duration <= 0 or marks <= 0:
        return None, "Duration and marks must be greater than zero."
    dates = [parse_date(form.get(f)) for f in DATE_FIELDS]
    if None in dates:
        return None, "All four timeline dates are required."
    cs, ce, bs, be = dates
    if cs > ce:
        return None, "Slot creation start must not be after slot creation end."
    if ce >= bs:
        return None, "Slot creation must end before slot booking begins."
    if bs > be:
        return None, "Slot booking start must not be after slot booking end."
    data = {"course_code": course.code, "name": name, "type": form["type"],
            "duration": duration, "marks": marks}
    data.update(dict(zip(DATE_FIELDS, dates)))
    return data, None


@admin_bp.route("/exams")
@admin_required
def exams():
    q = request.args.get("q", "").strip()
    course = request.args.get("course", "")
    etype = request.args.get("type", "")
    status = request.args.get("status", "")
    unassigned = request.args.get("unassigned")
    query = Exam.query
    if status:
        query = query.filter_by(status=status)
    else:
        query = query.filter(Exam.status != "Removed")
    if q:
        cond = Exam.name.ilike(f"%{q}%")
        if q.isdigit():
            cond = cond | (Exam.id == int(q))
        query = query.filter(cond)
    if course:
        query = query.filter_by(course_code=course)
    if etype:
        query = query.filter_by(type=etype)
    if unassigned:
        query = query.filter(Exam.examiner_id.is_(None))
    return render_template("admin/exams.html", exams=query.order_by(Exam.id).all(),
                           courses=Course.query.order_by(Course.code).all(),
                           types=EXAM_TYPES, q=q, course=course, etype=etype,
                           status=status, unassigned=unassigned)


@admin_bp.route("/exams/add", methods=["GET", "POST"])
@admin_required
def exam_add():
    if request.method == "POST":
        data, error = read_exam_form(request.form)
        if error:
            flash(error, "danger")
        else:
            db.session.add(Exam(**data, examiner_id=None, status="Not Completed"))
            db.session.commit()
            flash("Examination created.", "success")
            return redirect(url_for("admin.exams"))
    return render_template("admin/exam_form.html", exam=None, types=EXAM_TYPES,
                           courses=Course.query.filter_by(status="Current").all())


@admin_bp.route("/exams/<int:exam_id>")
@admin_required
def exam_details(exam_id):
    exam = db.get_or_404(Exam, exam_id)
    rubrics = Rubric.query.filter_by(exam_id=exam_id, status="Active").all()
    return render_template("admin/exam_details.html", exam=exam, rubrics=rubrics)


@admin_bp.route("/exams/<int:exam_id>/edit", methods=["GET", "POST"])
@admin_required
def exam_edit(exam_id):
    exam = db.get_or_404(Exam, exam_id)
    if request.method == "POST":
        data, error = read_exam_form(request.form)
        if error:
            flash(error, "danger")
        else:
            for key, value in data.items():
                setattr(exam, key, value)
            db.session.commit()
            flash("Examination updated.", "success")
            return redirect(url_for("admin.exam_details", exam_id=exam_id))
    return render_template("admin/exam_form.html", exam=exam, types=EXAM_TYPES,
                           courses=Course.query.filter_by(status="Current").all())


@admin_bp.route("/exams/<int:exam_id>/complete", methods=["POST"])
@admin_required
def exam_complete(exam_id):
    exam = db.get_or_404(Exam, exam_id)
    if exam.status == "Not Completed":
        exam.status = "Completed"
        db.session.commit()
        flash("Examination marked as Completed.", "success")
    return redirect(url_for("admin.exam_details", exam_id=exam_id))


@admin_bp.route("/exams/<int:exam_id>/delete", methods=["POST"])
@admin_required
def exam_delete(exam_id):
    exam = db.get_or_404(Exam, exam_id)
    exam.status = "Removed"
    db.session.commit()
    flash("Examination removed.", "success")
    return redirect(url_for("admin.exams"))


# ======================= Rubrics =======================

def rubric_totals(exam_id, exclude_id=None):
    rows = Rubric.query.filter_by(exam_id=exam_id, status="Active").all()
    rows = [r for r in rows if r.id != exclude_id]
    return sum(r.weightage for r in rows), sum(r.max_marks for r in rows)


def read_rubric_form(form, exam, exclude_id=None):
    name = form.get("name", "").strip()
    try:
        weightage, max_marks = float(form.get("weightage", "")), float(form.get("max_marks", ""))
    except ValueError:
        return None, "Weightage and maximum marks must be numbers."
    if not name:
        return None, "Criterion name is required."
    if weightage <= 0 or max_marks <= 0:
        return None, "Weightage and maximum marks must be greater than zero."
    used_w, used_m = rubric_totals(exam.id, exclude_id)
    if used_w + weightage > 100.0001:
        return None, f"Total weightage would exceed 100% (already used: {used_w:g}%)."
    if used_m + max_marks > exam.marks + 0.0001:
        return None, f"Total rubric marks would exceed the exam maximum of {exam.marks} (already used: {used_m:g})."
    return {"name": name, "weightage": weightage, "max_marks": max_marks,
            "description": form.get("description", "").strip()}, None


@admin_bp.route("/rubrics")
@admin_required
def rubrics():
    exams_ = Exam.query.filter(Exam.status != "Removed").order_by(Exam.id).all()
    rows = [(e, *rubric_totals(e.id)) for e in exams_]
    return render_template("admin/rubrics.html", exam=None, rows=rows)


@admin_bp.route("/rubrics/<int:exam_id>", methods=["GET", "POST"])
@admin_required
def exam_rubrics(exam_id):
    exam = db.get_or_404(Exam, exam_id)
    if request.method == "POST":
        data, error = read_rubric_form(request.form, exam)
        if error:
            flash(error, "danger")
        else:
            db.session.add(Rubric(exam_id=exam_id, status="Active", **data))
            db.session.commit()
            flash("Rubric criterion added.", "success")
            return redirect(url_for("admin.exam_rubrics", exam_id=exam_id))
    items = Rubric.query.filter_by(exam_id=exam_id, status="Active").all()
    total_w, total_m = rubric_totals(exam_id)
    return render_template("admin/rubrics.html", exam=exam, items=items,
                           total_w=total_w, total_m=total_m)


@admin_bp.route("/rubrics/item/<int:rubric_id>/edit", methods=["GET", "POST"])
@admin_required
def rubric_edit(rubric_id):
    rubric = db.get_or_404(Rubric, rubric_id)
    if request.method == "POST":
        data, error = read_rubric_form(request.form, rubric.exam, exclude_id=rubric.id)
        if error:
            flash(error, "danger")
        else:
            for key, value in data.items():
                setattr(rubric, key, value)
            db.session.commit()
            flash("Rubric criterion updated.", "success")
            return redirect(url_for("admin.exam_rubrics", exam_id=rubric.exam_id))
    return render_template("admin/rubric_form.html", rubric=rubric)


@admin_bp.route("/rubrics/item/<int:rubric_id>/delete", methods=["POST"])
@admin_required
def rubric_delete(rubric_id):
    rubric = db.get_or_404(Rubric, rubric_id)
    rubric.status = "Removed"
    db.session.commit()
    flash("Rubric criterion removed.", "success")
    return redirect(url_for("admin.exam_rubrics", exam_id=rubric.exam_id))


# ======================= Examiners =======================

@admin_bp.route("/examiners")
@admin_required
def examiners():
    q = request.args.get("q", "").strip()
    show_all = request.args.get("all")
    query = Examiner.query.join(User, Examiner.user_id == User.id)
    if not show_all:
        query = query.filter(Examiner.status == "Active")
    if q:
        cond = Examiner.name.ilike(f"%{q}%") | User.username.ilike(f"%{q}%")
        if q.isdigit():
            cond = cond | (Examiner.id == int(q))
        query = query.filter(cond)
    return render_template("admin/examiners.html", examiners=query.order_by(Examiner.id).all(),
                           q=q, show_all=show_all)


@admin_bp.route("/examiners/add", methods=["GET", "POST"])
@admin_required
def examiner_add():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
        else:
            try:
                user = create_user("Examiner")
                db.session.add(Examiner(user_id=user.id, name=name,
                                        contact_no=request.form.get("contact_no", "").strip(),
                                        department=request.form.get("department", "").strip(),
                                        status="Active"))
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash("Could not create the examiner.", "danger")
                return redirect(url_for("admin.examiner_add"))
            return credentials_page(user.username, "Examiner")
    return render_template("admin/examiner_form.html", examiner=None)


@admin_bp.route("/examiners/<int:examiner_id>")
@admin_required
def examiner_details(examiner_id):
    examiner = db.get_or_404(Examiner, examiner_id)
    assigned = [e for e in examiner.exams if e.status != "Removed"]
    return render_template("admin/examiner_details.html", examiner=examiner, assigned=assigned)


@admin_bp.route("/examiners/<int:examiner_id>/edit", methods=["GET", "POST"])
@admin_required
def examiner_edit(examiner_id):
    examiner = db.get_or_404(Examiner, examiner_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
        else:
            examiner.name = name
            examiner.contact_no = request.form.get("contact_no", "").strip()
            examiner.department = request.form.get("department", "").strip()
            db.session.commit()
            flash("Examiner updated.", "success")
            return redirect(url_for("admin.examiner_details", examiner_id=examiner_id))
    return render_template("admin/examiner_form.html", examiner=examiner)


def set_person_status(person, status):
    person.status = status
    person.user.status = status
    db.session.commit()


@admin_bp.route("/examiners/<int:examiner_id>/<action>", methods=["POST"])
@admin_required
def examiner_status(examiner_id, action):
    examiner = db.get_or_404(Examiner, examiner_id)
    if action == "deactivate":
        set_person_status(examiner, "Inactive")
        flash("Examiner deactivated.", "success")
    elif action == "activate":
        set_person_status(examiner, "Active")
        flash("Examiner activated.", "success")
    return redirect(url_for("admin.examiners", all=1))


# ======================= Examiner requests =======================

@admin_bp.route("/requests")
@admin_required
def examiner_requests():
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    query = (ExaminerRequest.query
             .join(Examiner, ExaminerRequest.examiner_id == Examiner.id)
             .join(Exam, ExaminerRequest.exam_id == Exam.id))
    if status:
        query = query.filter(ExaminerRequest.status == status)
    if q:
        query = query.filter(Examiner.name.ilike(f"%{q}%") | Exam.name.ilike(f"%{q}%"))
    reqs = query.order_by(ExaminerRequest.request_date.desc()).all()
    return render_template("admin/examiner_requests.html", reqs=reqs, status=status, q=q)


@admin_bp.route("/requests/<int:req_id>/<action>", methods=["POST"])
@admin_required
def request_decide(req_id, action):
    req = db.get_or_404(ExaminerRequest, req_id)
    if action not in ("approve", "reject"):
        return redirect(url_for("admin.examiner_requests"))
    if req.status != "Pending":
        flash("This request has already been decided.", "warning")
        return redirect(url_for("admin.examiner_requests"))
    try:
        if action == "approve":
            exam = req.exam
            if exam.examiner_id is not None:
                flash("This examination already has an examiner.", "danger")
                return redirect(url_for("admin.examiner_requests"))
            if req.examiner.status != "Active" or exam.status != "Not Completed":
                flash("Cannot approve: examiner inactive or examination not open.", "danger")
                return redirect(url_for("admin.examiner_requests"))
            exam.examiner_id = req.examiner_id
            req.status = "Approved"
        else:
            req.status = "Rejected"
        req.decision_date = datetime.now()
        db.session.commit()
        flash(f"Request {req.status.lower()}.", "success")
    except Exception:
        db.session.rollback()
        flash("Could not save the decision.", "danger")
    return redirect(url_for("admin.examiner_requests"))


# ======================= Students =======================

@admin_bp.route("/students")
@admin_required
def students():
    q = request.args.get("q", "").strip()
    class_name = request.args.get("class_name", "")
    section = request.args.get("section", "")
    year = request.args.get("academic_year", "")
    show_all = request.args.get("all")
    query = Student.query.join(User, Student.user_id == User.id)
    if not show_all:
        query = query.filter(Student.status == "Active")
    if q:
        cond = Student.name.ilike(f"%{q}%") | User.username.ilike(f"%{q}%")
        if q.isdigit():
            cond = cond | (Student.id == int(q))
        query = query.filter(cond)
    if class_name:
        query = query.filter(Student.class_name == class_name)
    if section:
        query = query.filter(Student.section == section)
    if year:
        query = query.filter(Student.academic_year == year)

    def distinct(col):
        return [r[0] for r in db.session.query(col).distinct().order_by(col) if r[0]]

    return render_template("admin/students.html", students=query.order_by(Student.id).all(),
                           q=q, class_name=class_name, section=section, year=year,
                           show_all=show_all, classes=distinct(Student.class_name),
                           sections=distinct(Student.section),
                           years=distinct(Student.academic_year))


def read_student_form(form):
    name = form.get("name", "").strip()
    if not name:
        return None, "Name is required."
    return {"name": name, "class_name": form.get("class_name", "").strip(),
            "section": form.get("section", "").strip(),
            "academic_year": form.get("academic_year", "").strip()}, None


@admin_bp.route("/students/add", methods=["GET", "POST"])
@admin_required
def student_add():
    if request.method == "POST":
        data, error = read_student_form(request.form)
        if error:
            flash(error, "danger")
        else:
            try:
                user = create_user("Student")
                db.session.add(Student(user_id=user.id, status="Active", **data))
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash("Could not create the student.", "danger")
                return redirect(url_for("admin.student_add"))
            return credentials_page(user.username, "Student")
    return render_template("admin/student_form.html", student=None)


@admin_bp.route("/students/<int:student_id>")
@admin_required
def student_details(student_id):
    student = db.get_or_404(Student, student_id)
    return render_template("admin/student_details.html", student=student)


@admin_bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@admin_required
def student_edit(student_id):
    student = db.get_or_404(Student, student_id)
    if request.method == "POST":
        data, error = read_student_form(request.form)
        if error:
            flash(error, "danger")
        else:
            for key, value in data.items():
                setattr(student, key, value)
            db.session.commit()
            flash("Student updated.", "success")
            return redirect(url_for("admin.student_details", student_id=student_id))
    return render_template("admin/student_form.html", student=student)


@admin_bp.route("/students/<int:student_id>/<action>", methods=["POST"])
@admin_required
def student_status(student_id, action):
    student = db.get_or_404(Student, student_id)
    if action == "deactivate":
        set_person_status(student, "Inactive")
        flash("Student deactivated.", "success")
    elif action == "activate":
        set_person_status(student, "Active")
        flash("Student activated.", "success")
    return redirect(url_for("admin.students", all=1))
