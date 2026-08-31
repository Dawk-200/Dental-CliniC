"""Shared helper functions: slot generation, audit logging, notifications."""
import re
import secrets
import string
from datetime import datetime, date, timedelta

from flask import request
from flask_login import current_user

from app.extensions import db
from app.models import (
    WorkingHours, BlockedSlot, Appointment, Notification, AuditLog
)

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(value: str):
    """Parse 'HH:MM' -> minutes since midnight, or None if invalid."""
    if not value or not TIME_RE.match(value):
        return None
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def minutes_to_hhmm(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"


def format_time_12h(hhmm: str) -> str:
    """'14:30' -> '2:30 PM'"""
    try:
        dt = datetime.strptime(hhmm, "%H:%M")
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return hhmm


def generate_public_code() -> str:
    """Short, human-shareable appointment reference, e.g. WCD-8F2K3Q."""
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"APT-{suffix}"


def get_available_slots(target_date: date, treatment_duration: int = 30):
    """
    Core scheduling engine (server-side source of truth).

    Returns a list of "HH:MM" strings that are bookable for the given date,
    honouring working hours, breaks, existing appointments and blocked slots.
    """
    if target_date < date.today():
        return []

    weekday = target_date.weekday()  # 0=Monday
    wh = WorkingHours.query.filter_by(weekday=weekday).first()
    if not wh or not wh.is_open:
        return []

    open_min = parse_hhmm(wh.open_time)
    close_min = parse_hhmm(wh.close_time)
    if open_min is None or close_min is None or open_min >= close_min:
        return []

    break_start = parse_hhmm(wh.break_start) if wh.break_start else None
    break_end = parse_hhmm(wh.break_end) if wh.break_end else None

    # Whole-day block?
    whole_day_blocked = BlockedSlot.query.filter_by(date=target_date, time=None).first()
    if whole_day_blocked:
        return []

    blocked_times = {
        b.time for b in BlockedSlot.query.filter_by(date=target_date).filter(
            BlockedSlot.time.isnot(None)
        ).all()
    }

    booked_times = {
        a.time for a in Appointment.query.filter_by(date=target_date).filter(
            Appointment.status.notin_(["cancelled"])
        ).all()
    }

    duration = treatment_duration or 30
    slots = []
    cursor = open_min

    # If booking for "today", don't offer past time slots
    now_min = None
    if target_date == date.today():
        now = datetime.now()
        now_min = now.hour * 60 + now.minute

    while cursor + duration <= close_min:
        # Skip if it overlaps the break window
        in_break = False
        if break_start is not None and break_end is not None:
            if cursor < break_end and (cursor + duration) > break_start:
                in_break = True

        hhmm = minutes_to_hhmm(cursor)
        if not in_break and hhmm not in blocked_times and hhmm not in booked_times:
            if now_min is None or cursor > now_min:
                slots.append(hhmm)

        cursor += duration

    return slots


def is_slot_valid(target_date: date, hhmm: str, treatment_duration: int = 30) -> bool:
    """Re-validate a slot server-side right before booking (anti double-booking)."""
    return hhmm in get_available_slots(target_date, treatment_duration)


def create_notification(ntype: str, title: str, message: str = "", link: str = ""):
    note = Notification(type=ntype, title=title, message=message, link=link)
    db.session.add(note)
    return note


def log_audit(action: str, target: str = "", details: str = ""):
    """Record an admin action for the audit trail."""
    try:
        admin_id = current_user.id if current_user.is_authenticated else None
        admin_email = current_user.email if current_user.is_authenticated else "system"
    except Exception:
        admin_id, admin_email = None, "system"

    entry = AuditLog(
        admin_id=admin_id,
        admin_email=admin_email,
        action=action,
        target=target,
        details=details,
        ip_address=request.remote_addr if request else None,
    )
    db.session.add(entry)


def add_history(appointment: Appointment, action: str, details: str = "", performed_by: str = "patient"):
    from app.models import AppointmentHistory
    h = AppointmentHistory(
        appointment_id=appointment.id,
        action=action,
        details=details,
        performed_by=performed_by,
    )
    db.session.add(h)


def whatsapp_link(number: str, message: str) -> str:
    from urllib.parse import quote
    number = re.sub(r"\D", "", number or "")
    return f"https://wa.me/{number}?text={quote(message)}"


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[\s_-]+", "-", value)
