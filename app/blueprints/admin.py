import functools
import bcrypt
from flask import Blueprint, render_template, redirect, url_for, request, session, flash, abort

from ..db import query_one, query_all, execute
from ..helpers import (
    csrf_check, is_login_locked_out, record_failed_login, clear_failed_logins,
    save_upload, get_logged_in_admin_id,
)
from flask import current_app

bp = Blueprint("admin", __name__)

# Product photos are normalized to this size (4:5, matching the product
# card's aspect-ratio in CSS) so uploads of any original size/shape display
# consistently on the grid instead of looking mismatched next to each other.
PRODUCT_IMAGE_SIZE = (800, 1000)

_NAV_BY_ENDPOINT = {
    "admin.dashboard": "dashboard",
    "admin.products": "products", "admin.product_edit": "products",
    "admin.product_new": "insert_product",
    "admin.categories": "categories", "admin.category_new": "categories", "admin.category_edit": "categories",
    "admin.brands": "brands", "admin.brand_new": "brands", "admin.brand_edit": "brands",
    "admin.orders": "orders",
    "admin.payments": "payments",
    "admin.users": "users",
    "admin.database": "database",
}


@bp.context_processor
def inject_active_nav():
    return dict(active_nav=_NAV_BY_ENDPOINT.get(request.endpoint))


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not get_logged_in_admin_id():
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


# ---------- auth ----------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        csrf_check()
        username = request.form["username"]
        password = request.form["password"]
        identifier = "admin:" + username.strip().lower()

        if identifier != "admin:" and is_login_locked_out(identifier):
            flash("Too many failed attempts. Please wait a few minutes and try again.", "error")
        else:
            admin = query_one("SELECT * FROM admin_table WHERE admin_username=%s", (username,))
            if admin and bcrypt.checkpw(password.encode(), admin["admin_password"].encode()):
                clear_failed_logins(identifier)
                session.clear()
                session["admin_id"] = admin["admin_id"]
                session["admin_username"] = admin["admin_username"]
                return redirect(url_for("admin.dashboard"))
            else:
                record_failed_login(identifier)
                flash("Invalid username or password", "error")

    return render_template("admin/login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        csrf_check()
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        existing = query_one(
            "SELECT * FROM admin_table WHERE admin_username=%s OR admin_email=%s",
            (username, email),
        )
        if existing:
            flash("An admin with that username or email already exists", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters", "error")
        elif password != confirm_password:
            flash("Passwords don't match", "error")
        else:
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            execute(
                "INSERT INTO admin_table (admin_username, admin_email, admin_password, admin_image) "
                "VALUES (%s, %s, %s, '')",
                (username, email, hashed),
            )
            flash("Admin account created — log in to continue")
            return redirect(url_for("admin.login"))

    return render_template("admin/register.html")


@bp.route("/logout")
def logout():
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    return redirect(url_for("admin.login"))


# ---------- dashboard ----------
@bp.route("/")
@admin_required
def dashboard():
    return render_template("admin/dashboard.html")


# ---------- products ----------
@bp.route("/products")
@admin_required
def products():
    rows = query_all(
        "SELECT p.*, (SELECT COUNT(*) FROM orders_pending op WHERE op.product_id = p.product_id) "
        "AS units_sold FROM products p"
    )
    return render_template("admin/products.html", rows=rows)


@bp.route("/products/new", methods=["GET", "POST"])
@admin_required
def product_new():
    categories = query_all("SELECT * FROM categories")
    brands = query_all("SELECT * FROM brands")

    if request.method == "POST":
        csrf_check()
        title = request.form["title"]
        description = request.form["description"]
        keywords = request.form["keywords"]
        category_id = request.form.get("category_id", type=int)
        brand_id = request.form.get("brand_id", type=int)
        price = request.form.get("price", type=int)

        img_dir = current_app.config["PRODUCT_IMAGE_DIR"]
        image1 = save_upload(request.files.get("image1"), img_dir, target_size=PRODUCT_IMAGE_SIZE)
        image2 = save_upload(request.files.get("image2"), img_dir, target_size=PRODUCT_IMAGE_SIZE) or ""
        image3 = save_upload(request.files.get("image3"), img_dir, target_size=PRODUCT_IMAGE_SIZE) or ""

        if not all([title, description, keywords, category_id, brand_id, price, image1]):
            flash("Please fill in all fields and choose a valid main image", "error")
        else:
            execute(
                "INSERT INTO products (product_title, product_description, product_keywords, "
                "category_id, brand_id, product_image1, product_image2, product_image3, price, "
                "date, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),'true')",
                (title, description, keywords, category_id, brand_id, image1, image2, image3, price),
            )
            flash("Product added")
            return redirect(url_for("admin.products"))

    return render_template("admin/product_form.html", categories=categories, brands=brands, product=None)


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_edit(product_id):
    product = query_one("SELECT * FROM products WHERE product_id=%s", (product_id,))
    if not product:
        abort(404)
    categories = query_all("SELECT * FROM categories")
    brands = query_all("SELECT * FROM brands")

    if request.method == "POST":
        csrf_check()
        title = request.form["title"]
        description = request.form["description"]
        keywords = request.form["keywords"]
        category_id = request.form.get("category_id", type=int)
        brand_id = request.form.get("brand_id", type=int)
        price = request.form.get("price", type=int)

        img_dir = current_app.config["PRODUCT_IMAGE_DIR"]
        image1 = save_upload(request.files.get("image1"), img_dir, target_size=PRODUCT_IMAGE_SIZE) or product["product_image1"]
        image2 = save_upload(request.files.get("image2"), img_dir, target_size=PRODUCT_IMAGE_SIZE) or product["product_image2"]
        image3 = save_upload(request.files.get("image3"), img_dir, target_size=PRODUCT_IMAGE_SIZE) or product["product_image3"]

        execute(
            "UPDATE products SET product_title=%s, product_description=%s, product_keywords=%s, "
            "category_id=%s, brand_id=%s, product_image1=%s, product_image2=%s, product_image3=%s, "
            "price=%s, date=NOW() WHERE product_id=%s",
            (title, description, keywords, category_id, brand_id, image1, image2, image3, price, product_id),
        )
        flash("Product updated")
        return redirect(url_for("admin.products"))

    return render_template("admin/product_form.html", categories=categories, brands=brands, product=product)


@bp.route("/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def product_delete(product_id):
    csrf_check()
    execute("DELETE FROM products WHERE product_id=%s", (product_id,))
    flash("Product deleted")
    return redirect(url_for("admin.products"))


# ---------- categories ----------
@bp.route("/categories")
@admin_required
def categories():
    rows = query_all("SELECT * FROM categories")
    return render_template("admin/categories.html", rows=rows)


@bp.route("/categories/new", methods=["GET", "POST"])
@admin_required
def category_new():
    if request.method == "POST":
        csrf_check()
        title = request.form["title"].strip()
        existing = query_one("SELECT 1 FROM categories WHERE category_title=%s", (title,))
        if existing:
            flash("This category already exists", "error")
        else:
            execute("INSERT INTO categories (category_title) VALUES (%s)", (title,))
            flash("Category added")
            return redirect(url_for("admin.categories"))
    return render_template("admin/category_form.html", category=None)


@bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@admin_required
def category_edit(category_id):
    category = query_one("SELECT * FROM categories WHERE category_id=%s", (category_id,))
    if not category:
        abort(404)
    if request.method == "POST":
        csrf_check()
        title = request.form["title"].strip()
        execute("UPDATE categories SET category_title=%s WHERE category_id=%s", (title, category_id))
        flash("Category updated")
        return redirect(url_for("admin.categories"))
    return render_template("admin/category_form.html", category=category)


@bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@admin_required
def category_delete(category_id):
    csrf_check()
    execute("DELETE FROM categories WHERE category_id=%s", (category_id,))
    flash("Category deleted")
    return redirect(url_for("admin.categories"))


# ---------- brands ----------
@bp.route("/brands")
@admin_required
def brands():
    rows = query_all("SELECT * FROM brands")
    return render_template("admin/brands.html", rows=rows)


@bp.route("/brands/new", methods=["GET", "POST"])
@admin_required
def brand_new():
    if request.method == "POST":
        csrf_check()
        title = request.form["title"].strip()
        existing = query_one("SELECT 1 FROM brands WHERE brand_title=%s", (title,))
        if existing:
            flash("This brand already exists", "error")
        else:
            execute("INSERT INTO brands (brand_title) VALUES (%s)", (title,))
            flash("Brand added")
            return redirect(url_for("admin.brands"))
    return render_template("admin/brand_form.html", brand=None)


@bp.route("/brands/<int:brand_id>/edit", methods=["GET", "POST"])
@admin_required
def brand_edit(brand_id):
    brand = query_one("SELECT * FROM brands WHERE brand_id=%s", (brand_id,))
    if not brand:
        abort(404)
    if request.method == "POST":
        csrf_check()
        title = request.form["title"].strip()
        execute("UPDATE brands SET brand_title=%s WHERE brand_id=%s", (title, brand_id))
        flash("Brand updated")
        return redirect(url_for("admin.brands"))
    return render_template("admin/brand_form.html", brand=brand)


@bp.route("/brands/<int:brand_id>/delete", methods=["POST"])
@admin_required
def brand_delete(brand_id):
    csrf_check()
    execute("DELETE FROM brands WHERE brand_id=%s", (brand_id,))
    flash("Brand deleted")
    return redirect(url_for("admin.brands"))


# ---------- orders / payments / users ----------
@bp.route("/orders")
@admin_required
def orders():
    rows = query_all("SELECT * FROM user_orders ORDER BY order_date DESC")
    return render_template("admin/orders.html", rows=rows)


@bp.route("/orders/<int:order_id>/delete", methods=["POST"])
@admin_required
def order_delete(order_id):
    csrf_check()
    execute("DELETE FROM user_orders WHERE order_id=%s", (order_id,))
    flash("Order deleted")
    return redirect(url_for("admin.orders"))


@bp.route("/payments")
@admin_required
def payments():
    rows = query_all("SELECT * FROM user_payments ORDER BY date DESC")
    return render_template("admin/payments.html", rows=rows)


@bp.route("/users")
@admin_required
def users():
    rows = query_all("SELECT * FROM user_table")
    return render_template("admin/users.html", rows=rows)


# ---------- DB browser (read-only, passwords always excluded) ----------
TABLES = {
    "admin_table": {"label": "Admins", "cols": ["admin_id", "admin_username", "admin_email"]},
    "user_table": {"label": "Users", "cols": ["user_id", "username", "user_email", "user_address", "user_mobile", "user_ip"]},
    "products": {"label": "Products", "cols": ["product_id", "product_title", "category_id", "brand_id", "price", "status", "date"]},
    "categories": {"label": "Categories", "cols": ["category_id", "category_title"]},
    "brands": {"label": "Brands", "cols": ["brand_id", "brand_title"]},
    "cart_details": {"label": "Cart items", "cols": ["product_id", "ip_address", "quantity"]},
    "user_orders": {"label": "Orders", "cols": ["order_id", "user_id", "product_id", "amount_due", "invoice_number", "total_products", "order_date", "order_status"]},
    "user_payments": {"label": "Payments", "cols": ["payment_id", "order_id", "invoice_number", "amount", "payment_mode", "date"]},
    "orders_pending": {"label": "Orders pending", "cols": ["id", "user_id", "invoice_number", "product_id", "quantity", "order_status"]},
    "wishlist_details": {"label": "Wishlist", "cols": ["wishlist_id", "user_id", "product_id", "date_added"]},
    "login_attempts": {"label": "Login attempts", "cols": ["id", "identifier", "attempted_at"]},
}


@bp.route("/database")
@admin_required
def database():
    active_table = request.args.get("table", "admin_table")
    if active_table not in TABLES:
        active_table = "admin_table"
    cols = TABLES[active_table]["cols"]

    col_list = ", ".join(f"`{c}`" for c in cols)
    rows = query_all(f"SELECT {col_list} FROM `{active_table}`")  # noqa: S608 — table/cols are whitelisted above, never user input directly

    counts = {}
    for t in TABLES:
        row = query_one(f"SELECT COUNT(*) AS c FROM `{t}`")  # noqa: S608 — t comes from the TABLES dict, not request input
        counts[t] = row["c"]

    return render_template(
        "admin/database.html",
        tables=TABLES, active_table=active_table, cols=cols, rows=rows, counts=counts,
    )
