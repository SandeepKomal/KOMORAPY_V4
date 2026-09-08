from .conftest import get_csrf_token


class TestIndex:
    def test_homepage_loads(self, client, mock_db, sample_product):
        mock_db["query_all"].return_value = [sample_product]
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"KOMORA" in resp.data

    def test_homepage_with_no_products(self, client, mock_db):
        mock_db["query_all"].return_value = []
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Nothing here yet" in resp.data

    def test_homepage_shows_drop_badge(self, client, mock_db, sample_product):
        mock_db["query_all"].return_value = [sample_product]
        resp = client.get("/")
        assert b"v-badge-tag" in resp.data or b"v-badge-low" in resp.data

    def test_homepage_low_stock_badge_for_product_id_divisible_by_4(self, client, mock_db, sample_product):
        sample_product["product_id"] = 4
        mock_db["query_all"].return_value = [sample_product]
        resp = client.get("/")
        assert b"Low stock" in resp.data

    def test_homepage_hover_swap_image_when_image2_present(self, client, mock_db, sample_product):
        sample_product["product_image2"] = "hover.jpg"
        mock_db["query_all"].return_value = [sample_product]
        resp = client.get("/")
        assert b"v-img-hover" in resp.data
        assert b"hover.jpg" in resp.data

    def test_homepage_no_hover_image_when_image2_absent(self, client, mock_db, sample_product):
        sample_product["product_image2"] = ""
        mock_db["query_all"].return_value = [sample_product]
        resp = client.get("/")
        assert b"v-img-hover" not in resp.data


class TestAllProducts:
    def test_all_products_loads(self, client, mock_db, sample_product):
        mock_db["query_all"].return_value = [sample_product]
        resp = client.get("/products")
        assert resp.status_code == 200

    def test_filter_by_category(self, client, mock_db, sample_product):
        mock_db["query_all"].return_value = [sample_product]
        resp = client.get("/products?category=1")
        assert resp.status_code == 200

    def test_filter_by_brand(self, client, mock_db, sample_product):
        mock_db["query_all"].return_value = [sample_product]
        resp = client.get("/products?brand=1")
        assert resp.status_code == 200

    def test_empty_catalogue_shows_empty_state(self, client, mock_db):
        mock_db["query_all"].return_value = []
        resp = client.get("/products")
        assert b"Nothing here" in resp.data


class TestSearch:
    def test_search_with_no_query_shows_prompt(self, client, mock_db):
        resp = client.get("/search")
        assert resp.status_code == 200
        assert b"Search the drop" in resp.data

    def test_search_with_matching_query(self, client, mock_db, sample_product):
        mock_db["query_all"].return_value = [sample_product]
        resp = client.get("/search?q=test")
        assert resp.status_code == 200
        assert b"Test Product" in resp.data

    def test_search_with_no_results(self, client, mock_db):
        mock_db["query_all"].return_value = []
        resp = client.get("/search?q=nonexistent")
        assert resp.status_code == 200
        assert b"No results found" in resp.data

    def test_search_uses_like_query_with_wildcards(self, client, mock_db):
        client.get("/search?q=shoes")
        # the view's own query runs first; later calls in the list are the
        # page's global context processor (categories/brands/cart badge)
        first_call = mock_db["query_all"].call_args_list[0]
        assert "%shoes%" in first_call.args[1]


class TestProductDetails:
    def test_existing_product_loads(self, client, mock_db, sample_product):
        mock_db["query_one"].return_value = sample_product
        resp = client.get("/product/1")
        assert resp.status_code == 200
        assert b"Test Product" in resp.data

    def test_nonexistent_product_returns_404(self, client, mock_db):
        mock_db["query_one"].return_value = None
        resp = client.get("/product/9999")
        assert resp.status_code == 404
