"""Custom decorators for route protection."""
from functools import wraps
from flask import abort
from flask_login import current_user


def admin_required(f):
    """Ensures the current user is an authenticated, active admin."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not getattr(current_user, "is_active_admin", False):
            abort(403)
        return f(*args, **kwargs)
    return wrapped
