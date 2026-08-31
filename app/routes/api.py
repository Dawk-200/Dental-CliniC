"""JSON endpoints consumed by vanilla JS fetch() calls."""
from datetime import datetime, date

from flask import Blueprint, request, jsonify
from flask_login import login_required

from app.models import Treatment, WorkingHours, Notification
from app.utils import get_available_slots, format_time_12h
from app.extensions import db, csrf

api_bp = Blueprint("api", __name__)


@api_bp.route("/available-slots")
def available_slots():
    """GET /api/available-slots?date=YYYY-MM-DD&treatment_id=3"""
    date_str = request.args.get("date", "")
    treatment_id = request.args.get("treatment_id", type=int)

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date"}), 400

    duration = 30
    if treatment_id:
        treatment = Treatment.query.get(treatment_id)
        if treatment:
            duration = treatment.duration_minutes or 30

    slots = get_available_slots(target_date, duration)
    return jsonify({
        "date": date_str,
        "slots": [{"value": s, "label": format_time_12h(s)} for s in slots],
    })


@api_bp.route("/clinic-open-days")
def clinic_open_days():
    """Returns which weekdays (0=Mon..6=Sun) the clinic is open, for calendar UI."""
    hours = WorkingHours.query.all()
    open_days = [h.weekday for h in hours if h.is_open]
    return jsonify({"open_weekdays": open_days})


@api_bp.route("/notifications/<int:notif_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    notif.is_read = True
    db.session.commit()
    return jsonify({"success": True})


@api_bp.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"success": True})
