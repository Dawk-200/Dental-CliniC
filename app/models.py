"""
Database models for the Dental Clinic Appointment Management System.

Design notes:
- Appointments are NEVER hard-deleted; status changes and edits are tracked
  in AppointmentHistory so a full audit trail is preserved.
- ClinicSettings and WorkingHours are stored in the DB (not hard-coded) so
  the admin can rebrand / reconfigure the clinic without touching code.
"""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


# ---------------------------------------------------------------------------
# Admin / Auth
# ---------------------------------------------------------------------------
class AdminUser(UserMixin, db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active_admin = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    # Flask-Login requires get_id() -> str, UserMixin provides it using .id
    @property
    def is_active(self):
        return self.is_active_admin


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------
class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(30), nullable=False, index=True)
    whatsapp = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(255), nullable=True, index=True)
    age = db.Column(db.Integer, nullable=True)
    patient_type = db.Column(db.String(20), default="new")  # new | existing
    notes = db.Column(db.Text, nullable=True)  # internal admin notes
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointments = db.relationship(
        "Appointment", back_populates="patient", order_by="Appointment.date.desc()"
    )


# ---------------------------------------------------------------------------
# Treatments
# ---------------------------------------------------------------------------
class Treatment(db.Model):
    __tablename__ = "treatments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    icon = db.Column(db.String(50), default="tooth")  # icon key, see static/js icon map
    short_description = db.Column(db.String(300), nullable=True)
    intro = db.Column(db.Text, nullable=True)
    what_is_it = db.Column(db.Text, nullable=True)
    when_needed = db.Column(db.Text, nullable=True)
    symptoms = db.Column(db.Text, nullable=True)
    procedure = db.Column(db.Text, nullable=True)
    recovery = db.Column(db.Text, nullable=True)
    faq_json = db.Column(db.Text, nullable=True)  # JSON list of {q, a}
    duration_minutes = db.Column(db.Integer, default=30)
    price_display = db.Column(db.String(60), nullable=True)  # optional, blank = hidden
    image_path = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    seo_title = db.Column(db.String(180), nullable=True)
    seo_description = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointments = db.relationship("Appointment", back_populates="treatment")


# ---------------------------------------------------------------------------
# Working hours / availability configuration
# ---------------------------------------------------------------------------
class WorkingHours(db.Model):
    """One row per weekday (0=Monday ... 6=Sunday)."""
    __tablename__ = "working_hours"

    id = db.Column(db.Integer, primary_key=True)
    weekday = db.Column(db.Integer, nullable=False, unique=True)  # 0-6
    is_open = db.Column(db.Boolean, default=True)
    open_time = db.Column(db.String(5), default="10:00")   # "HH:MM" 24h
    close_time = db.Column(db.String(5), default="19:00")
    break_start = db.Column(db.String(5), nullable=True)
    break_end = db.Column(db.String(5), nullable=True)


class BlockedSlot(db.Model):
    """Admin-blocked date/time (holidays, doctor unavailable, etc.)."""
    __tablename__ = "blocked_slots"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    time = db.Column(db.String(5), nullable=True)  # null = whole day blocked
    reason = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------
class Appointment(db.Model):
    __tablename__ = "appointments"
    __table_args__ = (
        db.UniqueConstraint("date", "time", name="uq_appointment_date_time_slot"),
    )

    id = db.Column(db.Integer, primary_key=True)
    public_code = db.Column(db.String(20), unique=True, nullable=False, index=True)

    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    treatment_id = db.Column(db.Integer, db.ForeignKey("treatments.id"), nullable=False)

    date = db.Column(db.Date, nullable=False, index=True)
    time = db.Column(db.String(5), nullable=False)  # "HH:MM"
    duration_minutes = db.Column(db.Integer, default=30)

    problem_description = db.Column(db.Text, nullable=True)
    additional_notes = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(30), default="pending", index=True)
    # pending | confirmed | completed | cancelled | no_show | reschedule_requested

    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = db.relationship("Patient", back_populates="appointments")
    treatment = db.relationship("Treatment", back_populates="appointments")
    history = db.relationship(
        "AppointmentHistory", back_populates="appointment",
        order_by="AppointmentHistory.created_at.desc()", cascade="all, delete-orphan"
    )

    @property
    def is_upcoming(self):
        from datetime import date as _date
        return self.date >= _date.today() and self.status not in (
            "cancelled", "completed", "no_show"
        )


class AppointmentHistory(db.Model):
    """Immutable audit trail of everything that happens to an appointment."""
    __tablename__ = "appointment_history"

    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # created, status_changed, rescheduled, cancelled
    details = db.Column(db.Text, nullable=True)
    performed_by = db.Column(db.String(100), default="patient")  # patient | admin | system
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointment = db.relationship("Appointment", back_populates="history")


# ---------------------------------------------------------------------------
# Clinic settings (singleton row)
# ---------------------------------------------------------------------------
class ClinicSettings(db.Model):
    __tablename__ = "clinic_settings"

    id = db.Column(db.Integer, primary_key=True)

    clinic_name = db.Column(db.String(150), default="Willow Creek Dental Clinic")
    tagline = db.Column(db.String(200), default="Gentle Care. Healthy Smiles.")
    logo_path = db.Column(db.String(255), nullable=True)

    doctor_name = db.Column(db.String(150), default="Dr. Sarah Bennett")
    doctor_designation = db.Column(db.String(150), default="Lead Dental Surgeon, BDS, MDS")
    doctor_photo = db.Column(db.String(255), nullable=True)
    doctor_bio = db.Column(db.Text, default=(
        "Dr. Sarah Bennett has spent over a decade helping patients feel calm and cared for "
        "during every visit. She believes gentle, transparent communication is just as "
        "important as clinical skill."
    ))
    doctor_qualifications = db.Column(db.String(300), default="BDS, MDS (Conservative Dentistry & Endodontics)")
    doctor_experience_years = db.Column(db.Integer, default=12)
    doctor_specializations = db.Column(db.String(300), default="Root Canal Therapy, Cosmetic Dentistry, Implants")
    doctor_languages = db.Column(db.String(200), default="English, Spanish")

    phone = db.Column(db.String(30), default="+1 555-010-2000")
    whatsapp = db.Column(db.String(30), default="15550102000")
    email = db.Column(db.String(255), default="hello@willowcreekdental.example")
    address = db.Column(db.String(300), default="221 Maple Avenue, Springfield, ST 12345")
    google_maps_url = db.Column(db.Text, nullable=True)

    facebook_url = db.Column(db.String(255), nullable=True)
    instagram_url = db.Column(db.String(255), nullable=True)

    default_appointment_duration = db.Column(db.Integer, default=30)

    # SEO defaults (site-wide)
    seo_site_title = db.Column(db.String(180), default="Willow Creek Dental Clinic | Gentle Family & Cosmetic Dentistry")
    seo_meta_description = db.Column(db.String(300), default=(
        "Modern, gentle dental care in Springfield. Book cleanings, root canals, "
        "whitening, implants and more with Dr. Sarah Bennett."
    ))
    seo_og_image = db.Column(db.String(255), nullable=True)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get():
        settings = ClinicSettings.query.first()
        if not settings:
            settings = ClinicSettings()
            db.session.add(settings)
            db.session.commit()
        return settings


# ---------------------------------------------------------------------------
# Notifications (admin-facing)
# ---------------------------------------------------------------------------
class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    # new_appointment | cancelled | rescheduled | new_patient | contact_form
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=True)
    link = db.Column(db.String(255), nullable=True)  # e.g. /admin/appointments/12
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Blog / CMS
# ---------------------------------------------------------------------------
class BlogPost(db.Model):
    __tablename__ = "blog_posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    excerpt = db.Column(db.String(400), nullable=True)
    content = db.Column(db.Text, nullable=False)
    featured_image = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    tags = db.Column(db.String(255), nullable=True)  # comma separated
    author = db.Column(db.String(100), default="Clinic Team")
    is_published = db.Column(db.Boolean, default=False)
    published_at = db.Column(db.DateTime, nullable=True)

    seo_title = db.Column(db.String(180), nullable=True)
    seo_description = db.Column(db.String(300), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Reviews / testimonials
# ---------------------------------------------------------------------------
class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(150), nullable=False)
    rating = db.Column(db.Integer, default=5)  # 1-5
    review_text = db.Column(db.Text, nullable=False)
    photo_path = db.Column(db.String(255), nullable=True)
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Contact form submissions
# ---------------------------------------------------------------------------
class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Audit log (admin actions)
# ---------------------------------------------------------------------------
class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=True)
    admin_email = db.Column(db.String(255), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    target = db.Column(db.String(200), nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
