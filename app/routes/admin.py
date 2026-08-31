"""
Admin dashboard: appointments, patients, treatments, availability,
notifications, blog CMS, reviews, settings, SEO, audit log, backups.

Every route in this blueprint is protected by @login_required + @admin_required.
"""
import json
import os
import shutil
from datetime import datetime, date, timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, jsonify,
    current_app, send_from_directory
)
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.decorators import admin_required
from app.models import (
    Appointment, Patient, Treatment, WorkingHours, BlockedSlot, ClinicSettings,
    Notification, BlogPost, Review, ContactMessage, AuditLog, AdminUser,
    AppointmentHistory
)
from app.utils import (
    create_notification, add_history, log_audit, slugify, is_slot_valid,
    generate_public_code
)

admin_bp = Blueprint("admin", __name__)

STATUS_LABELS = {
    "pending": "Pending",
    "confirmed": "Confirmed",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "no_show": "No-show",
    "reschedule_requested": "Reschedule Requested",
}


@admin_bp.before_request
@login_required
@admin_required
def require_admin():
    """Applied to every route in this blueprint."""
    pass


def _date_range_bounds(preset, start=None, end=None):
    today = date.today()
    if preset == "today":
        return today, today
    if preset == "yesterday":
        y = today - timedelta(days=1)
        return y, y
    if preset == "week":
        start_of_week = today - timedelta(days=today.weekday())
        return start_of_week, today
    if preset == "month":
        return today.replace(day=1), today
    if preset == "year":
        return today.replace(month=1, day=1), today
    if preset == "custom" and start and end:
        try:
            return (
                datetime.strptime(start, "%Y-%m-%d").date(),
                datetime.strptime(end, "%Y-%m-%d").date(),
            )
        except ValueError:
            pass
    return today.replace(day=1), today  # default: this month


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin_bp.route("/")
@admin_bp.route("/dashboard")
def dashboard():
    today = date.today()

    total_patients = Patient.query.filter_by(is_active=True).count()
    todays_appointments = Appointment.query.filter_by(date=today).count()
    upcoming = Appointment.query.filter(
        Appointment.date >= today, Appointment.status.notin_(["cancelled", "completed", "no_show"])
    ).count()
    pending = Appointment.query.filter_by(status="pending").count()
    completed = Appointment.query.filter_by(status="completed").count()
    cancelled = Appointment.query.filter_by(status="cancelled").count()
    no_show = Appointment.query.filter_by(status="no_show").count()
    new_patients_month = Patient.query.filter(
        Patient.created_at >= today.replace(day=1)
    ).count()

    upcoming_list = Appointment.query.filter(
        Appointment.date >= today, Appointment.status.notin_(["cancelled", "completed"])
    ).order_by(Appointment.date, Appointment.time).limit(8).all()

    # Last 7 days appointment volume for chart
    chart_labels, chart_values = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = Appointment.query.filter_by(date=d).count()
        chart_labels.append(d.strftime("%a"))
        chart_values.append(count)

    return render_template(
        "admin/dashboard.html",
        total_patients=total_patients, todays_appointments=todays_appointments,
        upcoming=upcoming, pending=pending, completed=completed, cancelled=cancelled,
        no_show=no_show, new_patients_month=new_patients_month,
        upcoming_list=upcoming_list, chart_labels=chart_labels, chart_values=chart_values,
        status_labels=STATUS_LABELS,
    )


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@admin_bp.route("/statistics")
def statistics():
    preset = request.args.get("range", "month")
    start = request.args.get("start")
    end = request.args.get("end")
    start_date, end_date = _date_range_bounds(preset, start, end)

    q = Appointment.query.filter(Appointment.date.between(start_date, end_date))
    total_appts = q.count()
    completed = q.filter(Appointment.status == "completed").count()
    cancelled = q.filter(Appointment.status == "cancelled").count()
    no_show = q.filter(Appointment.status == "no_show").count()

    new_patients = Patient.query.filter(
        func.date(Patient.created_at).between(start_date, end_date)
    ).count()

    # returning = patients with appointments in range who were created before start_date
    returning_patients = db.session.query(func.count(func.distinct(Appointment.patient_id))).join(
        Patient
    ).filter(
        Appointment.date.between(start_date, end_date),
        Patient.created_at < datetime.combine(start_date, datetime.min.time()),
    ).scalar() or 0

    treatment_breakdown = db.session.query(
        Treatment.name, func.count(Appointment.id)
    ).join(Appointment).filter(
        Appointment.date.between(start_date, end_date)
    ).group_by(Treatment.name).all()

    return render_template(
        "admin/statistics.html",
        preset=preset, start_date=start_date, end_date=end_date,
        total_appts=total_appts, completed=completed, cancelled=cancelled, no_show=no_show,
        new_patients=new_patients, returning_patients=returning_patients,
        treatment_breakdown=treatment_breakdown,
    )


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------
@admin_bp.route("/appointments")
def appointments():
    status = request.args.get("status", "")
    treatment_id = request.args.get("treatment_id", type=int)
    date_filter = request.args.get("date", "")
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    q = Appointment.query.join(Patient)
    if status:
        q = q.filter(Appointment.status == status)
    if treatment_id:
        q = q.filter(Appointment.treatment_id == treatment_id)
    if date_filter:
        try:
            d = datetime.strptime(date_filter, "%Y-%m-%d").date()
            q = q.filter(Appointment.date == d)
        except ValueError:
            pass
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Patient.full_name.ilike(like), Patient.phone.ilike(like),
            Appointment.public_code.ilike(like)
        ))

    pagination = q.order_by(Appointment.date.desc(), Appointment.time.desc()).paginate(
        page=page, per_page=15, error_out=False
    )
    treatments = Treatment.query.order_by(Treatment.name).all()

    return render_template(
        "admin/appointments.html", pagination=pagination, appointments=pagination.items,
        treatments=treatments, status_labels=STATUS_LABELS,
        current_status=status, current_treatment=treatment_id, current_date=date_filter, search=search,
    )


@admin_bp.route("/appointments/new", methods=["GET", "POST"])
def new_appointment():
    treatments = Treatment.query.filter_by(is_active=True).order_by(Treatment.name).all()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        treatment_id = request.form.get("treatment_id", type=int)
        date_str = request.form.get("date", "")
        time_str = request.form.get("time", "")
        notes = request.form.get("additional_notes", "").strip()

        treatment = Treatment.query.get(treatment_id)
        if not full_name or not phone or not treatment or not date_str or not time_str:
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("admin.new_appointment"))

        try:
            appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date.", "error")
            return redirect(url_for("admin.new_appointment"))

        patient = Patient.query.filter_by(phone=phone).first()
        if not patient:
            patient = Patient(full_name=full_name, phone=phone, email=email, patient_type="new")
            db.session.add(patient)
            db.session.flush()

        appointment = Appointment(
            public_code=generate_public_code(),
            patient_id=patient.id, treatment_id=treatment.id,
            date=appt_date, time=time_str,
            duration_minutes=treatment.duration_minutes,
            additional_notes=notes, status="confirmed",
        )
        db.session.add(appointment)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            flash("That slot is already booked. Please choose another time.", "error")
            return redirect(url_for("admin.new_appointment"))

        add_history(appointment, "created", "Manually created by admin", performed_by="admin")
        log_audit("create_appointment", target=appointment.public_code)
        db.session.commit()
        flash(f"Appointment {appointment.public_code} created.", "success")
        return redirect(url_for("admin.appointment_detail", appointment_id=appointment.id))

    return render_template("admin/appointment_form.html", treatments=treatments)


@admin_bp.route("/appointments/<int:appointment_id>")
def appointment_detail(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    return render_template(
        "admin/appointment_detail.html", appointment=appointment, status_labels=STATUS_LABELS
    )


@admin_bp.route("/appointments/<int:appointment_id>/status", methods=["POST"])
def update_appointment_status(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    new_status = request.form.get("status")
    if new_status not in STATUS_LABELS:
        flash("Invalid status.", "error")
        return redirect(url_for("admin.appointment_detail", appointment_id=appointment_id))

    old_status = appointment.status
    appointment.status = new_status
    if new_status == "cancelled":
        appointment.cancelled_at = datetime.utcnow()
        appointment.cancellation_reason = "Cancelled by admin"

    add_history(
        appointment, "status_changed", f"{old_status} -> {new_status}", performed_by="admin"
    )
    log_audit("update_appointment_status", target=appointment.public_code, details=f"{old_status}->{new_status}")
    db.session.commit()
    flash(f"Status updated to {STATUS_LABELS[new_status]}.", "success")
    return redirect(url_for("admin.appointment_detail", appointment_id=appointment_id))


@admin_bp.route("/appointments/<int:appointment_id>/reschedule", methods=["POST"])
def admin_reschedule_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    date_str = request.form.get("date", "")
    time_str = request.form.get("time", "")

    try:
        new_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date.", "error")
        return redirect(url_for("admin.appointment_detail", appointment_id=appointment_id))

    duration = appointment.duration_minutes or 30
    # Allow the current slot to "stay" if unchanged, otherwise re-validate
    if (new_date, time_str) != (appointment.date, appointment.time):
        if not is_slot_valid(new_date, time_str, duration):
            flash("That slot is not available.", "error")
            return redirect(url_for("admin.appointment_detail", appointment_id=appointment_id))

    old_date, old_time = appointment.date, appointment.time
    appointment.date, appointment.time = new_date, time_str
    add_history(
        appointment, "rescheduled", f"{old_date} {old_time} -> {new_date} {time_str}",
        performed_by="admin"
    )
    log_audit("reschedule_appointment", target=appointment.public_code)
    db.session.commit()
    flash("Appointment rescheduled.", "success")
    return redirect(url_for("admin.appointment_detail", appointment_id=appointment_id))


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------
@admin_bp.route("/patients")
def patients():
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    q = Patient.query
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Patient.full_name.ilike(like), Patient.phone.ilike(like), Patient.email.ilike(like)))
    pagination = q.order_by(Patient.created_at.desc()).paginate(page=page, per_page=15, error_out=False)
    return render_template("admin/patients.html", pagination=pagination, patients=pagination.items, search=search)


@admin_bp.route("/patients/<int:patient_id>", methods=["GET", "POST"])
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if request.method == "POST":
        patient.full_name = request.form.get("full_name", patient.full_name).strip()
        patient.phone = request.form.get("phone", patient.phone).strip()
        patient.email = request.form.get("email", patient.email or "").strip()
        patient.notes = request.form.get("notes", "").strip()
        log_audit("update_patient", target=patient.full_name)
        db.session.commit()
        flash("Patient updated.", "success")
        return redirect(url_for("admin.patient_detail", patient_id=patient_id))
    return render_template("admin/patient_detail.html", patient=patient)


@admin_bp.route("/patients/<int:patient_id>/deactivate", methods=["POST"])
def deactivate_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    patient.is_active = not patient.is_active
    log_audit("toggle_patient_active", target=patient.full_name, details=str(patient.is_active))
    db.session.commit()
    flash("Patient status updated.", "success")
    return redirect(url_for("admin.patient_detail", patient_id=patient_id))


# ---------------------------------------------------------------------------
# Treatments
# ---------------------------------------------------------------------------
@admin_bp.route("/treatments")
def treatments():
    all_treatments = Treatment.query.order_by(Treatment.display_order).all()
    return render_template("admin/treatments.html", treatments=all_treatments)


@admin_bp.route("/treatments/new", methods=["GET", "POST"])
def new_treatment():
    if request.method == "POST":
        return _save_treatment(None)
    return render_template("admin/treatment_form.html", t=None)


@admin_bp.route("/treatments/<int:treatment_id>/edit", methods=["GET", "POST"])
def edit_treatment(treatment_id):
    t = Treatment.query.get_or_404(treatment_id)
    if request.method == "POST":
        return _save_treatment(t)
    return render_template("admin/treatment_form.html", t=t)


def _save_treatment(t):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Treatment name is required.", "error")
        return redirect(request.referrer or url_for("admin.treatments"))

    is_new = t is None
    if is_new:
        t = Treatment()
        base_slug = slugify(name)
        slug = base_slug
        i = 2
        while Treatment.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{i}"
            i += 1
        t.slug = slug
        db.session.add(t)

    t.name = name
    t.icon = request.form.get("icon", "tooth").strip()
    t.short_description = request.form.get("short_description", "").strip()
    t.intro = request.form.get("intro", "").strip()
    t.what_is_it = request.form.get("what_is_it", "").strip()
    t.when_needed = request.form.get("when_needed", "").strip()
    t.symptoms = request.form.get("symptoms", "").strip()
    t.procedure = request.form.get("procedure", "").strip()
    t.recovery = request.form.get("recovery", "").strip()
    t.duration_minutes = request.form.get("duration_minutes", type=int) or 30
    t.price_display = request.form.get("price_display", "").strip()
    t.display_order = request.form.get("display_order", type=int) or 0
    t.is_active = request.form.get("is_active") == "on"
    t.seo_title = request.form.get("seo_title", "").strip()
    t.seo_description = request.form.get("seo_description", "").strip()

    # FAQ pairs: faq_q_1, faq_a_1, ...
    faqs = []
    i = 1
    while True:
        q = request.form.get(f"faq_q_{i}")
        a = request.form.get(f"faq_a_{i}")
        if q is None:
            break
        if q.strip() and a and a.strip():
            faqs.append({"q": q.strip(), "a": a.strip()})
        i += 1
    t.faq_json = json.dumps(faqs)

    log_audit("save_treatment", target=t.name)
    db.session.commit()
    flash(f"Treatment '{t.name}' saved.", "success")
    return redirect(url_for("admin.treatments"))


@admin_bp.route("/treatments/<int:treatment_id>/toggle", methods=["POST"])
def toggle_treatment(treatment_id):
    t = Treatment.query.get_or_404(treatment_id)
    t.is_active = not t.is_active
    log_audit("toggle_treatment", target=t.name, details=str(t.is_active))
    db.session.commit()
    flash("Treatment status updated.", "success")
    return redirect(url_for("admin.treatments"))


# ---------------------------------------------------------------------------
# Availability / Slot management
# ---------------------------------------------------------------------------
@admin_bp.route("/availability", methods=["GET", "POST"])
def availability():
    if request.method == "POST":
        for wh in WorkingHours.query.all():
            prefix = f"day_{wh.weekday}_"
            wh.is_open = request.form.get(prefix + "open") == "on"
            wh.open_time = request.form.get(prefix + "start", wh.open_time)
            wh.close_time = request.form.get(prefix + "end", wh.close_time)
            break_start = request.form.get(prefix + "break_start", "").strip()
            break_end = request.form.get(prefix + "break_end", "").strip()
            wh.break_start = break_start or None
            wh.break_end = break_end or None
        log_audit("update_working_hours")
        db.session.commit()
        flash("Clinic working hours updated.", "success")
        return redirect(url_for("admin.availability"))

    hours = WorkingHours.query.order_by(WorkingHours.weekday).all()
    blocked = BlockedSlot.query.order_by(BlockedSlot.date.desc()).limit(30).all()
    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return render_template("admin/availability.html", hours=hours, blocked=blocked, weekday_names=weekday_names)


@admin_bp.route("/availability/block", methods=["POST"])
def block_slot():
    date_str = request.form.get("date", "")
    time_str = request.form.get("time", "").strip() or None
    reason = request.form.get("reason", "").strip()
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date.", "error")
        return redirect(url_for("admin.availability"))

    db.session.add(BlockedSlot(date=d, time=time_str, reason=reason))
    log_audit("block_slot", target=f"{date_str} {time_str or 'all day'}")
    db.session.commit()
    flash("Slot blocked.", "success")
    return redirect(url_for("admin.availability"))


@admin_bp.route("/availability/block/<int:block_id>/delete", methods=["POST"])
def unblock_slot(block_id):
    b = BlockedSlot.query.get_or_404(block_id)
    log_audit("unblock_slot", target=f"{b.date} {b.time or 'all day'}")
    db.session.delete(b)
    db.session.commit()
    flash("Block removed.", "success")
    return redirect(url_for("admin.availability"))


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@admin_bp.route("/notifications")
def notifications():
    page = request.args.get("page", 1, type=int)
    pagination = Notification.query.order_by(Notification.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template("admin/notifications.html", pagination=pagination, notifications=pagination.items)


@admin_bp.route("/notifications/<int:notif_id>/read", methods=["POST"])
def mark_notification_read_form(notif_id):
    n = Notification.query.get_or_404(notif_id)
    n.is_read = True
    db.session.commit()
    if n.link:
        return redirect(n.link)
    return redirect(url_for("admin.notifications"))


@admin_bp.route("/notifications/read-all", methods=["POST"])
def mark_all_read_form():
    Notification.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("admin.notifications"))


# ---------------------------------------------------------------------------
# Contact messages
# ---------------------------------------------------------------------------
@admin_bp.route("/contact-messages")
def contact_messages():
    page = request.args.get("page", 1, type=int)
    pagination = ContactMessage.query.order_by(ContactMessage.created_at.desc()).paginate(
        page=page, per_page=15, error_out=False
    )
    return render_template("admin/contact_messages.html", pagination=pagination, messages=pagination.items)


@admin_bp.route("/contact-messages/<int:msg_id>/read", methods=["POST"])
def mark_message_read(msg_id):
    m = ContactMessage.query.get_or_404(msg_id)
    m.is_read = True
    db.session.commit()
    return redirect(url_for("admin.contact_messages"))


# ---------------------------------------------------------------------------
# Blog CMS
# ---------------------------------------------------------------------------
@admin_bp.route("/blog")
def blog():
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    return render_template("admin/blog.html", posts=posts)


@admin_bp.route("/blog/new", methods=["GET", "POST"])
def new_blog_post():
    if request.method == "POST":
        return _save_blog_post(None)
    return render_template("admin/blog_form.html", post=None)


@admin_bp.route("/blog/<int:post_id>/edit", methods=["GET", "POST"])
def edit_blog_post(post_id):
    post = BlogPost.query.get_or_404(post_id)
    if request.method == "POST":
        return _save_blog_post(post)
    return render_template("admin/blog_form.html", post=post)


def _save_blog_post(post):
    title = request.form.get("title", "").strip()
    if not title:
        flash("Title is required.", "error")
        return redirect(request.referrer or url_for("admin.blog"))

    is_new = post is None
    if is_new:
        post = BlogPost()
        base_slug = slugify(title)
        slug = base_slug
        i = 2
        while BlogPost.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{i}"
            i += 1
        post.slug = slug
        db.session.add(post)

    post.title = title
    post.excerpt = request.form.get("excerpt", "").strip()
    post.content = request.form.get("content", "").strip()
    post.category = request.form.get("category", "").strip()
    post.tags = request.form.get("tags", "").strip()
    post.author = request.form.get("author", "Clinic Team").strip()
    post.seo_title = request.form.get("seo_title", "").strip()
    post.seo_description = request.form.get("seo_description", "").strip()

    was_published = post.is_published
    post.is_published = request.form.get("is_published") == "on"
    if post.is_published and not was_published:
        post.published_at = datetime.utcnow()

    log_audit("save_blog_post", target=post.title)
    db.session.commit()
    flash(f"Blog post '{post.title}' saved.", "success")
    return redirect(url_for("admin.blog"))


@admin_bp.route("/blog/<int:post_id>/delete", methods=["POST"])
def delete_blog_post(post_id):
    post = BlogPost.query.get_or_404(post_id)
    log_audit("delete_blog_post", target=post.title)
    db.session.delete(post)
    db.session.commit()
    flash("Blog post deleted.", "success")
    return redirect(url_for("admin.blog"))


# ---------------------------------------------------------------------------
# Reviews / testimonials
# ---------------------------------------------------------------------------
@admin_bp.route("/reviews")
def reviews():
    all_reviews = Review.query.order_by(Review.created_at.desc()).all()
    return render_template("admin/reviews.html", reviews=all_reviews)


@admin_bp.route("/reviews/new", methods=["GET", "POST"])
def new_review():
    if request.method == "POST":
        return _save_review(None)
    return render_template("admin/review_form.html", review=None)


@admin_bp.route("/reviews/<int:review_id>/edit", methods=["GET", "POST"])
def edit_review(review_id):
    review = Review.query.get_or_404(review_id)
    if request.method == "POST":
        return _save_review(review)
    return render_template("admin/review_form.html", review=review)


def _save_review(review):
    name = request.form.get("patient_name", "").strip()
    text = request.form.get("review_text", "").strip()
    if not name or not text:
        flash("Patient name and review text are required.", "error")
        return redirect(request.referrer or url_for("admin.reviews"))

    if review is None:
        review = Review()
        db.session.add(review)

    review.patient_name = name
    review.review_text = text
    review.rating = request.form.get("rating", type=int) or 5
    review.is_published = request.form.get("is_published") == "on"

    log_audit("save_review", target=review.patient_name)
    db.session.commit()
    flash("Review saved.", "success")
    return redirect(url_for("admin.reviews"))


@admin_bp.route("/reviews/<int:review_id>/delete", methods=["POST"])
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)
    log_audit("delete_review", target=review.patient_name)
    db.session.delete(review)
    db.session.commit()
    flash("Review deleted.", "success")
    return redirect(url_for("admin.reviews"))


# ---------------------------------------------------------------------------
# Clinic settings
# ---------------------------------------------------------------------------
@admin_bp.route("/settings", methods=["GET", "POST"])
def settings():
    settings = ClinicSettings.get()
    if request.method == "POST":
        for field in [
            "clinic_name", "tagline", "doctor_name", "doctor_designation", "doctor_bio",
            "doctor_qualifications", "doctor_specializations", "doctor_languages",
            "phone", "whatsapp", "email", "address", "google_maps_url",
            "facebook_url", "instagram_url",
        ]:
            value = request.form.get(field)
            if value is not None:
                setattr(settings, field, value.strip())

        exp_years = request.form.get("doctor_experience_years", type=int)
        if exp_years is not None:
            settings.doctor_experience_years = exp_years

        duration = request.form.get("default_appointment_duration", type=int)
        if duration:
            settings.default_appointment_duration = duration

        log_audit("update_clinic_settings")
        db.session.commit()
        flash("Clinic settings updated.", "success")
        return redirect(url_for("admin.settings"))

    return render_template("admin/settings.html", settings=settings)


@admin_bp.route("/seo-settings", methods=["GET", "POST"])
def seo_settings():
    settings = ClinicSettings.get()
    if request.method == "POST":
        settings.seo_site_title = request.form.get("seo_site_title", "").strip()
        settings.seo_meta_description = request.form.get("seo_meta_description", "").strip()
        log_audit("update_seo_settings")
        db.session.commit()
        flash("SEO settings updated.", "success")
        return redirect(url_for("admin.seo_settings"))
    return render_template("admin/seo_settings.html", settings=settings)


# ---------------------------------------------------------------------------
# Admin profile
# ---------------------------------------------------------------------------
@admin_bp.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")

        if name:
            current_user.name = name

        if new_password:
            if not current_user.check_password(current_password):
                flash("Current password is incorrect.", "error")
                return redirect(url_for("admin.profile"))
            if len(new_password) < 8:
                flash("New password must be at least 8 characters.", "error")
                return redirect(url_for("admin.profile"))
            current_user.set_password(new_password)
            log_audit("change_password", target=current_user.email)

        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("admin.profile"))

    return render_template("admin/profile.html")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
@admin_bp.route("/audit-log")
def audit_log():
    page = request.args.get("page", 1, type=int)
    pagination = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )
    return render_template("admin/audit_log.html", pagination=pagination, logs=pagination.items)


# ---------------------------------------------------------------------------
# Database backup
# ---------------------------------------------------------------------------
@admin_bp.route("/backup", methods=["GET", "POST"])
def backup():
    backups_dir = os.path.join(current_app.instance_path, "backups")
    os.makedirs(backups_dir, exist_ok=True)

    if request.method == "POST":
        db_uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
        if db_uri.startswith("sqlite:///"):
            db_path = db_uri.replace("sqlite:///", "", 1)
            if os.path.exists(db_path):
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                backup_name = f"clinic_backup_{timestamp}.db"
                shutil.copy2(db_path, os.path.join(backups_dir, backup_name))
                log_audit("create_backup", target=backup_name)
                db.session.commit()
                flash(f"Backup created: {backup_name}", "success")
            else:
                flash("Database file not found.", "error")
        else:
            flash("Backups are only supported for SQLite databases.", "error")
        return redirect(url_for("admin.backup"))

    files = sorted(os.listdir(backups_dir), reverse=True) if os.path.exists(backups_dir) else []
    return render_template("admin/backup.html", files=files)


@admin_bp.route("/backup/download/<path:filename>")
def download_backup(filename):
    backups_dir = os.path.join(current_app.instance_path, "backups")
    log_audit("download_backup", target=filename)
    db.session.commit()
    # send_from_directory prevents path traversal outside backups_dir
    return send_from_directory(backups_dir, filename, as_attachment=True)
