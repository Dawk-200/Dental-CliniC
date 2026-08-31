"""Admin login / logout."""
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email

from app.extensions import db, limiter
from app.models import AdminUser
from app.utils import log_audit

admin_auth_bp = Blueprint("admin_auth", __name__)


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")


@admin_auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = AdminUser.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.is_active_admin and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            user.last_login_at = datetime.utcnow()
            log_audit("admin_login", target=user.email)
            db.session.commit()
            next_page = request.args.get("next")
            # Only allow safe relative redirects
            if not next_page or not next_page.startswith("/"):
                next_page = url_for("admin.dashboard")
            return redirect(next_page)
        flash("Invalid email or password.", "error")
    return render_template("admin/login.html", form=form)


@admin_auth_bp.route("/logout")
@login_required
def logout():
    log_audit("admin_logout", target=current_user.email)
    db.session.commit()
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin_auth.login"))
