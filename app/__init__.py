import os
import sys
import logging
from flask import Flask, render_template, send_from_directory, session

from . import db
from .helpers import (
    csrf_token, get_categories, get_brands, get_cart_rows,
    get_logged_in_user_id, get_wishlist_ids, product_image_path, user_image_path,
)


def create_app():
    app = Flask(__name__)

    # Fail loudly and immediately if required config is missing, instead of
    # booting "successfully" and then failing on the first real request with
    # a confusing error buried in a traceback (this has cost real debugging
    # time multiple times now — DB_HOST blank defaulting to "localhost" is
    # a genuinely misleading failure mode to hit blind).
    required = ["DB_HOST", "DB_USER", "DB_PASS", "SECRET_KEY"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Check that .env exists in this directory and docker-compose picked it up "
            f"(run `docker compose config` to see what the container actually received)."
        )

    app.secret_key = os.environ["SECRET_KEY"]

    # Guarantee errors are visible via `docker compose logs` regardless of
    # how gunicorn's own logging is configured — explicit stdout handler,
    # not relying on Python's default "last resort" logging behavior.
    if not app.logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
        ))
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    # Session cookie hardening — same reasoning as the PHP app's
    # session_set_cookie_params(): HttpOnly limits damage from any XSS,
    # SameSite=Lax mitigates CSRF, Secure auto-activates once served over
    # HTTPS (doesn't break local/plain-HTTP testing in the meantime).
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FORCE_HTTPS_COOKIES", "0") == "1",
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB upload ceiling
    )

    # Never show stack traces / file paths to visitors in production —
    # this bit us for real in the PHP app before we locked it down.
    app.config["DEBUG"] = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.config["PROPAGATE_EXCEPTIONS"] = False

    db.init_app(app)

    # Cache-busting version string for static assets, based on actual file
    # mtime — computed once here, not per-request, so browsers still cache
    # normally between deploys (only changes when the file's content does).
    def _asset_version():
        import os as _os
        css_path = os.path.join(app.static_folder, "css", "komora.css")
        js_path = os.path.join(app.static_folder, "js", "komora.js")
        try:
            return int(max(_os.path.getmtime(css_path), _os.path.getmtime(js_path)))
        except OSError:
            return 1
    asset_version = _asset_version()

    upload_root = os.environ.get("UPLOAD_ROOT", "/data/uploads")
    app.config["PRODUCT_IMAGE_DIR"] = os.path.join(upload_root, "products")
    app.config["USER_IMAGE_DIR"] = os.path.join(upload_root, "users")

    # ---------- template globals available on every page ----------
    @app.context_processor
    def inject_globals():
        # Defensive: if the DB is what's actually broken (e.g. this is
        # rendering the 500 error page itself), fall back to empty data
        # rather than throwing a second exception while handling the first.
        try:
            user_id = get_logged_in_user_id()
            categories = get_categories()
            brands = get_brands()
            cart_rows = get_cart_rows()
            wishlist_ids = get_wishlist_ids(user_id) if user_id else []
        except Exception:
            user_id, categories, brands, cart_rows, wishlist_ids = None, [], [], [], []

        return dict(
            csrf_token=csrf_token,
            categories=categories,
            brands=brands,
            cart_rows=cart_rows,
            logged_in_user_id=user_id,
            wishlist_ids=wishlist_ids,
            product_image_path=product_image_path,
            user_image_path=user_image_path,
            session=session,
            asset_version=asset_version,
            now_year=__import__("datetime").datetime.now().year,
        )

    # ---------- serve uploaded images (outside static/, so uploads can be
    # bind-mounted independently, matching the old admin_area/product_images
    # and users_area/user_images volumes) ----------
    @app.route("/media/products/<path:filename>")
    def media_products(filename):
        return send_from_directory(app.config["PRODUCT_IMAGE_DIR"], filename)

    @app.route("/media/users/<path:filename>")
    def media_users(filename):
        return send_from_directory(app.config["USER_IMAGE_DIR"], filename)

    # ---------- error pages (no stack traces shown to visitors) ----------
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, message=str(e.description or "Forbidden")), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="Page not found"), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import request as _req
        app.logger.exception("Unhandled server error on %s %s", _req.method, _req.path)
        return render_template("error.html", code=500, message="Something went wrong. Please try again later."), 500

    # ---------- blueprints ----------
    from .blueprints.storefront import bp as storefront_bp
    from .blueprints.cart import bp as cart_bp
    from .blueprints.wishlist import bp as wishlist_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.checkout import bp as checkout_bp
    from .blueprints.admin import bp as admin_bp

    app.register_blueprint(storefront_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    return app
