"""These test pure/isolated logic directly, without going through a full
HTTP request where it's not needed — faster and more precise than routing
everything through the test client."""
from app.helpers import product_image_path, user_image_path


class TestImagePaths:
    def test_empty_filename_returns_placeholder(self):
        assert product_image_path("") == "/static/images/empty.gif"
        assert product_image_path(None) == "/static/images/empty.gif"

    def test_whitespace_only_filename_returns_placeholder(self):
        assert product_image_path("   ") == "/static/images/empty.gif"

    def test_real_filename_returns_media_path(self):
        assert product_image_path("shoe.jpg") == "/media/products/shoe.jpg"

    def test_filename_is_stripped(self):
        assert product_image_path("  shoe.jpg  ") == "/media/products/shoe.jpg"

    def test_user_image_path_uses_users_directory(self):
        assert user_image_path("avatar.png") == "/media/users/avatar.png"
        assert user_image_path("") == "/static/images/empty.gif"


class TestCoverCrop:
    """The image-normalization feature: every uploaded product photo gets
    resized+cropped to a fixed 4:5 ratio regardless of its original shape."""

    def test_wide_image_crops_to_target_size(self):
        from PIL import Image
        from app.helpers import _cover_crop
        img = Image.new("RGB", (2000, 800), "red")
        out = _cover_crop(img, (800, 1000))
        assert out.size == (800, 1000)

    def test_tall_image_crops_to_target_size(self):
        from PIL import Image
        from app.helpers import _cover_crop
        img = Image.new("RGB", (600, 3000), "blue")
        out = _cover_crop(img, (800, 1000))
        assert out.size == (800, 1000)

    def test_square_image_crops_to_target_size(self):
        from PIL import Image
        from app.helpers import _cover_crop
        img = Image.new("RGB", (1000, 1000), "green")
        out = _cover_crop(img, (800, 1000))
        assert out.size == (800, 1000)

    def test_already_correct_ratio_still_resizes_exactly(self):
        from PIL import Image
        from app.helpers import _cover_crop
        img = Image.new("RGB", (400, 500), "yellow")  # already 4:5
        out = _cover_crop(img, (800, 1000))
        assert out.size == (800, 1000)


class TestSaveUpload:
    def test_rejects_disallowed_extension(self, tmp_path, mocker):
        from app.helpers import save_upload
        fake_file = mocker.MagicMock()
        fake_file.filename = "malicious.exe"
        result = save_upload(fake_file, str(tmp_path))
        assert result is None

    def test_rejects_missing_file(self, tmp_path):
        from app.helpers import save_upload
        assert save_upload(None, str(tmp_path)) is None

    def test_rejects_file_with_no_filename(self, tmp_path, mocker):
        from app.helpers import save_upload
        fake_file = mocker.MagicMock()
        fake_file.filename = ""
        assert save_upload(fake_file, str(tmp_path)) is None

    def test_rejects_non_image_content_disguised_as_image(self, tmp_path, mocker):
        """Defense-in-depth: a file named photo.jpg that isn't actually a
        valid image (e.g. a renamed script) must be rejected — this is
        exactly the check that stops a malicious upload bypassing the
        extension whitelist by just renaming the file."""
        import io
        from app.helpers import save_upload
        fake_file = mocker.MagicMock()
        fake_file.filename = "fake.jpg"
        fake_file.stream = io.BytesIO(b"this is not an image, just text")
        result = save_upload(fake_file, str(tmp_path))
        assert result is None

    def test_accepts_and_normalizes_a_real_image(self, tmp_path):
        import io
        from PIL import Image
        from werkzeug.datastructures import FileStorage
        from app.helpers import save_upload

        buf = io.BytesIO()
        Image.new("RGB", (2400, 900), "purple").save(buf, format="JPEG")
        buf.seek(0)
        upload = FileStorage(stream=buf, filename="wide_photo.jpg")

        result = save_upload(upload, str(tmp_path), target_size=(800, 1000))
        assert result is not None
        assert result.endswith(".jpg")

        saved_path = tmp_path / result
        assert saved_path.exists()
        with Image.open(saved_path) as saved_img:
            assert saved_img.size == (800, 1000)


class TestCsrf:
    def test_token_is_generated_and_persisted_in_session(self, app):
        from app.helpers import csrf_token
        with app.test_request_context():
            token1 = csrf_token()
            token2 = csrf_token()
            assert token1 == token2  # same session -> same token, not regenerated each call
            assert len(token1) == 64  # secrets.token_hex(32) -> 64 hex chars

    def test_check_rejects_missing_token(self, app):
        from app.helpers import csrf_check
        from flask import request
        with app.test_request_context("/", method="POST", data={}):
            try:
                csrf_check()
                assert False, "should have aborted"
            except Exception as e:
                assert "403" in str(e) or getattr(e, "code", None) == 403

    def test_check_accepts_matching_token(self, app):
        from app.helpers import csrf_token, csrf_check
        with app.test_request_context():
            token = csrf_token()
        with app.test_request_context("/", method="POST", data={"csrf_token": token}):
            from flask import session as flask_session
            flask_session["csrf_token"] = token
            csrf_check()  # should not raise
