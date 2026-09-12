"""Streamlit page for Module 1: Regulation RAG Assistant."""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, patch, post
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

    st.subheader("Administrator: update existing regulation")
    st.caption(
        "Structured eligibility fields are maintained here. Ingested RAG "
        "documents are not replaced."
    )
    try:
        existing = get("/regulations", token=token)
    except HTTPError as error:
        detail = error.response.text
        try:
            detail = error.response.json().get("detail", detail)
        except ValueError:
            pass
        st.error(detail)
        existing = []
    except Exception:
        st.error("Backend is not reachable.")
        existing = []

    if not existing:
        st.caption("No schemes are registered yet.")
    else:
        selected = st.selectbox(
            "Regulation",
            existing,
            format_func=lambda row: f"#{row['regulation_id']} {row['scheme_name']}",
            key="update-regulation-choice",
        )
        with st.form("update-regulation"):
            update_name = st.text_input("Scheme name", value=selected["scheme_name"])
            update_department = st.text_input("Department", value=selected["department"])
            update_criteria = st.text_area(
                "Eligibility criteria",
                value=selected.get("eligibility_criteria") or "",
                height=80,
            )
            update_documents = st.text_area(
                "Required documents",
                value=selected.get("required_documents") or "",
                height=60,
            )
            update_circular = st.text_input(
                "Circular reference",
                value=selected.get("circular_reference") or "",
            )
            updated = st.form_submit_button("Update regulation")
        if updated:
            if not update_name.strip() or not update_department.strip():
                st.warning("Scheme name and department are required.")
            else:
                try:
                    result = patch(
                        f"/regulations/{selected['regulation_id']}",
                        {
                            "scheme_name": update_name.strip(),
                            "department": update_department.strip(),
                            "eligibility_criteria": update_criteria.strip() or None,
                            "required_documents": update_documents.strip() or None,
                            "circular_reference": update_circular.strip() or None,
                        },
                        token=token,
                    )
                    st.success(
                        f"Updated regulation #{result['regulation_id']} "
                        f"({result['scheme_name']})."
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
