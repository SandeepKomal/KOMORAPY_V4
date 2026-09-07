from flask import Blueprint, render_template, request

from ..db import query_one, query_all
from ..helpers import get_wishlist_ids, get_logged_in_user_id

bp = Blueprint("storefront", __name__)


@bp.route("/")
def index():
    products = query_all("SELECT * FROM products ORDER BY RAND() LIMIT 24")
    return render_template("storefront/index.html", products=products)


@bp.route("/products")
def all_products():
    category_id = request.args.get("category", type=int)
    brand_id = request.args.get("brand", type=int)

    sql = "SELECT * FROM products"
    where = []
    params = []
    if category_id:
        where.append("category_id=%s")
        params.append(category_id)
    if brand_id:
        where.append("brand_id=%s")
        params.append(brand_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY RAND()"

    products = query_all(sql, tuple(params))
    return render_template(
        "storefront/catalogue.html",
        title="All products",
        products=products,
        active_category=category_id,
        active_brand=brand_id,
    )


@bp.route("/search")
def search():
    q = request.args.get("q", "").strip()
    products = []
    searched = "q" in request.args
    if searched and q:
        products = query_all(
            "SELECT * FROM products WHERE product_keywords LIKE %s", (f"%{q}%",)
        )
    return render_template(
        "storefront/catalogue.html",
        title=f"Search: {q}" if q else "Search",
        products=products,
        searched=searched,
        query=q,
        active_category=None,
        active_brand=None,
    )


@bp.route("/product/<int:product_id>")
def product_details(product_id):
    product = query_one("SELECT * FROM products WHERE product_id=%s", (product_id,))
    if not product:
        from flask import abort
        abort(404)
    category = query_one("SELECT * FROM categories WHERE category_id=%s", (product["category_id"],))
    brand = query_one("SELECT * FROM brands WHERE brand_id=%s", (product["brand_id"],))
    related = query_all(
        "SELECT * FROM products WHERE category_id=%s AND product_id != %s LIMIT 4",
        (product["category_id"], product_id),
    )
    return render_template(
        "storefront/product_details.html",
        product=product, category=category, brand=brand, related=related,
    )
