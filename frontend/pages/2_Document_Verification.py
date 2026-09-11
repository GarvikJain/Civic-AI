"""Streamlit page for Module 2: Document Verification."""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post, upload
from utils.auth import sidebar_login

DOCUMENT_TYPES = ["Income Certificate", "Identity Proof", "Residence Proof", "Other"]

STATUS_HELP = {
    "verified": "This document passed every automated check.",
    "rejected": "This document failed a check. The exact reason is shown below.",
    "needs_review": "An officer needs to look at this document.",
    "processing": "This document is still being checked.",
    "pending": "This document has not been checked yet.",
}

st.title("Document Verification")
st.write(
    "Upload a government document. CivicAI reads it with OCR and checks it "
    "against the rules of the relevant scheme."
)

token = sidebar_login()


def show_document(document: dict) -> None:
    """Render one document's OCR and verification state."""
    status = document["verification_status"]
    message = STATUS_HELP.get(status, "")

    if status == "verified":
        st.success(f"Verified. {message}")
    elif status == "rejected":
        st.error(f"Rejected. {message}")
    elif status == "needs_review":
        st.warning(f"Needs Officer Review. {message}")
    else:
        st.info(f"{status}. {message}")

    st.caption(
        f"Document #{document['document_id']} | type: {document['document_type']} | "
        f"OCR status: {document['ocr_status']}"
    )

    if document.get("rejection_reason"):
        st.markdown(f"**Reason:** {document['rejection_reason']}")

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
    st.subheader("Upload a document")
    uploaded = st.file_uploader("Document (PNG, JPG or PDF)", type=["png", "jpg", "jpeg", "pdf"])
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
                        files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                        data=data,
                        token=token,
                    )
                except HTTPError as error:
                    st.error(describe_error(error))
                    result = None
                except Exception:
                    st.error("Backend is not reachable.")
                    result = None

            if result:
                show_document(result)

    st.divider()
    st.subheader("Your documents")
    if st.button("Refresh list"):
        st.rerun()

    try:
        documents = get("/documents", token=token)["documents"]
    except HTTPError as error:
        st.error(describe_error(error))
        documents = []
    except Exception:
        st.error("Backend is not reachable.")
        documents = []

    if not documents:
        st.caption("You have not uploaded any documents yet.")
    for document in documents:
        with st.expander(
            f"#{document['document_id']} {document['document_type']} "
            f"({document['verification_status']})"
        ):
            show_document(document)
            if st.button("Check again", key=f"recheck-{document['document_id']}"):
                try:
                    post(f"/documents/{document['document_id']}/verify", {}, token=token)
                    st.rerun()
                except HTTPError as error:
                    st.error(describe_error(error))
