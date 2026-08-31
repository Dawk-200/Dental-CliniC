"""
Patient-facing appointment booking, lookup, cancellation and rescheduling.

The backend is the source of truth for slot availability at every step -
frontend JS is only used for UX; every booking/reschedule is re-validated
here before it touches the database.
"""
import re
from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy.exc import IntegrityError

from app.extensions import db, limiter
from app.models import Treatment, Patient, Appointment, WorkingHours
from app.utils import (
    get_available_slots, is_slot_valid, generate_public_code,
    create_notification, add_history, whatsapp_link
)

booking_bp = Blueprint("booking", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+()\-\s]{7,20}$")


def _valid_email(v):
    return not v or bool(EMAIL_RE.match(v))


def _valid_phone(v):
    return bool(v and PHONE_RE.match(v))


@booking_bp.route("/book-appointment")
def book_appointment():
    treatments = Treatment.query.filter_by(is_active=True).order_by(Treatment.display_order).all()
    preselect = request.args.get("treatment", "")
    return render_template("booking.html", treatments=treatments, preselect=preselect)


@booking_bp.route("/appointment/manage", methods=["GET", "POST"])
@limiter.limit("15/hour", methods=["POST"])
def manage_appointment():
    """Patients look up an appointment using their reference code + phone."""
    appointment = None
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        phone = request.form.get("phone", "").strip()
        if not code or not phone:
            flash("Please enter both your appointment code and phone number.", "error")
        else:
            appointment = Appointment.query.filter_by(public_code=code).first()
            if not appointment or appointment.patient.phone.strip() != phone:
                flash("We couldn't find a matching appointment. Please check your details.", "error")
                appointment = None
    return render_template("manage_appointment.html", appointment=appointment)


@booking_bp.route("/appointment/<public_code>/cancel", methods=["POST"])
def cancel_appointment(public_code):
    appointment = Appointment.query.filter_by(public_code=public_code).first_or_404()
    phone = request.form.get("phone", "").strip()
    if appointment.patient.phone.strip() != phone:
        flash("Phone number does not match our records.", "error")
        return redirect(url_for("booking.manage_appointment"))

    if appointment.status in ("cancelled", "completed"):
        flash("This appointment can no longer be cancelled.", "error")
        return redirect(url_for("booking.manage_appointment"))

    appointment.status = "cancelled"
    appointment.cancelled_at = datetime.utcnow()
    appointment.cancellation_reason = request.form.get("reason", "Cancelled by patient")
    add_history(appointment, "cancelled", "Cancelled by patient", performed_by="patient")
    create_notification(
        "cancelled",
        f"Appointment cancelled: {appointment.public_code}",
        f"{appointment.patient.full_name} cancelled their appointment on {appointment.date}.",
        url_for("admin.appointment_detail", appointment_id=appointment.id),
    )
    db.session.commit()
    flash("Your appointment has been cancelled. The time slot is now available for others.", "success")
    return redirect(url_for("booking.manage_appointment"))


@booking_bp.route("/appointment/<public_code>/reschedule", methods=["GET", "POST"])
def reschedule_appointment(public_code):
    appointment = Appointment.query.filter_by(public_code=public_code).first_or_404()

    if request.method == "GET":
        phone = request.args.get("phone", "").strip()
        if appointment.patient.phone.strip() != phone:
            flash("Phone number does not match our records.", "error")
            return redirect(url_for("booking.manage_appointment"))
        return render_template("reschedule.html", appointment=appointment, phone=phone)

    # POST: perform the reschedule
    phone = request.form.get("phone", "").strip()
    new_date_str = request.form.get("date", "")
    new_time = request.form.get("time", "")

    if appointment.patient.phone.strip() != phone:
        flash("Phone number does not match our records.", "error")
        return redirect(url_for("booking.manage_appointment"))

    if appointment.status in ("cancelled", "completed"):
        flash("This appointment can no longer be rescheduled.", "error")
        return redirect(url_for("booking.manage_appointment"))

    try:
        new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Please select a valid date.", "error")
        return redirect(url_for("booking.reschedule_appointment", public_code=public_code, phone=phone))

    duration = appointment.duration_minutes or appointment.treatment.duration_minutes
    if not is_slot_valid(new_date, new_time, duration):
        flash("Sorry, that slot is no longer available. Please choose another.", "error")
        return redirect(url_for("booking.reschedule_appointment", public_code=public_code, phone=phone))

    old_date, old_time = appointment.date, appointment.time
    appointment.date = new_date
    appointment.time = new_time
    appointment.status = "reschedule_requested"
    add_history(
        appointment, "rescheduled",
        f"Moved from {old_date} {old_time} to {new_date} {new_time}",
        performed_by="patient",
    )
    create_notification(
        "rescheduled",
        f"Reschedule request: {appointment.public_code}",
        f"{appointment.patient.full_name} moved their appointment to {new_date} {new_time}.",
        url_for("admin.appointment_detail", appointment_id=appointment.id),
    )

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("That slot was just taken. Please pick another time.", "error")
        return redirect(url_for("booking.reschedule_appointment", public_code=public_code, phone=phone))

    flash("Your appointment has been rescheduled and is pending confirmation.", "success")
    return redirect(url_for("booking.manage_appointment"))


@booking_bp.route("/book-appointment/confirm", methods=["POST"])
@limiter.limit("10/hour", methods=["POST"])
def confirm_booking():
    """
    Final booking submission. Performs full server-side validation
    (this is the authoritative step - never trust the frontend).
    """
    data = request.form

    # --- 1. Validate treatment -----------------------------------------
    treatment_id = data.get("treatment_id", type=int)
    treatment = Treatment.query.filter_by(id=treatment_id, is_active=True).first()
    other_problem = data.get("other_problem", "").strip()
    if not treatment:
        flash("Please select a valid treatment.", "error")
        return redirect(url_for("booking.book_appointment"))

    # --- 2. Validate date -------------------------------------------------
    date_str = data.get("date", "")
    try:
        appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Please select a valid appointment date.", "error")
        return redirect(url_for("booking.book_appointment", treatment=treatment.slug))

    if appt_date < date.today():
        flash("Appointments cannot be booked in the past.", "error")
        return redirect(url_for("booking.book_appointment", treatment=treatment.slug))

    # --- 3. Validate slot (working hours, breaks, double-booking) --------
    time_str = data.get("time", "")
    duration = treatment.duration_minutes or 30
    if not is_slot_valid(appt_date, time_str, duration):
        flash("Please select an available appointment slot.", "error")
        return redirect(url_for("booking.book_appointment", treatment=treatment.slug))

    # --- 4. Validate patient info ------------------------------------------
    full_name = data.get("full_name", "").strip()
    phone = data.get("phone", "").strip()
    whatsapp = data.get("whatsapp", "").strip() or phone
    email = data.get("email", "").strip()
    age = data.get("age", type=int)
    patient_type = data.get("patient_type", "new")
    problem_description = data.get("problem_description", "").strip() or other_problem
    additional_notes = data.get("additional_notes", "").strip()

    errors = []
    if not full_name or len(full_name) < 2:
        errors.append("Please enter your full name.")
    if not _valid_phone(phone):
        errors.append("Please enter a valid phone number.")
    if not _valid_email(email):
        errors.append("Please enter a valid email address.")
    if age is not None and (age < 0 or age > 120):
        errors.append("Please enter a valid age.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("booking.book_appointment", treatment=treatment.slug))

    # --- 5. Create / reuse patient record ----------------------------------
    patient = Patient.query.filter_by(phone=phone).first()
    if not patient:
        patient = Patient(
            full_name=full_name, phone=phone, whatsapp=whatsapp, email=email,
            age=age, patient_type=patient_type,
        )
        db.session.add(patient)
        db.session.flush()
        is_new_patient = True
    else:
        is_new_patient = False
        patient.full_name = full_name
        patient.whatsapp = whatsapp or patient.whatsapp
        patient.email = email or patient.email
        if age is not None:
            patient.age = age

    # --- 6. Create appointment (unique constraint guards double-booking) --
    appointment = Appointment(
        public_code=generate_public_code(),
        patient_id=patient.id,
        treatment_id=treatment.id,
        date=appt_date,
        time=time_str,
        duration_minutes=duration,
        problem_description=problem_description,
        additional_notes=additional_notes,
        status="pending",
    )
    db.session.add(appointment)

    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        flash("Sorry, that slot was just booked by someone else. Please choose another time.", "error")
        return redirect(url_for("booking.book_appointment", treatment=treatment.slug))

    add_history(appointment, "created", "Appointment created by patient", performed_by="patient")

    if is_new_patient:
        create_notification(
            "new_patient", f"New patient: {patient.full_name}",
            f"Registered via appointment booking.", url_for("admin.patient_detail", patient_id=patient.id)
        )
    create_notification(
        "new_appointment",
        f"New appointment: {appointment.public_code}",
        f"{patient.full_name} booked {treatment.name} on {appt_date} at {time_str}.",
        url_for("admin.appointment_detail", appointment_id=appointment.id),
    )

    db.session.commit()
    return redirect(url_for("booking.booking_success", public_code=appointment.public_code))


@booking_bp.route("/book-appointment/success/<public_code>")
def booking_success(public_code):
    appointment = Appointment.query.filter_by(public_code=public_code).first_or_404()
    return render_template("booking_success.html", appointment=appointment)
