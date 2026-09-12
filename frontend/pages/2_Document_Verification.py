"""Streamlit page for Module 2: Document Verification."""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post, upload
from utils.auth import sidebar_login
from utils.ui import (
    apply_content_width,
    empty_state,
    info_rows,
    kicker,
    page_hero,
    surface,
    workflow_steps,
)

DOCUMENT_TYPES = ["Income Certificate", "Identity Proof", "Residence Proof", "Other"]

STATUS_HELP = {
    "verified": "This document passed every automated check.",
    "rejected": "This document failed a check. The exact reason is shown below.",
    "needs_review": "An officer needs to look at this document.",
    "processing": "This document is still being checked.",
    "pending": "This document has not been checked yet.",
}

STATUS_LABELS = {
    "verified": "Verified",
    "rejected": "Rejected",
    "needs_review": "Needs review",
    "processing": "Processing",
    "pending": "Pending",
}

STATUS_SURFACES = {
    "verified": "civicai-verified",
    "rejected": "civicai-rejected",
    "needs_review": "civicai-review",
}


def _as_text(value) -> str | None:
    """Show an existing value. ISO timestamps are spaced for readability."""
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 19 and text[4:5] == "-" and "T" in text:
        return text.replace("T", " ", 1).split(".")[0]
    return text

token = sidebar_login()
apply_content_width()

page_hero(
    "Document Verification",
    "Upload government documents for automated OCR and rule-based verification.",
    badge="Automated verification",
)
workflow_steps(("Upload", "Document processing", "Verification result"))


def show_document(document: dict, *, slot: str = "view") -> None:
    """Render one document's OCR and verification state."""
    status = document["verification_status"]
    message = STATUS_HELP.get(status, "")
    label = STATUS_LABELS.get(status, status)
    doc_id = document["document_id"]
    surface_name = STATUS_SURFACES.get(status, "civicai-pending")

    with surface(f"{surface_name}-{doc_id}-{slot}"):
        st.subheader(label)
        if status == "verified":
            st.success(f"Verified. {message}")
        elif status == "rejected":
            st.error(f"Rejected. {message}")
        elif status == "needs_review":
            st.warning(f"Needs Officer Review. {message}")
        else:
            st.info(f"{status}. {message}")

        if document.get("rejection_reason"):
            st.markdown(f"**Reason:** {document['rejection_reason']}")

    with surface(f"civicai-doc-info-{doc_id}-{slot}"):
        st.subheader("Document information")
        info_rows(
            (
                ("Document ID", f"#{document['document_id']}"),
                ("Document type", document.get("document_type")),
                ("Upload date", _as_text(document.get("upload_date"))),
                ("OCR status", document.get("ocr_status")),
                ("Verification status", status),
                ("Rejection reason", document.get("rejection_reason")),
            )
        )

        reviewer = document.get("reviewer_name")
        reviewed_at = document.get("reviewed_at")
        if reviewer or reviewed_at:
            st.caption(
                "Officer decision: "
                + (reviewer or "recorded officer")
                + (f" at {_as_text(reviewed_at)}" if reviewed_at else "")
            )

        fields = document.get("extracted_fields") or {}
        if fields:
            st.markdown("**Details read from the document**")
            for name, value in fields.items():
                st.markdown(f"- {name.replace('_', ' ').title()}: {value}")
        elif document["ocr_status"] == "completed":
            st.caption("No labelled fields could be read from this document.")


def describe_error(error: HTTPError) -> str:
    """The backend's message for a failed request."""
    try:
        return error.response.json().get("detail", error.response.text)
    except ValueError:
        return error.response.text


if not token:
    st.info("Please sign in from the sidebar to upload a document.")
else:
    with surface("civicai-upload"):
        kicker("Upload")
        st.subheader("Upload a document")
        st.caption(
            "Choose a PNG, JPG or PDF. CivicAI reads it with OCR and checks it "
            "against the rules of the relevant scheme."
        )
        uploaded = st.file_uploader(
            "Document (PNG, JPG or PDF)",
            type=["png", "jpg", "jpeg", "pdf"],
            max_upload_size=10,
        )
        document_type = st.selectbox("Document type", DOCUMENT_TYPES)
        regulation_id = st.text_input(
            "Scheme / regulation ID (optional)",
            help="Leave empty to let CivicAI work out the scheme, or send it for review.",
        )

        if st.button("Upload and verify", type="primary"):
            if uploaded is None:
                st.warning("Please choose a file first.")
            else:
                data = {"document_type": document_type}
                if regulation_id.strip():
                    data["regulation_id"] = regulation_id.strip()
                with st.spinner("Reading and checking the document..."):
                    try:
                        result = upload(
                            "/documents/upload",
                            files={
                                "file": (
                                    uploaded.name,
                                    uploaded.getvalue(),
                                    uploaded.type,
                                )
                            },
                            data=data,
                            token=token,
                        )
                    except HTTPError as error:
                        with surface("civicai-query-error-upload"):
                            st.error(describe_error(error))
                        result = None
                    except Exception:
                        with surface("civicai-query-error-upload"):
                            st.error("Backend is not reachable.")
                        result = None

                if result:
                    show_document(result, slot="result")

    with surface("civicai-doc-list"):
        kicker("Your records")
        st.subheader("Your documents")
        if st.button("Refresh list"):
            st.rerun()

        try:
            documents = get("/documents", token=token)["documents"]
        except HTTPError as error:
            with surface("civicai-query-error-list"):
                st.error(describe_error(error))
            documents = []
        except Exception:
            with surface("civicai-query-error-list"):
                st.error("Backend is not reachable.")
            documents = []

        if not documents:
            empty_state("You have not uploaded any documents yet.")
        for document in documents:
            with st.expander(
                f"#{document['document_id']} {document['document_type']} "
                f"({document['verification_status']})"
            ):
                show_document(document, slot="list")
                with surface(f"civicai-doc-actions-{document['document_id']}"):
                    st.subheader("Document actions")
                    if st.button(
                        "Check again", key=f"recheck-{document['document_id']}"
                    ):
                        try:
                            post(
                                f"/documents/{document['document_id']}/verify",
                                {},
                                token=token,
                            )
                            st.rerun()
                        except HTTPError as error:
                            st.error(describe_error(error))
