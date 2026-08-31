import os
from flask import Flask, render_template, request
from config import config_map
from app.extensions import db, csrf, login_manager, limiter


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_map.get(config_name, config_map["default"]))

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(os.path.join(app.instance_path, "backups"), exist_ok=True)

    # --- Extensions --------------------------------------------------
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "admin_auth.login"
    login_manager.login_message_category = "info"
    limiter.init_app(app)

    # --- Custom Jinja filters -------------------------------------------
    import json as _json

    @app.template_filter("from_json")
    def from_json_filter(value):
        try:
            return _json.loads(value) if value else []
        except Exception:
            return []

    from app.models import AdminUser

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(AdminUser, int(user_id))

    # --- Blueprints ----------------------------------------------------
    from app.routes.main import main_bp
    from app.routes.booking import booking_bp
    from app.routes.admin_auth import admin_auth_bp
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp
    from app.routes.seo import seo_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(admin_auth_bp, url_prefix="/admin")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(seo_bp)

    # --- Security headers -----------------------------------------------
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # Keep admin pages out of search indexes
        if request.path.startswith("/admin"):
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    # --- Context processor: clinic settings available in every template -
    @app.context_processor
    def inject_globals():
        from app.models import ClinicSettings, Notification
        from app.utils import whatsapp_link, format_time_12h
        settings = ClinicSettings.get()
        unread_count = 0
        try:
            unread_count = Notification.query.filter_by(is_read=False).count()
        except Exception:
            pass
        from datetime import datetime as _dt
        return dict(
            clinic=settings,
            whatsapp_link=whatsapp_link,
            format_time_12h=format_time_12h,
            unread_notifications=unread_count,
            site_url=app.config.get("SITE_URL", ""),
            ga_id=app.config.get("GOOGLE_ANALYTICS_ID", ""),
            google_site_verification=app.config.get("GOOGLE_SITE_VERIFICATION", ""),
            current_year=_dt.utcnow().year,
        )

    # --- Error handlers ---------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("403.html"), 403

    @app.errorhandler(401)
    def unauthorized(e):
        return render_template("403.html"), 401

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template("500.html"), 500

    return app
