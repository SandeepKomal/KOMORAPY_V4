import bcrypt
from .conftest import get_csrf_token


def _hash(pw):
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


class TestLogin:
    def test_login_page_loads(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Login" in resp.data

    def test_login_rejects_missing_csrf(self, client):
        resp = client.post("/login", data={"username": "x", "password": "y"})
        assert resp.status_code == 403

    def test_successful_login_redirects_to_home(self, client, mock_db, sample_customer):
        sample_customer["user_password"] = _hash("correct-password")
        # call order: 1) lockout count  2) user lookup  3) cart-items check
        mock_db["query_one"].side_effect = [{"c": 0}, sample_customer, None]

        token = get_csrf_token(client, "/login")
        resp = client.post("/login", data={
            "username": "testuser", "password": "correct-password", "csrf_token": token,
        }, follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")
        with client.session_transaction() as sess:
            assert sess["user_id"] == 1
            assert sess["username"] == "testuser"

    def test_successful_login_with_pending_cart_goes_to_checkout(self, client, mock_db, sample_customer):
        sample_customer["user_password"] = _hash("correct-password")
        mock_db["query_one"].side_effect = [{"c": 0}, sample_customer, {"1": 1}]  # has_cart_items truthy

        token = get_csrf_token(client, "/login")
        resp = client.post("/login", data={
            "username": "testuser", "password": "correct-password", "csrf_token": token,
        }, follow_redirects=False)
        assert "/checkout/payment" in resp.headers["Location"]

    def test_wrong_password_shows_error_and_records_failed_attempt(self, client, mock_db, sample_customer):
        sample_customer["user_password"] = _hash("correct-password")
        mock_db["query_one"].side_effect = [{"c": 0}, sample_customer]

        token = get_csrf_token(client, "/login")
        resp = client.post("/login", data={
            "username": "testuser", "password": "wrong-password", "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"Invalid username or password" in resp.data
        assert mock_db["execute"].called  # record_failed_login() ran

    def test_nonexistent_username_shows_generic_error(self, client, mock_db):
        mock_db["query_one"].side_effect = [{"c": 0}, None]
        token = get_csrf_token(client, "/login")
        resp = client.post("/login", data={
            "username": "nosuchuser", "password": "whatever", "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"Invalid username or password" in resp.data

    def test_locked_out_identifier_blocks_login_attempt(self, client, mock_db, sample_customer):
        sample_customer["user_password"] = _hash("correct-password")
        # lockout count >= LOGIN_ATTEMPT_LIMIT (5) — should short-circuit
        # before ever looking up the user, even with the right password.
        mock_db["query_one"].side_effect = [{"c": 5}]

        token = get_csrf_token(client, "/login")
        resp = client.post("/login", data={
            "username": "testuser", "password": "correct-password", "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"Too many failed attempts" in resp.data

    def test_login_with_redirect_wishlist_saves_item_and_redirects_there(self, client, mock_db, sample_customer):
        sample_customer["user_password"] = _hash("correct-password")
        mock_db["query_one"].side_effect = [{"c": 0}, sample_customer]

        token = get_csrf_token(client, "/login?redirect_wishlist=42")
        resp = client.post("/login?redirect_wishlist=42", data={
            "username": "testuser", "password": "correct-password", "csrf_token": token,
        }, follow_redirects=False)
        assert "/wishlist" in resp.headers["Location"]
        # INSERT IGNORE INTO wishlist_details ran with the right product id
        insert_call = mock_db["execute"].call_args
        assert insert_call[0][1] == (1, 42)


class TestRegister:
    def test_register_page_loads(self, client):
        resp = client.get("/register")
        assert resp.status_code == 200

    def test_successful_registration_redirects_to_login(self, client, mock_db):
        mock_db["query_one"].return_value = None  # no existing duplicate
        mock_db["execute"].return_value = (1, 7)   # new user_id = 7

        token = get_csrf_token(client, "/register")
        resp = client.post("/register", data={
            "username": "newuser", "email": "new@example.com",
            "password": "longenoughpw", "confirm_password": "longenoughpw",
            "address": "1 Main St", "mobile": "9999999999",
            "csrf_token": token,
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/login")

    def test_duplicate_username_is_rejected(self, client, mock_db, sample_customer):
        mock_db["query_one"].return_value = sample_customer  # username collides
        token = get_csrf_token(client, "/register")
        resp = client.post("/register", data={
            "username": "testuser", "email": "new@example.com",
            "password": "longenoughpw", "confirm_password": "longenoughpw",
            "address": "1 Main St", "mobile": "1111111111",
            "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"already taken" in resp.data

    def test_short_password_is_rejected(self, client, mock_db):
        mock_db["query_one"].return_value = None
        token = get_csrf_token(client, "/register")
        resp = client.post("/register", data={
            "username": "newuser", "email": "new@example.com",
            "password": "short", "confirm_password": "short",
            "address": "1 Main St", "mobile": "9999999999",
            "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"at least 8 characters" in resp.data

    def test_mismatched_passwords_are_rejected(self, client, mock_db):
        mock_db["query_one"].return_value = None
        token = get_csrf_token(client, "/register")
        resp = client.post("/register", data={
            "username": "newuser", "email": "new@example.com",
            "password": "longenoughpw", "confirm_password": "differentpw",
            "address": "1 Main St", "mobile": "9999999999",
            "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"don&#39;t match" in resp.data or b"don't match" in resp.data

    def test_registration_with_redirect_wishlist_saves_item(self, client, mock_db):
        mock_db["query_one"].return_value = None
        mock_db["execute"].return_value = (1, 9)

        token = get_csrf_token(client, "/register?redirect_wishlist=5")
        resp = client.post("/register?redirect_wishlist=5", data={
            "username": "newuser", "email": "new@example.com",
            "password": "longenoughpw", "confirm_password": "longenoughpw",
            "address": "1 Main St", "mobile": "9999999999",
            "csrf_token": token,
        }, follow_redirects=False)
        assert "redirect_wishlist=5" in resp.headers["Location"]


class TestLogout:
    def test_logout_clears_session_and_redirects_home(self, logged_in_customer):
        resp = logged_in_customer.get("/logout", follow_redirects=False)
        assert resp.status_code == 302
        with logged_in_customer.session_transaction() as sess:
            assert "user_id" not in sess


class TestProfileEdit:
    def test_requires_login(self, client):
        resp = client.get("/profile/edit", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_loads_for_logged_in_user(self, logged_in_customer, mock_db, sample_customer):
        mock_db["query_one"].return_value = sample_customer
        resp = logged_in_customer.get("/profile/edit")
        assert resp.status_code == 200
        assert b"testuser" in resp.data

    def test_successful_update(self, logged_in_customer, mock_db, sample_customer):
        mock_db["query_one"].side_effect = [sample_customer, None]  # load, then dup-check finds nothing
        token = get_csrf_token(logged_in_customer, "/profile/edit")
        resp = logged_in_customer.post("/profile/edit", data={
            "username": "testuser", "email": "updated@example.com",
            "address": "New address", "mobile": "8888888888",
            "csrf_token": token,
        }, follow_redirects=False)
        assert resp.status_code == 302

    def test_duplicate_email_rejected(self, logged_in_customer, mock_db, sample_customer):
        other_user = dict(sample_customer, user_id=2, username="other", user_email="taken@example.com")
        mock_db["query_one"].side_effect = [sample_customer, other_user]
        token = get_csrf_token(logged_in_customer, "/profile/edit")
        resp = logged_in_customer.post("/profile/edit", data={
            "username": "testuser", "email": "taken@example.com",
            "address": "New address", "mobile": "8888888888",
            "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"already exists" in resp.data


class TestContact:
    def test_contact_page_loads(self, client):
        resp = client.get("/contact")
        assert resp.status_code == 200
