"""Public-facing website routes: home, about, treatments, contact, blog, etc."""
import json
from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional

from app.extensions import db, limiter
from app.models import Treatment, BlogPost, Review, ContactMessage, WorkingHours
from app.utils import create_notification, slugify

main_bp = Blueprint("main", __name__)

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class ContactForm(FlaskForm):
    name = StringField("Full Name", validators=[DataRequired(), Length(max=150)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=255)])
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    message = TextAreaField("Message", validators=[DataRequired(), Length(max=2000)])


@main_bp.route("/")
def home():
    treatments = Treatment.query.filter_by(is_active=True).order_by(Treatment.display_order).limit(8).all()
    reviews = Review.query.filter_by(is_published=True).order_by(Review.created_at.desc()).limit(6).all()
    return render_template("home.html", treatments=treatments, reviews=reviews)


@main_bp.route("/about-doctor")
def about():
    return render_template("about.html")


@main_bp.route("/treatments")
def treatments():
    all_treatments = Treatment.query.filter_by(is_active=True).order_by(Treatment.display_order).all()
    return render_template("treatments.html", treatments=all_treatments)


@main_bp.route("/treatments/<slug>")
def treatment_detail(slug):
    treatment = Treatment.query.filter_by(slug=slug, is_active=True).first_or_404()
    faqs = []
    if treatment.faq_json:
        try:
            faqs = json.loads(treatment.faq_json)
        except Exception:
            faqs = []
    related = Treatment.query.filter(
        Treatment.id != treatment.id, Treatment.is_active == True
    ).order_by(Treatment.display_order).limit(3).all()
    return render_template("treatment_detail.html", t=treatment, faqs=faqs, related=related)


@main_bp.route("/clinic-timings")
def timings():
    hours = WorkingHours.query.order_by(WorkingHours.weekday).all()
    return render_template("timings.html", hours=hours, weekday_names=WEEKDAY_NAMES)


@main_bp.route("/contact", methods=["GET", "POST"])
@limiter.limit("10/hour", methods=["POST"])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        msg = ContactMessage(
            name=form.name.data.strip(),
            email=(form.email.data or "").strip(),
            phone=(form.phone.data or "").strip(),
            message=form.message.data.strip(),
        )
        db.session.add(msg)
        create_notification(
            "contact_form",
            "New contact form submission",
            f"From {msg.name}",
            url_for("admin.contact_messages"),
        )
        db.session.commit()
        flash("Thank you! Your message has been sent. We'll get back to you soon.", "success")
        return redirect(url_for("main.contact"))
    return render_template("contact.html", form=form)


@main_bp.route("/faq")
def faq():
    return render_template("faq.html")


@main_bp.route("/blog")
def blog_list():
    page = request.args.get("page", 1, type=int)
    pagination = BlogPost.query.filter_by(is_published=True).order_by(
        BlogPost.published_at.desc()
    ).paginate(page=page, per_page=6, error_out=False)
    return render_template("blog_list.html", pagination=pagination, posts=pagination.items)


@main_bp.route("/blog/<slug>")
def blog_post(slug):
    post = BlogPost.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template("blog_post.html", post=post)


@main_bp.route("/privacy-policy")
def privacy():
    return render_template("privacy.html")


@main_bp.route("/terms-conditions")
def terms():
    return render_template("terms.html")
