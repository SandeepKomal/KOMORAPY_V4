# KOMORA — Flask port

A from-scratch rewrite of the PHP KOMORA storefront/admin app in Flask,
against the **same RDS MySQL database** — same tables, same data, no
migration needed. Existing user/admin accounts and their bcrypt password
hashes work as-is; nobody needs to re-register.

## What this is

- Flask (blueprints per feature area: storefront, cart, wishlist, auth,
  checkout, admin) instead of one PHP file per URL
- Raw SQL via PyMySQL, not an ORM — every query is a direct, faithful
  translation of the working PHP queries, not a redesign
- Jinja2 templates with real inheritance (`{% extends %}`), replacing the
  PHP `include()`-per-page pattern
- `komora.css`/`komora.js` carried over unchanged — those were never PHP
- Same security posture as the final PHP version: CSRF tokens on every
  state-changing form, session-isolated admin/customer accounts, rate-limited
  login (5 attempts / 15 minutes), hardened session cookies, no stack traces
  shown to visitors

## Setup

```bash
cp .env.example .env
# fill in DB_HOST/DB_USER/DB_PASS (same RDS instance as before) and a
# real SECRET_KEY: python3 -c "import secrets; print(secrets.token_hex(32))"

docker compose up -d --build
```

Visit `http://<your-server>:8080`.

## Uploaded images

Product and user images live in `uploads/products/` and `uploads/users/`
on the host, bind-mounted into the container — same idea as the PHP app's
`admin_area/product_images`/`users_area/user_images` volumes. **Copy your
actual current images from those PHP directories into the matching
`uploads/` folders here** before relying on this — a handful of sample
images are included, but your live product catalogue almost certainly has
more than what's bundled.

## What's been tested, and what hasn't

Every route was smoke-tested with Flask's test client against a fake
database (checking that every page renders without error, CSRF is enforced
correctly, `url_for()` references all resolve) — but **not against your
actual RDS instance or in a real browser**. Treat this as a solid first
draft: run it, click through every flow (browse → cart → wishlist →
checkout → admin CRUD), and expect to find and report a handful of real
bugs before this is production-ready. That's normal for a rewrite this
size, not a sign something went wrong.

## Known gaps vs. the PHP version

- No equivalent of PHP's `.htaccess`-based upload-directory script-blocking
  — less relevant here since Python's WSGI server doesn't auto-execute
  arbitrary files dropped into a directory the way Apache+mod_php does, but
  worth knowing this protection wasn't recreated, just made less necessary.
- The admin "Users" page dropped the "Delete" action — the PHP version's
  equivalent (`delete_users.php`) was an empty, non-functional stub to begin
  with, so there was nothing working to actually port.
