from decimal import Decimal
from .conftest import get_csrf_token


class TestAddToCart:
    def test_first_add_shows_added_message(self, client, mock_db):
        mock_db["query_one"].return_value = None  # not already in cart
        resp = client.get("/cart/add/1", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Added to your bag" in resp.data

    def test_second_add_increments_quantity_and_says_so(self, client, mock_db):
        # already in cart with quantity=1 -> should become 2, not silently no-op
        mock_db["query_one"].return_value = {"product_id": 1, "ip_address": "127.0.0.1", "quantity": 1}
        resp = client.get("/cart/add/1", follow_redirects=True)
        assert resp.status_code == 200
        assert b"now 2 in your bag" in resp.data
        # confirms the UPDATE (not a fresh INSERT) ran with quantity=2
        update_call = mock_db["execute"].call_args
        assert update_call[0][1][0] == 2

    def test_add_to_cart_does_not_require_login(self, client, mock_db):
        # guest, no session — should still succeed (only *viewing* the bag requires login)
        mock_db["query_one"].return_value = None
        resp = client.get("/cart/add/1", follow_redirects=False)
        assert resp.status_code == 302  # redirect, not a 401/redirect-to-login


class TestCartView:
    def test_requires_login(self, client):
        resp = client.get("/cart", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        assert "next=cart" in resp.headers["Location"]

    def test_empty_cart_shows_empty_state(self, logged_in_customer, mock_db):
        mock_db["query_all"].return_value = []  # no cart_details rows
        resp = logged_in_customer.get("/cart")
        assert resp.status_code == 200
        assert b"Your bag is empty" in resp.data

    def test_cart_with_items_computes_line_and_total_correctly(self, logged_in_customer, mock_db):
        # get_cart_rows() does: query_all(cart_details) -> for each, query_one(product)
        mock_db["query_all"].return_value = [{"product_id": 1, "ip_address": "127.0.0.1", "quantity": 3}]
        mock_db["query_one"].return_value = {
            "product_id": 1, "product_title": "Test Product", "product_image1": "x.jpg",
            "price": Decimal("100.00"),
        }
        resp = logged_in_customer.get("/cart")
        assert resp.status_code == 200
        # price(100) * quantity(3) = 300 — this is the exact bug that was
        # previously reported and fixed: total must scale with quantity.
        assert b"300" in resp.data


class TestUpdateQuantity:
    def test_update_scopes_to_the_correct_row_only(self, logged_in_customer, mock_db):
        """Regression test: with a shared/unscoped field name, updating one
        row could silently update the wrong product. Each row's quantity
        field must be uniquely named per product_id."""
        mock_db["query_all"].return_value = []  # for the final re-render
        token = get_csrf_token(logged_in_customer, "/cart")
        resp = logged_in_customer.post("/cart", data={
            "csrf_token": token,
            "update_cart": "2",       # clicked Update on product_id=2
            "quantity_1": "99",       # a DIFFERENT row's field — must be ignored
            "quantity_2": "5",        # THIS row's field — must be what's used
        }, follow_redirects=False)
        assert resp.status_code == 302
        sql, params = mock_db["execute"].call_args[0]
        assert params == (5, "127.0.0.1", 2)  # quantity=5, product_id=2 — not 99, not 1

    def test_update_rejects_missing_csrf(self, logged_in_customer, mock_db):
        resp = logged_in_customer.post("/cart", data={"update_cart": "1", "quantity_1": "2"})
        assert resp.status_code == 403


class TestRemoveFromCart:
    def test_remove_selected_deletes_each_checked_row(self, logged_in_customer, mock_db):
        mock_db["query_all"].return_value = []
        token = get_csrf_token(logged_in_customer, "/cart")
        resp = logged_in_customer.post("/cart", data={
            "csrf_token": token,
            "remove_cart": "1",
            "remove_item": ["1", "2"],
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert mock_db["execute"].call_count == 2

    def test_remove_with_nothing_checked_shows_prompt(self, logged_in_customer, mock_db):
        mock_db["query_all"].return_value = []
        token = get_csrf_token(logged_in_customer, "/cart")
        resp = logged_in_customer.post("/cart", data={
            "csrf_token": token, "remove_cart": "1",
        }, follow_redirects=True)
        assert b"Select at least one item" in resp.data
