import bcrypt
from flask import Blueprint, render_template, redirect, url_for, request, session, flash

from ..db import query_one, query_all, execute
from ..helpers import (
    csrf_check, get_ip, is_login_locked_out, record_failed_login, clear_failed_logins,
    get_logged_in_user_id,
)

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    redirect_wishlist = request.values.get("redirect_wishlist", type=int)
    next_dest = request.values.get("next")  # "cart" or "wishlist" — where to land after login

    if request.method == "POST":
        csrf_check()
        username = request.form["username"]
        password = request.form["password"]
        identifier = username.strip().lower()

        if identifier and is_login_locked_out(identifier):
            flash("Too many failed attempts. Please wait a few minutes and try again.", "error")
        else:
            user = query_one("SELECT * FROM user_table WHERE username=%s", (username,))
            if user and bcrypt.checkpw(password.encode(), user["user_password"].encode()):
                clear_failed_logins(identifier)
                session.clear()
                session["user_id"] = user["user_id"]
                session["username"] = user["username"]

                if redirect_wishlist:
                    execute(
                        "INSERT IGNORE INTO wishlist_details (user_id, product_id) VALUES (%s, %s)",
                        (user["user_id"], redirect_wishlist),
                    )
                    flash("Saved to your wishlist")
                    return redirect(url_for("wishlist.view"))

                if next_dest == "cart":
                    return redirect(url_for("cart.view"))
                if next_dest == "wishlist":
                    return redirect(url_for("wishlist.view"))

                ip = get_ip()
                has_cart_items = query_one(
                    "SELECT 1 FROM cart_details WHERE ip_address=%s", (ip,)
                )
                if has_cart_items:
                    return redirect(url_for("checkout.payment"))
                return redirect(url_for("storefront.index"))
            else:
                if identifier:
                    record_failed_login(identifier)
                flash("Invalid username or password", "error")

    return render_template(
        "auth/login.html", redirect_wishlist=redirect_wishlist, next_dest=next_dest
    )


@bp.route("/register", methods=["GET", "POST"])
def register():
    redirect_wishlist = request.values.get("redirect_wishlist", type=int)

    if request.method == "POST":
        csrf_check()
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        address = request.form.get("address", "").strip()
        mobile = request.form.get("mobile", "").strip()

        existing = query_one(
            "SELECT username, user_email, user_mobile FROM user_table "
            "WHERE username=%s OR user_email=%s OR user_mobile=%s",
            (username, email, mobile),
        )

        if existing:
            if existing["username"] == username:
                flash("That username is already taken", "error")
            elif existing["user_email"] == email:
                flash("An account with that email already exists", "error")
            else:
                flash("An account with that phone number already exists", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters", "error")
        elif password != confirm_password:
            flash("Passwords don't match", "error")
        else:
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            ip = get_ip()
            _, new_user_id = execute(
                "INSERT INTO user_table (username, user_email, user_password, user_image, "
                "user_ip, user_address, user_mobile) VALUES (%s, %s, %s, '', %s, %s, %s)",
                (username, email, hashed, ip, address, mobile),
            )

            if redirect_wishlist:
                execute(
                    "INSERT IGNORE INTO wishlist_details (user_id, product_id) VALUES (%s, %s)",
                    (new_user_id, redirect_wishlist),
                )
                flash("Account created and saved to your wishlist — log in to see it")
                return redirect(url_for("auth.login", redirect_wishlist=redirect_wishlist))

            flash("Account created — log in to continue")
            return redirect(url_for("auth.login"))

    return render_template("auth/register.html", redirect_wishlist=redirect_wishlist)


@bp.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return redirect(url_for("storefront.index"))


@bp.route("/profile/edit", methods=["GET", "POST"])
def profile_edit():
    user_id = get_logged_in_user_id()
    if not user_id:
        return redirect(url_for("auth.login"))

    user = query_one("SELECT * FROM user_table WHERE user_id=%s", (user_id,))

    if request.method == "POST":
        csrf_check()
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        address = request.form.get("address", "").strip()
        mobile = request.form.get("mobile", "").strip()

        # same uniqueness check used at registration, excluding this
        # account's own current row so you can save without changing
        # a field and have it flag itself as "already taken"
        existing = query_one(
            "SELECT username, user_email, user_mobile FROM user_table "
            "WHERE (username=%s OR user_email=%s OR user_mobile=%s) AND user_id != %s",
            (username, email, mobile, user_id),
        )

        if existing:
            if existing["username"] == username:
                flash("That username is already taken", "error")
            elif existing["user_email"] == email:
                flash("An account with that email already exists", "error")
            else:
                flash("An account with that phone number already exists", "error")
            user = dict(user, username=username, user_email=email, user_address=address, user_mobile=mobile)
        else:
            execute(
                "UPDATE user_table SET username=%s, user_email=%s, user_address=%s, user_mobile=%s WHERE user_id=%s",
                (username, email, address, mobile, user_id),
            )
            session["username"] = username  # keep session in sync if it changed
            flash("Profile updated")
            return redirect(url_for("auth.profile_edit"))

    return render_template("auth/profile_edit.html", user=user)


@bp.route("/contact")
def contact():
    return render_template("auth/contact.html")
