class TestWishlistView:
    def test_guest_sees_login_gate_not_a_redirect(self, client):
        """The wishlist page shows an inline 'please log in' interstitial
        for guests rather than hard-redirecting — this is a deliberate UX
        choice made earlier, worth protecting with a regression test."""
        resp = client.get("/wishlist")
        assert resp.status_code == 200  # NOT a 302 — stays on /wishlist
        assert b"Please log in" in resp.data

    def test_logged_in_user_sees_their_items(self, logged_in_customer, mock_db, sample_product):
        mock_db["query_all"].return_value = [sample_product]
        resp = logged_in_customer.get("/wishlist")
        assert resp.status_code == 200
        assert b"Test Product" in resp.data

    def test_empty_wishlist_shows_empty_state(self, logged_in_customer, mock_db):
        mock_db["query_all"].return_value = []
        resp = logged_in_customer.get("/wishlist")
        assert b"Nothing saved yet" in resp.data


class TestWishlistAdd:
    def test_guest_redirected_to_login_with_product_id_preserved(self, client):
        resp = client.get("/wishlist/add/42", follow_redirects=False)
        assert resp.status_code == 302
        assert "redirect_wishlist=42" in resp.headers["Location"]

    def test_logged_in_user_can_add(self, logged_in_customer, mock_db):
        resp = logged_in_customer.get("/wishlist/add/1", follow_redirects=False)
        assert resp.status_code == 302
        assert mock_db["execute"].called
        sql = mock_db["execute"].call_args[0][0]
        assert "INSERT IGNORE" in sql


class TestWishlistRemove:
    def test_removes_and_flashes(self, logged_in_customer, mock_db):
        resp = logged_in_customer.get("/wishlist/remove/1", follow_redirects=True)
        assert resp.status_code == 200
        assert mock_db["execute"].called
        assert b"Removed from wishlist" in resp.data

    def test_guest_does_not_trigger_delete(self, client, mock_db):
        client.get("/wishlist/remove/1")
        assert not mock_db["execute"].called


class TestMoveToBag:
    def test_moves_item_when_not_already_in_cart(self, logged_in_customer, mock_db):
        # sequence: 1) already_in_cart check -> None  2) add_to_cart's own
        # existing-check -> None (so it INSERTs fresh)
        mock_db["query_one"].side_effect = [None, None]
        resp = logged_in_customer.get("/wishlist/move-to-bag/1", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Moved to bag" in resp.data
        # both the cart insert and the wishlist delete should have run
        assert mock_db["execute"].call_count == 2

    def test_does_not_duplicate_if_already_in_cart(self, logged_in_customer, mock_db):
        mock_db["query_one"].return_value = {"1": 1}  # already_in_cart truthy
        logged_in_customer.get("/wishlist/move-to-bag/1", follow_redirects=True)
        # only the wishlist DELETE should run, no cart INSERT/UPDATE
        assert mock_db["execute"].call_count == 1

    def test_guest_is_redirected_without_side_effects(self, client, mock_db):
        resp = client.get("/wishlist/move-to-bag/1", follow_redirects=False)
        assert resp.status_code == 302
        assert not mock_db["execute"].called
