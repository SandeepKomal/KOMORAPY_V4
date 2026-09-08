from decimal import Decimal
from .conftest import get_csrf_token


def _one_cart_line_and_product(mock_db, price=Decimal("500.00"), quantity=2):
    """Wires up mock_db so _cart_line_items() resolves to exactly one item."""
    mock_db["query_all"].return_value = [{"product_id": 1, "ip_address": "127.0.0.1", "quantity": quantity}]
    mock_db["query_one"].return_value = {
        "product_id": 1, "product_title": "Test Product", "product_image1": "x.jpg", "price": price,
    }


class TestAddressStep:
    def test_requires_login(self, client):
        resp = client.get("/checkout/address", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_empty_cart_redirects_to_cart_page(self, logged_in_customer, mock_db):
        mock_db["query_all"].return_value = []
        resp = logged_in_customer.get("/checkout/address", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/cart")

    def test_shows_saved_address_when_present(self, logged_in_customer, mock_db):
        mock_db["query_all"].return_value = [{"product_id": 1, "ip_address": "127.0.0.1", "quantity": 1}]
        # side_effect: 1) product lookup for the cart line  2) user's saved address
        mock_db["query_one"].side_effect = [
            {"product_id": 1, "product_title": "T", "product_image1": "x.jpg", "price": Decimal("100")},
            {"user_address": "123 Saved St", "user_mobile": "9999999999"},
        ]
        resp = logged_in_customer.get("/checkout/address")
        assert resp.status_code == 200
        assert b"123 Saved St" in resp.data

    def test_submitting_new_address_advances_to_payment(self, logged_in_customer, mock_db):
        mock_db["query_all"].return_value = [{"product_id": 1, "ip_address": "127.0.0.1", "quantity": 1}]
        mock_db["query_one"].side_effect = [
            {"product_id": 1, "product_title": "T", "product_image1": "x.jpg", "price": Decimal("100")},
            {"user_address": "", "user_mobile": ""},
        ]
        token = get_csrf_token(logged_in_customer, "/checkout/address")
        resp = logged_in_customer.post("/checkout/address", data={
            "address_choice": "new", "address": "42 New Ave", "mobile": "8888888888",
            "csrf_token": token,
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/checkout/payment")
        with logged_in_customer.session_transaction() as sess:
            assert sess["checkout_address"] == "42 New Ave"

    def test_missing_address_shows_error(self, logged_in_customer, mock_db):
        mock_db["query_all"].return_value = [{"product_id": 1, "ip_address": "127.0.0.1", "quantity": 1}]
        mock_db["query_one"].side_effect = [
            {"product_id": 1, "product_title": "T", "product_image1": "x.jpg", "price": Decimal("100")},
            {"user_address": "", "user_mobile": ""},
        ]
        token = get_csrf_token(logged_in_customer, "/checkout/address")
        resp = logged_in_customer.post("/checkout/address", data={
            "address_choice": "new", "address": "", "mobile": "", "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"Please fill in both fields" in resp.data


class TestPaymentStep:
    def test_requires_login(self, client):
        resp = client.get("/checkout/payment", follow_redirects=False)
        assert resp.status_code == 302

    def test_redirects_to_address_if_no_address_chosen_yet(self, logged_in_customer, mock_db):
        resp = logged_in_customer.get("/checkout/payment", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/checkout/address")

    def test_shows_total_multiplied_by_quantity(self, logged_in_customer, mock_db):
        with logged_in_customer.session_transaction() as sess:
            sess["checkout_address"] = "1 Main St"
            sess["checkout_mobile"] = "9999999999"
        _one_cart_line_and_product(mock_db, price=Decimal("500.00"), quantity=3)
        resp = logged_in_customer.get("/checkout/payment")
        assert resp.status_code == 200
        assert b"1,500" in resp.data  # 500 * 3

    def test_placing_order_creates_one_row_set_per_item_and_empties_cart(self, logged_in_customer, mock_db):
        with logged_in_customer.session_transaction() as sess:
            sess["checkout_address"] = "1 Main St"
            sess["checkout_mobile"] = "9999999999"
        _one_cart_line_and_product(mock_db, price=Decimal("500.00"), quantity=1)
        mock_db["execute"].return_value = (1, 55)  # (rowcount, new order_id)

        token = get_csrf_token(logged_in_customer, "/checkout/payment")
        resp = logged_in_customer.post("/checkout/payment", data={
            "payment_mode": "UPI", "csrf_token": token,
        }, follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/orders")
        # one item -> user_orders insert, orders_pending insert, user_payments
        # insert, cart_details delete = 4 execute() calls
        assert mock_db["execute"].call_count == 4
        with logged_in_customer.session_transaction() as sess:
            assert "checkout_address" not in sess

    def test_missing_payment_mode_shows_error(self, logged_in_customer, mock_db):
        with logged_in_customer.session_transaction() as sess:
            sess["checkout_address"] = "1 Main St"
        _one_cart_line_and_product(mock_db)
        token = get_csrf_token(logged_in_customer, "/checkout/payment")
        resp = logged_in_customer.post("/checkout/payment", data={
            "payment_mode": "", "csrf_token": token,
        })
        assert resp.status_code == 200
        assert b"Please select a payment mode" in resp.data


class TestOrdersList:
    def test_requires_login(self, client):
        resp = client.get("/orders", follow_redirects=False)
        assert resp.status_code == 302

    def test_shows_orders_for_logged_in_user(self, logged_in_customer, mock_db):
        mock_db["query_all"].return_value = [{
            "order_id": 1, "amount_due": Decimal("500.00"), "invoice_number": 12345,
            "total_products": 1, "order_date": "2026-01-01", "order_status": "Complete",
            "product_title": "Test Product", "product_image1": "x.jpg",
        }]
        resp = logged_in_customer.get("/orders")
        assert resp.status_code == 200
        assert b"12345" in resp.data
