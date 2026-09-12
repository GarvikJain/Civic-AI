"""Streamlit page for Module 1: Regulation RAG Assistant."""

import streamlit as st
from requests import HTTPError, Timeout

from utils.api_client import get, patch, post
from utils.auth import current_role, sidebar_login
from utils.ui import (
    apply_content_width,
    kicker,
    page_hero,
    render_citations,
    section_header,
    surface,
)

token = sidebar_login()
role = current_role()
apply_content_width()

page_hero(
    "Regulation RAG Assistant",
    "Get answers from official government regulations with supporting citations.",
    badge="Official sources only",
)

if role == "administrator" and token:
    with surface("civicai-admin"):
        section_header("Administrator: register a scheme")
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

        section_header("Administrator: update existing regulation")
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

with surface("civicai-ask"):
    kicker("Ask a question")
    st.markdown(
        '<h2 class="civicai-section-title">Ask about a government scheme</h2>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="civicai-section-caption">Enter a question about eligibility, '
        "required documents, procedures, or regulations.</p>",
        unsafe_allow_html=True,
    )
    question = st.text_area(
        "Your question",
        placeholder="What documents do I need for an income certificate?",
        height=100,
    )
    asked = st.button("Ask", type="primary")

if asked:
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
                with surface("civicai-query-error"):
                    if response.status_code == 503:
                        st.error(f"The assistant is not available: {detail}")
                    else:
                        st.error(f"Request failed ({response.status_code}): {detail}")
                result = None
            except Timeout:
                with surface("civicai-timeout"):
                    st.info(
                        "The AI assistant may still be initializing. The first "
                        "question can take longer than usual. Please try again.",
                        title="Assistant initializing",
                    )
                result = None
            except Exception:
                with surface("civicai-query-error"):
                    st.error("Backend is not reachable.")
                result = None

        if result:
            if result["insufficient_evidence"]:
                with surface("civicai-warning"):
                    st.subheader("Insufficient evidence")
                    st.warning(result["answer"])
            else:
                with surface("civicai-answer"):
                    st.subheader("Answer")
                    st.write(result["answer"])
                    st.caption(
                        f"Based on {result['evidence_count']} regulation extract(s)."
                    )

                citations = result.get("citations") or []
                if citations:
                    with surface("civicai-citations"):
                        st.subheader("Sources & Citations")
                        render_citations(citations)
else:
    st.caption(
        "Official answers and citations will appear here after you ask a question."
    )
