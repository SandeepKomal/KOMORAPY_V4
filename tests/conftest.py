"""
Shared pytest fixtures.

The DB layer (app.db.query_one / query_all / execute) is mocked rather than
hitting a real MySQL instance — this keeps the suite fast, deterministic,
and runnable in CI/SonarQube without needing RDS credentials. Each
blueprint does `from ..db import query_one, ...`, which binds the name
into that module's own namespace, so the mock has to be patched at each
blueprint's import point, not just on app.db itself.
"""
import os
import sys

os.environ.setdefault("DB_HOST", "test-host")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASS", "test-pass")
os.environ.setdefault("DB_NAME", "mystore")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("UPLOAD_ROOT", "/tmp/komora-test-uploads")

import pytest

BLUEPRINT_MODULES = [
    "app.helpers",  # add_to_cart, get_cart_rows, get_wishlist_ids, is_login_locked_out,
                    # record_failed_login, clear_failed_logins, get_categories, get_brands
                    # all live here and import query_one/query_all/execute into this
                    # module's own namespace — miss this one and half the suite would
                    # silently try to hit a real (fake) database instead of the mock.
    "app.blueprints.storefront",
    "app.blueprints.cart",
    "app.blueprints.wishlist",
    "app.blueprints.auth",
    "app.blueprints.checkout",
    "app.blueprints.admin",
]


@pytest.fixture
def mock_db(mocker):
    """Patches query_one/query_all/execute everywhere they're imported.
    Returns the three MagicMocks so a test can set .return_value /
    .side_effect on them directly.

    Note on side_effect lists and the global context processor: every
    page render also triggers app/__init__.py's inject_globals(), which
    calls get_cart_rows()/get_categories()/get_brands()/get_wishlist_ids()
    — these run AFTER a view function's own query_one/query_all calls
    (they fire during render_template(), at the very end of the view),
    so a side_effect list sized to just the view's own expected calls is
    safe UNLESS the context processor itself needs more values than are
    left. If it runs out, inject_globals()'s own try/except silently
    swallows the StopIteration and falls back to an empty cart/wishlist
    for that render — it will not fail your test, but it does mean the
    header's cart/wishlist badge counts won't reflect real data in tests
    that don't over-provision their side_effect list. Pad the list with
    a few extra entries (or use return_value instead of side_effect)
    if a test specifically needs the header badges to be accurate too.
    """
    query_one = mocker.MagicMock(return_value=None)
    query_all = mocker.MagicMock(return_value=[])
    execute = mocker.MagicMock(return_value=(1, 1))

    for module in BLUEPRINT_MODULES:
        mocker.patch(f"{module}.query_one", query_one, create=True)
        mocker.patch(f"{module}.query_all", query_all, create=True)
        mocker.patch(f"{module}.execute", execute, create=True)

    return {"query_one": query_one, "query_all": query_all, "execute": execute}


@pytest.fixture
def app(mock_db):
    from app import create_app
    flask_app = create_app()
    flask_app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_product():
    """A representative product row, matching the real products schema
    (including Decimal-typed price, the actual type PyMySQL returns for
    a DECIMAL column — a real source of bugs a naive int/float stub
    would never catch)."""
    from decimal import Decimal
    return {
        "product_id": 1, "product_title": "Test Product",
        "product_description": "A test product", "product_keywords": "test",
        "category_id": 1, "brand_id": 1,
        "product_image1": "test1.jpg", "product_image2": "", "product_image3": "",
        "price": Decimal("1999.00"), "status": "true",
    }


@pytest.fixture
def sample_customer():
    return {
        "user_id": 1, "username": "testuser", "user_email": "test@example.com",
        "user_password": "$2b$12$fakehashfakehashfakehashfakehashfakehashfake",
        "user_address": "123 Test St", "user_mobile": "9999999999",
        "user_image": "", "user_ip": "127.0.0.1",
    }


@pytest.fixture
def sample_admin():
    return {
        "admin_id": 1, "admin_username": "testadmin", "admin_email": "admin@example.com",
        "admin_password": "$2b$12$fakehashfakehashfakehashfakehashfakehashfake",
        "admin_image": "",
    }


@pytest.fixture
def logged_in_customer(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "testuser"
    return client


@pytest.fixture
def logged_in_admin(client):
    with client.session_transaction() as sess:
        sess["admin_id"] = 1
        sess["admin_username"] = "testadmin"
    return client


def get_csrf_token(client, path):
    """Loads a GET page and pulls the csrf_token hidden field out of it —
    every POST test needs a real token or csrf_check() will 403 it."""
    import re
    resp = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', resp.data.decode())
    assert match, f"No csrf_token found on {path}"
    return match.group(1)
