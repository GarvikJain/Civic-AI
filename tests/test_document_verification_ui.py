"""Frontend presentation checks for Document Verification."""

import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

from utils.auth_store import COOKIE_NAME, DictTokenStore

PAGE = FRONTEND / "pages" / "2_Document_Verification.py"


def _page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_page_source_keeps_upload_and_verify_contract():
    page = _page_text()
    assert 'type=["png", "jpg", "jpeg", "pdf"]' in page
    assert "max_upload_size=10" in page
    assert "200MB" not in page
    assert "200 MB" not in page
    assert 'st.button("Upload and verify", type="primary")' in page
    assert '"/documents/upload"' in page
    assert 'f"/documents/{document[\'document_id\']}/verify"' in page
    assert 'key=f"recheck-{document[\'document_id\']}"' in page
    assert 'st.error("Backend is not reachable.")' in page
    assert "This document passed every automated check." in page
    assert "An officer needs to look at this document." in page
    assert "Needs Officer Review." in page
    assert "Reading and checking the document..." in page
    assert "DOCUMENT_TYPES = " in page


def test_visible_uploader_limit_matches_backend_10mb():
    config = (FRONTEND.parent / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    backend = (
        FRONTEND.parent / "backend" / "core" / "config.py"
    ).read_text(encoding="utf-8")
    validation = (
        FRONTEND.parent
        / "ai_modules"
        / "document_verification"
        / "file_validation.py"
    ).read_text(encoding="utf-8")
    assert "maxUploadSize = 10" in config
    assert "max_upload_size_mb: int = 10" in backend
    assert "DEFAULT_MAX_BYTES = 10 * 1024 * 1024" in validation


def test_page_source_uses_civic_document_surfaces():
    page = _page_text()
    assert "page_hero" in page
    assert "Automated verification" in page
    assert "Upload a document" in page
    assert "Your documents" in page
    assert "civicai-upload" in page
    assert "civicai-verified" in page
    assert "civicai-rejected" in page
    assert "civicai-review" in page
    assert 'st.info("Please sign in from the sidebar to upload a document.")' in page


def _signed_in_citizen(monkeypatch, *, documents=None, upload_impl=None, get_error=None):
    from streamlit.testing.v1 import AppTest

    import utils.api_client as api_client
    import utils.auth as auth

    store = DictTokenStore({COOKIE_NAME: "jwt-citizen"})
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            return {
                "id": 1,
                "email": "citizen@example.com",
                "role": "citizen",
                "full_name": "Test Citizen",
                "is_active": True,
            }
        if path == "/documents":
            if get_error is not None:
                raise get_error
            return {"documents": documents or []}
        return {}

    monkeypatch.setattr(auth, "get", fake_get)
    monkeypatch.setattr(api_client, "get", fake_get)
    monkeypatch.setattr(
        api_client,
        "upload",
        upload_impl or (lambda *args, **kwargs: {}),
    )
    monkeypatch.setattr(api_client, "post", lambda *args, **kwargs: {})
    monkeypatch.setattr(auth, "post", lambda *args, **kwargs: {"access_token": "x"})

    at = AppTest.from_file(str(PAGE), default_timeout=10)
    at.run()
    assert not at.exception
    return at


def test_apptest_logged_out_page_has_hero(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.auth as auth

    monkeypatch.setattr(auth, "get_browser_token_store", lambda: DictTokenStore())
    at = AppTest.from_file(str(PAGE), default_timeout=10)
    at.run()
    assert not at.exception
    body = " ".join(str(item.value) for item in at.markdown)
    assert "Document Verification" in body
    assert "Automated verification" in body
    assert any(
        "Please sign in from the sidebar to upload a document." in str(item.value)
        for item in at.info
    )
    assert not any(button.label == "Upload and verify" for button in at.button)


def test_apptest_signed_in_upload_section(monkeypatch):
    at = _signed_in_citizen(monkeypatch)
    body = " ".join(str(item.value) for item in at.markdown)
    assert "Upload a document" in body or any(
        item.value == "Upload a document" for item in at.subheader
    )
    assert any(button.label == "Upload and verify" for button in at.button)
    assert at.file_uploader
    assert at.selectbox
    assert any("You have not uploaded any documents yet." in str(item.value) for item in at.markdown)


def test_apptest_renders_verified_rejected_and_review_documents(monkeypatch):
    documents = [
        {
            "document_id": 1,
            "document_type": "Income Certificate",
            "ocr_status": "completed",
            "verification_status": "verified",
            "rejection_reason": None,
            "extracted_fields": {"name": "Test Citizen"},
            "upload_date": "2026-09-12T10:00:00",
            "reviewer_name": None,
            "reviewed_at": None,
        },
        {
            "document_id": 2,
            "document_type": "Identity Proof",
            "ocr_status": "completed",
            "verification_status": "rejected",
            "rejection_reason": "Required name field could not be found on the document.",
            "extracted_fields": {},
            "upload_date": "2026-09-12T11:00:00",
            "reviewer_name": None,
            "reviewed_at": None,
        },
        {
            "document_id": 3,
            "document_type": "Residence Proof",
            "ocr_status": "completed",
            "verification_status": "needs_review",
            "rejection_reason": "The document text could not be extracted, so it needs officer review.",
            "extracted_fields": {},
            "upload_date": "2026-09-12T12:00:00",
            "reviewer_name": None,
            "reviewed_at": None,
        },
    ]
    at = _signed_in_citizen(monkeypatch, documents=documents)
    assert any("Verified." in str(item.value) for item in at.success)
    assert any("Rejected." in str(item.value) for item in at.error)
    assert any("Needs Officer Review." in str(item.value) for item in at.warning)
    labels = [item.value for item in at.subheader]
    assert "Verified" in labels
    assert "Rejected" in labels
    assert "Needs review" in labels
    body = " ".join(str(item.value) for item in at.markdown)
    assert "Required name field could not be found on the document." in body
    assert "The document text could not be extracted, so it needs officer review." in body
    assert any(button.label == "Check again" for button in at.button)


def test_apptest_list_connection_error_is_unchanged(monkeypatch):
    at = _signed_in_citizen(monkeypatch, get_error=ConnectionError("refused"))
    assert any("Backend is not reachable." in str(item.value) for item in at.error)
