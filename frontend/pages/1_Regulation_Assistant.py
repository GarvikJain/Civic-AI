"""Streamlit page for Module 1: Regulation RAG Assistant."""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post
from utils.auth import current_role, sidebar_login

st.title("Regulation RAG Assistant")
st.write(
    "Ask a question about a government scheme. Answers come only from the "
    "official regulation documents that have been ingested, with citations."
)

token = sidebar_login()
role = current_role()

if role == "administrator" and token:
    st.subheader("Administrator: register a scheme")
    with st.form("create-regulation"):
        scheme_name = st.text_input("Scheme name")
        department = st.text_input("Department")
        criteria = st.text_area("Eligibility criteria", height=80)
        documents = st.text_area("Required documents", height=60)
        circular = st.text_input("Circular reference (optional)")
        submitted = st.form_submit_button("Save regulation")
    if submitted:
        if not scheme_name.strip() or not department.strip():
            st.warning("Scheme name and department are required.")
        else:
            try:
                created = post(
                    "/regulations",
                    {
                        "scheme_name": scheme_name.strip(),
                        "department": department.strip(),
                        "eligibility_criteria": criteria.strip() or None,
                        "required_documents": documents.strip() or None,
                        "circular_reference": circular.strip() or None,
                    },
                    token=token,
                )
                st.success(f"Saved regulation #{created['regulation_id']}.")
            except HTTPError as error:
                detail = error.response.text
                try:
                    detail = error.response.json().get("detail", detail)
                except ValueError:
                    pass
                st.error(detail)
    if st.button("Ingest regulation documents from data/regulations/"):
        try:
            ingested = post("/regulations/ingest", {}, token=token, timeout=180)
            st.success(
                f"Ingested {ingested.get('documents')} document(s), "
                f"{ingested.get('chunks')} chunk(s)."
            )
        except HTTPError as error:
            detail = error.response.text
            try:
                detail = error.response.json().get("detail", detail)
            except ValueError:
                pass
            st.error(detail)

question = st.text_area(
    "Your question",
    placeholder="What documents do I need for an income certificate?",
    height=100,
)

if st.button("Ask", type="primary"):
    if not token:
        st.warning("Please sign in from the sidebar first.")
    elif len(question.strip()) < 3:
        st.warning("Please type a longer question.")
    else:
        with st.spinner("Searching the official regulations..."):
            try:
                result = post("/regulations/query", {"query": question}, token=token)
            except HTTPError as error:
                response = error.response
                detail = ""
                try:
                    detail = response.json().get("detail", "")
                except ValueError:
                    detail = response.text
                if response.status_code == 503:
                    st.error(f"The assistant is not available: {detail}")
                else:
                    st.error(f"Request failed ({response.status_code}): {detail}")
                result = None
            except Exception:
                st.error("Backend is not reachable.")
                result = None

        if result:
            if result["insufficient_evidence"]:
                st.warning(result["answer"])
            else:
                st.subheader("Answer")
                st.write(result["answer"])

                citations = result.get("citations") or []
                if citations:
                    st.subheader("References")
                    for citation in citations:
                        # Only show fields the source document actually had.
                        parts = [
                            f"**{citation['scheme_name']}**"
                            if citation.get("scheme_name")
                            else None,
                            f"Circular: {citation['circular_reference']}"
                            if citation.get("circular_reference")
                            else None,
                            citation.get("section"),
                            f"Source: {citation['source']}"
                            if citation.get("source")
                            else None,
                        ]
                        st.markdown("- " + " | ".join(p for p in parts if p))

                st.caption(f"Based on {result['evidence_count']} regulation extract(s).")
