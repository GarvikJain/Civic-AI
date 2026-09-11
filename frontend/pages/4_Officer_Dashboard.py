"""Streamlit page for Module 4: Officer Productivity Dashboard.

The productivity metrics are still to come. For now this page carries the
minimal document review queue added with document verification.
"""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post
from utils.auth import sidebar_login

st.title("Officer Dashboard")
st.write("Review the documents that automated checks could not decide.")

token = sidebar_login()

try:
    st.caption(f"Productivity metrics: {get('/officers/status')['status']}")
except Exception as error:
    st.warning(f"Could not reach the backend: {error}")


def describe_error(error: HTTPError) -> str:
    """The backend's message for a failed request."""
    try:
        return error.response.json().get("detail", error.response.text)
    except ValueError:
        return error.response.text


st.divider()
st.subheader("Documents needing review")

if not token:
    st.info("Please sign in as an officer or administrator from the sidebar.")
else:
    try:
        documents = get("/officers/documents/review", token=token)["documents"]
    except HTTPError as error:
        if error.response.status_code == 403:
            st.error("This queue is only available to officers and administrators.")
        else:
            st.error(describe_error(error))
        documents = []
    except Exception:
        st.error("Backend is not reachable.")
        documents = []

    if not documents:
        st.success("Nothing is waiting for review.")

    for document in documents:
        with st.expander(
            f"#{document['document_id']} {document['document_type']} "
            f"(citizen {document['citizen_id']})"
        ):
            st.caption(f"OCR status: {document['ocr_status']}")
            if document.get("rejection_reason"):
                st.markdown(f"**Why it needs review:** {document['rejection_reason']}")

            fields = document.get("extracted_fields") or {}
            if fields:
                for name, value in fields.items():
                    st.markdown(f"- {name.replace('_', ' ').title()}: {value}")
            else:
                st.caption("No labelled fields could be read from this document.")

            document_id = document["document_id"]
            reason = st.text_input(
                "Rejection reason", key=f"reason-{document_id}", max_chars=500
            )
            approve, reject = st.columns(2)

            if approve.button("Approve", key=f"approve-{document_id}"):
                try:
                    post(
                        f"/officers/documents/{document_id}/approve", {}, token=token
                    )
                    st.rerun()
                except HTTPError as error:
                    st.error(describe_error(error))

            if reject.button("Reject", key=f"reject-{document_id}"):
                if len(reason.strip()) < 3:
                    st.warning("Please type the reason for rejecting the document.")
                else:
                    try:
                        post(
                            f"/officers/documents/{document_id}/reject",
                            {"reason": reason.strip()},
                            token=token,
                        )
                        st.rerun()
                    except HTTPError as error:
                        st.error(describe_error(error))
