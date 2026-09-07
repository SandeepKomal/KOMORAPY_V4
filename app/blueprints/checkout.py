import random
from flask import Blueprint, render_template, redirect, url_for, request, session, flash

from ..db import query_one, query_all, execute
from ..helpers import get_ip, get_logged_in_user_id, csrf_check, product_image_path

bp = Blueprint("checkout", __name__)


def _cart_line_items():
    ip = get_ip()
    cart_lines = query_all("SELECT * FROM cart_details WHERE ip_address=%s", (ip,))
    items = []
    total = 0
    for line in cart_lines:
        product = query_one("SELECT * FROM products WHERE product_id=%s", (line["product_id"],))
        if not product:
            continue
        quantity = max(1, line["quantity"])
        product["quantity"] = quantity
        product["line_total"] = product["price"] * quantity
        total += product["line_total"]
        items.append(product)
    return items, total


@bp.route("/checkout/address", methods=["GET", "POST"])
def address():
    user_id = get_logged_in_user_id()
    if not user_id:
        return redirect(url_for("auth.login", next="cart"))

    items, total = _cart_line_items()
    if not items:
        flash("Your bag is empty.")
        return redirect(url_for("cart.view"))

    user = query_one(
        "SELECT user_address, user_mobile FROM user_table WHERE user_id=%s", (user_id,)
    )
    saved_address = (user["user_address"] or "").strip()
    saved_mobile = (user["user_mobile"] or "").strip()

    if request.method == "POST":
        csrf_check()
        choice = request.form.get("address_choice", "new")
        if choice == "saved" and saved_address:
            final_address, final_mobile = saved_address, saved_mobile
        else:
            final_address = request.form.get("address", "").strip()
            final_mobile = request.form.get("mobile", "").strip()

        if not final_address or not final_mobile:
            flash("Please fill in both fields.", "error")
        else:
            execute(
                "UPDATE user_table SET user_address=%s, user_mobile=%s WHERE user_id=%s",
                (final_address, final_mobile, user_id),
            )
            session["checkout_address"] = final_address
            session["checkout_mobile"] = final_mobile
            return redirect(url_for("checkout.payment"))

    return render_template(
        "storefront/address.html",
        items=items, saved_address=saved_address, saved_mobile=saved_mobile,
    )


@bp.route("/checkout/payment", methods=["GET", "POST"])
def payment():
    user_id = get_logged_in_user_id()
    if not user_id:
        return redirect(url_for("auth.login", next="cart"))
    if "checkout_address" not in session:
        return redirect(url_for("checkout.address"))

    items, total = _cart_line_items()
    if not items:
        flash("Your bag is empty.")
        return redirect(url_for("cart.view"))

    if request.method == "POST":
        csrf_check()
        payment_mode = request.form.get("payment_mode", "")
        if not payment_mode:
            flash("Please select a payment mode.", "error")
        else:
            invoice_number = random.randint(100000, 999999999)
            for item in items:
                _, order_id = execute(
                    "INSERT INTO user_orders (user_id, amount_due, invoice_number, "
                    "total_products, order_date, order_status, product_id) "
                    "VALUES (%s, %s, %s, %s, NOW(), 'Complete', %s)",
                    (user_id, item["line_total"], invoice_number, item["quantity"], item["product_id"]),
                )
                execute(
                    "INSERT INTO orders_pending (user_id, invoice_number, product_id, "
                    "quantity, order_status) VALUES (%s, %s, %s, %s, 'Complete')",
                    (user_id, invoice_number, item["product_id"], item["quantity"]),
                )
                execute(
                    "INSERT INTO user_payments (order_id, invoice_number, amount, payment_mode) "
                    "VALUES (%s, %s, %s, %s)",
                    (order_id, invoice_number, item["line_total"], payment_mode),
                )

            ip = get_ip()
            execute("DELETE FROM cart_details WHERE ip_address=%s", (ip,))
            session.pop("checkout_address", None)
            session.pop("checkout_mobile", None)

            flash(f"Order placed and paid — invoice #{invoice_number}")
            return redirect(url_for("checkout.orders"))

    return render_template(
        "storefront/payment.html",
        items=items, total=total,
        checkout_address=session.get("checkout_address"),
        checkout_mobile=session.get("checkout_mobile"),
    )


@bp.route("/orders")
def orders():
    user_id = get_logged_in_user_id()
    if not user_id:
        return redirect(url_for("auth.login"))
    rows = query_all(
        "SELECT uo.*, p.product_title, p.product_image1 FROM user_orders uo "
        "LEFT JOIN products p ON p.product_id = uo.product_id "
        "WHERE uo.user_id=%s ORDER BY uo.order_date DESC",
        (user_id,),
    )
    return render_template("storefront/orders.html", rows=rows)
