import os
import re
import secrets
import time
from datetime import datetime, timedelta

from flask import session, request, current_app

from .db import query_one, query_all, execute

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_MINUTES = 15


# ---------- request IP (mirrors getIPAddress() in the PHP app) ----------
def get_ip():
    # Client-IP / X-Forwarded-For first (reverse proxy setups), then the
    # direct remote address — same fallback order as the original PHP.
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


# ---------- CSRF ----------
def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def csrf_check():
    submitted = request.form.get("csrf_token", "")
    if not submitted or submitted != session.get("csrf_token"):
        from flask import abort
        abort(403, "Security check failed — please go back, refresh the page, and try again.")


# ---------- login rate-limiting ----------
def is_login_locked_out(identifier):
    row = query_one(
        "SELECT COUNT(*) AS c FROM login_attempts WHERE identifier=%s "
        "AND attempted_at > (NOW() - INTERVAL %s MINUTE)",
        (identifier, LOGIN_ATTEMPT_WINDOW_MINUTES),
    )
    return row["c"] >= LOGIN_ATTEMPT_LIMIT


def record_failed_login(identifier):
    execute("INSERT INTO login_attempts (identifier) VALUES (%s)", (identifier,))


def clear_failed_logins(identifier):
    execute("DELETE FROM login_attempts WHERE identifier=%s", (identifier,))


# ---------- product image paths ----------
def product_image_path(raw_filename):
    clean = (raw_filename or "").strip()
    if not clean:
        return "/static/images/empty.gif"
    return f"/media/products/{clean}"


def user_image_path(raw_filename):
    clean = (raw_filename or "").strip()
    if not clean:
        return "/static/images/empty.gif"
    return f"/media/users/{clean}"


# ---------- catalogue helpers ----------
def get_categories():
    return query_all("SELECT * FROM categories")


def get_brands():
    return query_all("SELECT * FROM brands")


# ---------- cart (guest, keyed by IP — same model as the PHP app) ----------
def get_cart_rows():
    ip = get_ip()
    cart_rows = query_all("SELECT * FROM cart_details WHERE ip_address=%s", (ip,))
    rows = []
    for c in cart_rows:
        product = query_one("SELECT * FROM products WHERE product_id=%s", (c["product_id"],))
        if product:
            product["cart_quantity"] = c["quantity"]
            rows.append(product)
    return rows


def add_to_cart(product_id):
    """Adds a product to the guest/IP-keyed cart. If it's already in the
    bag, bumps the quantity by 1 instead of no-op'ing — so clicking "Add +"
    on the same product repeatedly behaves the way people actually expect."""
    ip = get_ip()
    existing = query_one(
        "SELECT * FROM cart_details WHERE ip_address=%s AND product_id=%s", (ip, product_id)
    )
    if existing:
        new_quantity = max(1, existing["quantity"]) + 1
        execute(
            "UPDATE cart_details SET quantity=%s WHERE ip_address=%s AND product_id=%s",
            (new_quantity, ip, product_id),
        )
        return new_quantity
    execute(
        "INSERT INTO cart_details (product_id, ip_address, quantity) VALUES (%s, %s, 1)",
        (product_id, ip),
    )
    return 1


# ---------- wishlist (DB-backed, tied to the logged-in customer) ----------
def get_wishlist_ids(user_id):
    if not user_id:
        return []
    rows = query_all("SELECT product_id FROM wishlist_details WHERE user_id=%s", (user_id,))
    return [r["product_id"] for r in rows]


def get_logged_in_user_id():
    return session.get("user_id")


def get_logged_in_admin_id():
    return session.get("admin_id")


# ---------- allowed image upload extensions ----------
ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "webp"}


def _cover_crop(img, target_size):
    """Resize + center-crop an image to exactly target_size, filling the
    whole frame without distorting the aspect ratio (like CSS object-fit:
    cover) — so a portrait photo and a wide photo both end up looking
    consistent side by side on the product grid."""
    from PIL import Image
    target_w, target_h = target_size
    target_ratio = target_w / target_h
    src_w, src_h = img.size
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_h = src_h
        new_w = int(src_h * target_ratio)
    else:
        new_w = src_w
        new_h = int(src_w / target_ratio)

    left = (src_w - new_w) // 2
    top = (src_h - new_h) // 2
    img = img.crop((left, top, left + new_w, top + new_h))
    return img.resize(target_size, Image.LANCZOS)


def save_upload(file_storage, dest_dir, target_size=None):
    """Validates and saves an uploaded image with a random filename.
    If target_size=(w, h) is given, the image is resized and center-cropped
    to exactly that size first, so uploads of any original size/aspect
    ratio display consistently (used for product photos, so they don't
    look mismatched on the product grid). Returns the new filename, or
    None if the file failed validation."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in ALLOWED_IMAGE_EXT:
        return None

    from PIL import Image
    try:
        file_storage.stream.seek(0)
        Image.open(file_storage.stream).verify()  # same defense-in-depth as before
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream)
        img.load()
    except Exception:
        return None

    os.makedirs(dest_dir, exist_ok=True)

    if target_size:
        img = _cover_crop(img.convert("RGB"), target_size)
        new_name = secrets.token_hex(8) + ".jpg"
        img.save(os.path.join(dest_dir, new_name), "JPEG", quality=88)
    else:
        new_name = secrets.token_hex(8) + "." + ext
        file_storage.stream.seek(0)
        file_storage.save(os.path.join(dest_dir, new_name))

    return new_name
