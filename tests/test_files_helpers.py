"""Unit tests for pure helpers in tools.files."""

from nc_mcp_server.tools.files import _resolve_content_type


class TestResolveContentType:
    def test_explicit_content_type_kept(self) -> None:
        assert _resolve_content_type("photo.png", "custom/type") == "custom/type"

    def test_explicit_content_type_kept_for_unknown_extension(self) -> None:
        assert _resolve_content_type("blob.weirdext", "application/x-custom") == "application/x-custom"

    def test_png_extension_inferred(self) -> None:
        assert _resolve_content_type("photo.png", "") == "image/png"

    def test_pdf_extension_inferred(self) -> None:
        assert _resolve_content_type("doc.pdf", "") == "application/pdf"

    def test_jpeg_extension_inferred(self) -> None:
        assert _resolve_content_type("photo.jpeg", "") == "image/jpeg"

    def test_unknown_extension_falls_back(self) -> None:
        assert _resolve_content_type("blob.weirdext", "") == "application/octet-stream"

    def test_no_extension_falls_back(self) -> None:
        assert _resolve_content_type("noext", "") == "application/octet-stream"

    def test_nested_path_inference(self) -> None:
        assert _resolve_content_type("deep/sub/path/photo.png", "") == "image/png"

    def test_whitespace_only_content_type_falls_back_to_inference(self) -> None:
        assert _resolve_content_type("photo.png", "   ") == "image/png"
        assert _resolve_content_type("photo.png", "\t\n") == "image/png"

    def test_whitespace_only_content_type_falls_back_to_octet_stream(self) -> None:
        assert _resolve_content_type("blob.weirdext", "   ") == "application/octet-stream"

    def test_explicit_content_type_trimmed(self) -> None:
        assert _resolve_content_type("photo.png", "  image/png  ") == "image/png"
