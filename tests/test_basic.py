"""
Basic smoke tests for the dental clinic app.

Run with:
    pytest tests/
"""
import os
import sys
import json
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from app import create_app
from app.extensions import db
from app.models import AdminUser, Treatment, WorkingHours, Patient, Appointment
from app.utils import get_available_slots, generate_public_code


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()

        admin = AdminUser(name="Test Admin", email="admin@test.com")
        admin.set_password("TestPassword123!")
        db.session.add(admin)

        for weekday in range(7):
            db.session.add(WorkingHours(
                weekday=weekday, is_open=(weekday != 6),
                open_time="10:00", close_time="18:00",
            ))

        t = Treatment(name="Dental Cleaning", slug="dental-cleaning", duration_minutes=30, is_active=True)
        db.session.add(t)
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_home_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Book an Appointment" in resp.data or b"Book" in resp.data


def test_admin_dashboard_requires_login(client):
    resp = client.get("/admin/dashboard")
    assert resp.status_code in (302, 401)


def test_sitemap_and_robots(client):
    assert client.get("/sitemap.xml").status_code == 200
    assert client.get("/robots.txt").status_code == 200


def test_available_slots_respect_working_hours(app):
    with app.app_context():
        next_monday = date.today() + timedelta(days=1)
        while next_monday.weekday() != 0:
            next_monday += timedelta(days=1)
        slots = get_available_slots(next_monday, 30)
        assert "10:00" in slots
        assert "18:00" not in slots  # closing time itself shouldn't be bookable


def test_double_booking_is_prevented(app):
    with app.app_context():
        patient = Patient(full_name="A", phone="+10000000001")
        db.session.add(patient)
        db.session.flush()
        treatment = Treatment.query.first()

        next_monday = date.today() + timedelta(days=1)
        while next_monday.weekday() != 0:
            next_monday += timedelta(days=1)

        a1 = Appointment(
            public_code=generate_public_code(), patient_id=patient.id,
            treatment_id=treatment.id, date=next_monday, time="10:00",
            duration_minutes=30, status="pending",
        )
        db.session.add(a1)
        db.session.commit()

        a2 = Appointment(
            public_code=generate_public_code(), patient_id=patient.id,
            treatment_id=treatment.id, date=next_monday, time="10:00",
            duration_minutes=30, status="pending",
        )
        db.session.add(a2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()


def test_admin_login_flow(client):
    resp = client.get("/admin/login")
    assert resp.status_code == 200

    resp = client.post("/admin/login", data={
        "email": "admin@test.com", "password": "TestPassword123!",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Dashboard" in resp.data
