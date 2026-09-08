import bcrypt
from decimal import Decimal
from .conftest import get_csrf_token


def _hash(pw):
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


class TestAdminAuth:
    def test_login_page_loads(self, client):
        resp = client.get("/admin/login")
        assert resp.status_code == 200

    def test_successful_login_uses_separate_session_key_from_customers(self, client, mock_db, sample_admin):
        sample_admin["admin_password"] = _hash("adminpass")
        mock_db["query_one"].side_effect = [{"c": 0}, sample_admin]

        token = get_csrf_token(client, "/admin/login")
        resp = client.post("/admin/login", data={
            "username": "testadmin", "password": "adminpass", "csrf_token": token,
        }, follow_redirects=False)
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert sess["admin_id"] == 1
            assert "user_id" not in sess  # must never collide with the customer session key

    def test_admin_rate_limited_independently_of_customer_login(self, client, mock_db, sample_admin):
        """Regression test for the privilege-separation fix: admin lockouts
        must be tracked under an 'admin:' prefixed identifier, distinct
        from a customer with the same username."""
        sample_admin["admin_password"] = _hash("adminpass")
        mock_db["query_one"].side_effect = [{"c": 5}]  # locked out
        token = get_csrf_token(client, "/admin/login")
        resp = client.post("/admin/login", data={
            "username": "testadmin", "password": "adminpass", "csrf_token": token,
        })
        assert b"Too many failed attempts" in resp.data
        # confirm the identifier passed to the lockout check is prefixed
        lockout_call = mock_db["query_one"].call_args_list[0]
        assert lockout_call[0][1][0] == "admin:testadmin"

    def test_logout_clears_only_admin_session(self, logged_in_admin):
        resp = logged_in_admin.get("/admin/logout", follow_redirects=False)
        assert resp.status_code == 302
        with logged_in_admin.session_transaction() as sess:
            assert "admin_id" not in sess

    def test_dashboard_requires_admin_login(self, client):
        resp = client.get("/admin/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_customer_session_alone_cannot_reach_admin_dashboard(self, logged_in_customer):
        """Critical regression test for the privilege-escalation bug fixed
        earlier: a logged-in customer must NOT be able to access the admin
        panel just because *some* session exists."""
        resp = logged_in_customer.get("/admin/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]


class TestAdminRegister:
    def test_register_page_loads(self, client):
        resp = client.get("/admin/register")
        assert resp.status_code == 200

    def test_successful_registration(self, client, mock_db):
        mock_db["query_one"].return_value = None
        token = get_csrf_token(client, "/admin/register")
        resp = client.post("/admin/register", data={
            "username": "newadmin", "email": "newadmin@example.com",
            "password": "longenoughpw", "confirm_password": "longenoughpw",
            "csrf_token": token,
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/admin/login")

    def test_duplicate_admin_rejected(self, client, mock_db, sample_admin):
        mock_db["query_one"].return_value = sample_admin
        token = get_csrf_token(client, "/admin/register")
        resp = client.post("/admin/register", data={
            "username": "testadmin", "email": "x@example.com",
            "password": "longenoughpw", "confirm_password": "longenoughpw",
            "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"already exists" in resp.data


class TestProductCRUD:
    def test_list_requires_login(self, client):
        resp = client.get("/admin/products", follow_redirects=False)
        assert resp.status_code == 302

    def test_list_loads_for_admin(self, logged_in_admin, mock_db, sample_product):
        mock_db["query_all"].return_value = [dict(sample_product, units_sold=3)]
        resp = logged_in_admin.get("/admin/products")
        assert resp.status_code == 200
        assert b"Test Product" in resp.data

    def test_new_product_form_loads(self, logged_in_admin, mock_db):
        mock_db["query_all"].return_value = []
        resp = logged_in_admin.get("/admin/products/new")
        assert resp.status_code == 200

    def test_delete_requires_csrf(self, logged_in_admin, mock_db):
        resp = logged_in_admin.post("/admin/products/1/delete", data={})
        assert resp.status_code == 403

    def test_delete_removes_product(self, logged_in_admin, mock_db):
        token = get_csrf_token(logged_in_admin, "/admin/products")
        resp = logged_in_admin.post("/admin/products/1/delete", data={"csrf_token": token}, follow_redirects=False)
        assert resp.status_code == 302
        assert mock_db["execute"].called


class TestCategoryCRUD:
    def test_list_loads(self, logged_in_admin, mock_db):
        mock_db["query_all"].return_value = [{"category_id": 1, "category_title": "Shoes"}]
        resp = logged_in_admin.get("/admin/categories")
        assert resp.status_code == 200
        assert b"Shoes" in resp.data

    def test_insert_rejects_duplicate(self, logged_in_admin, mock_db):
        mock_db["query_one"].return_value = {"category_id": 1}  # already exists
        token = get_csrf_token(logged_in_admin, "/admin/categories/new")
        resp = logged_in_admin.post("/admin/categories/new", data={
            "title": "Shoes", "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"already exists" in resp.data

    def test_insert_succeeds_when_new(self, logged_in_admin, mock_db):
        mock_db["query_one"].return_value = None
        token = get_csrf_token(logged_in_admin, "/admin/categories/new")
        resp = logged_in_admin.post("/admin/categories/new", data={
            "title": "New Category", "csrf_token": token,
        }, follow_redirects=False)
        assert resp.status_code == 302


class TestBrandCRUD:
    def test_list_loads(self, logged_in_admin, mock_db):
        mock_db["query_all"].return_value = [{"brand_id": 1, "brand_title": "Nike"}]
        resp = logged_in_admin.get("/admin/brands")
        assert resp.status_code == 200
        assert b"Nike" in resp.data


class TestOrdersPaymentsUsers:
    def test_orders_list_requires_login(self, client):
        resp = client.get("/admin/orders", follow_redirects=False)
        assert resp.status_code == 302

    def test_orders_list_loads(self, logged_in_admin, mock_db):
        mock_db["query_all"].return_value = [{
            "order_id": 1, "amount_due": Decimal("500"), "invoice_number": 111,
            "total_products": 1, "order_date": "2026-01-01", "order_status": "Complete",
        }]
        resp = logged_in_admin.get("/admin/orders")
        assert resp.status_code == 200

    def test_payments_list_loads(self, logged_in_admin, mock_db):
        mock_db["query_all"].return_value = []
        resp = logged_in_admin.get("/admin/payments")
        assert resp.status_code == 200

    def test_users_list_loads(self, logged_in_admin, mock_db):
        mock_db["query_all"].return_value = []
        resp = logged_in_admin.get("/admin/users")
        assert resp.status_code == 200


class TestDatabaseBrowser:
    def test_requires_login(self, client):
        resp = client.get("/admin/database", follow_redirects=False)
        assert resp.status_code == 302

    def test_default_table_is_admins(self, logged_in_admin, mock_db):
        mock_db["query_all"].return_value = []
        mock_db["query_one"].return_value = {"c": 0}
        resp = logged_in_admin.get("/admin/database")
        assert resp.status_code == 200
        assert b"Admins" in resp.data

    def test_valid_table_param_is_used(self, logged_in_admin, mock_db):
        mock_db["query_all"].return_value = []
        mock_db["query_one"].return_value = {"c": 0}
        resp = logged_in_admin.get("/admin/database?table=products")
        assert resp.status_code == 200

    def test_invalid_table_param_falls_back_safely(self, logged_in_admin, mock_db):
        """Security-relevant test: an arbitrary/malicious ?table= value
        must never reach the SQL string — it should silently fall back to
        the whitelisted default instead.

        Note: the page's global context processor also calls query_all()
        (for the cart badge count), so we search every call made during
        the request rather than assuming the view's own query was the
        last one — template rendering can trigger additional queries
        after the view function's own logic has already run."""
        mock_db["query_all"].return_value = []
        mock_db["query_one"].return_value = {"c": 0}
        resp = logged_in_admin.get("/admin/database?table=products; DROP TABLE users;--")
        assert resp.status_code == 200
        all_sql = [call.args[0] for call in mock_db["query_all"].call_args_list]
        db_browser_calls = [sql for sql in all_sql if "FROM `" in sql]
        assert db_browser_calls, "db_browser's own query never ran"
        assert any("admin_table" in sql for sql in db_browser_calls)
        assert not any("DROP TABLE" in sql for sql in db_browser_calls)

    def test_password_columns_never_selected(self, logged_in_admin, mock_db):
        """The DB browser is documented as never exposing password hashes
        — verify no query it builds ever selects a password column."""
        mock_db["query_all"].return_value = []
        mock_db["query_one"].return_value = {"c": 0}
        for table in ["admin_table", "user_table"]:
            logged_in_admin.get(f"/admin/database?table={table}")
            all_sql = [call.args[0] for call in mock_db["query_all"].call_args_list]
            db_browser_calls = [sql for sql in all_sql if "FROM `" in sql]
            assert db_browser_calls
            assert not any("password" in sql.lower() for sql in db_browser_calls)
