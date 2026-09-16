from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import execute, query_all, query_one
from ..helpers import (add_to_cart, get_ip, get_logged_in_user_id,
                       safe_redirect_target)

bp = Blueprint("wishlist", __name__)


@bp.route("/wishlist")
def view():
    user_id = get_logged_in_user_id()
    if not user_id:
        return render_template("storefront/wishlist_login_gate.html")

    products = query_all(
        "SELECT p.* FROM products p "
        "INNER JOIN wishlist_details w ON w.product_id = p.product_id "
        "WHERE w.user_id = %s ORDER BY w.date_added DESC",
        (user_id,),
    )
    return render_template("storefront/wishlist.html", products=products)


@bp.route("/wishlist/add/<int:product_id>")
def add(product_id):
    user_id = get_logged_in_user_id()
    if not user_id:
        return redirect(url_for("auth.login", redirect_wishlist=product_id))
    execute(
        "INSERT IGNORE INTO wishlist_details (user_id, product_id) VALUES (%s, %s)",
        (user_id, product_id),
    )
    return redirect(safe_redirect_target(request.referrer, url_for("wishlist.view")))


@bp.route("/wishlist/remove/<int:product_id>")
def remove(product_id):
    user_id = get_logged_in_user_id()
    if user_id:
        execute(
            "DELETE FROM wishlist_details WHERE user_id=%s AND product_id=%s",
            (user_id, product_id),
        )
        flash("Removed from wishlist")
    return redirect(url_for("wishlist.view"))


@bp.route("/wishlist/move-to-bag/<int:product_id>")
def move_to_bag(product_id):
    user_id = get_logged_in_user_id()
    if not user_id:
        return redirect(url_for("wishlist.view"))

    ip = get_ip()
    already_in_cart = query_one(
        "SELECT 1 FROM cart_details WHERE ip_address=%s AND product_id=%s",
        (ip, product_id),
    )
    if not already_in_cart:
        add_to_cart(product_id)

    execute(
        "DELETE FROM wishlist_details WHERE user_id=%s AND product_id=%s",
        (user_id, product_id),
    )
    flash("Moved to bag")
    return redirect(url_for("wishlist.view"))
