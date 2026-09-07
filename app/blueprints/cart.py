from flask import Blueprint, render_template, redirect, url_for, request, session, flash

from ..db import query_one, execute
from ..helpers import get_ip, get_cart_rows, add_to_cart, csrf_check, get_logged_in_user_id

bp = Blueprint("cart", __name__)


@bp.route("/cart/add/<int:product_id>")
def add(product_id):
    new_quantity = add_to_cart(product_id)
    if new_quantity > 1:
        flash(f"Bag updated — now {new_quantity} in your bag")
    else:
        flash("Added to your bag")
    return redirect(request.referrer or url_for("storefront.index"))


@bp.route("/cart", methods=["GET", "POST"])
def view():
    # Viewing the bag requires login (adding to it doesn't) — same
    # deliberate choice made in the PHP app's later iteration.
    if not get_logged_in_user_id():
        return redirect(url_for("auth.login", next="cart"))

    ip = get_ip()

    if request.method == "POST":
        csrf_check()

        # "Update" was clicked on one specific row — its button's value is
        # that row's product_id, and its quantity field is scoped to that
        # same id so it can never be confused with any other row's field.
        if "update_cart" in request.form:
            product_id = request.form.get("update_cart", type=int)
            quantity = max(1, request.form.get(f"quantity_{product_id}", type=int, default=1))
            execute(
                "UPDATE cart_details SET quantity=%s WHERE ip_address=%s AND product_id=%s",
                (quantity, ip, product_id),
            )
            flash("Bag updated")
            return redirect(url_for("cart.view"))

        # "Remove selected" — one or more checkboxes, all named remove_item.
        if "remove_cart" in request.form:
            remove_ids = request.form.getlist("remove_item", type=int)
            for product_id in remove_ids:
                execute(
                    "DELETE FROM cart_details WHERE ip_address=%s AND product_id=%s",
                    (ip, product_id),
                )
            flash("Removed from bag" if remove_ids else "Select at least one item to remove")
            return redirect(url_for("cart.view"))

    rows = get_cart_rows()
    total = 0
    for r in rows:
        qty = max(1, r["cart_quantity"])
        r["line_total"] = r["price"] * qty
        total += r["line_total"]
    return render_template("storefront/cart.html", rows=rows, total=total)
