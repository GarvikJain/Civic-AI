"""Streamlit page for Module 5: Proactive Eligibility Nudge."""

import html

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post
from utils.auth import current_role, sidebar_login
from utils.ui import (
    apply_content_width,
    empty_state,
    info_rows,
    kicker,
    page_hero,
    surface,
    workflow_steps,
)

RESULT_LABELS = {
    "eligible": "Eligible",
    "potentially_ineligible": "Potentially ineligible",
    "manual_review": "Manual review",
}
RESULT_SURFACES = {
    "eligible": "civicai-eligible",
    "potentially_ineligible": "civicai-ineligible",
    "manual_review": "civicai-manual",
}
_FAILED_MARK = " Failed criteria: "
_UNCERTAIN_MARK = " Uncertain criteria: "
_MISSING_MARK = " Required document may be missing: "

token = sidebar_login()
role = current_role()
apply_content_width()

page_hero(
    "Eligibility Nudge",
    "Check whether you appear to meet the scheme criteria before preparing your documents.",
    badge="Preliminary guidance",
)
workflow_steps(
    ("Answer questions", "Criteria check", "Eligibility guidance", "Documents to prepare")
)


def describe_error(error: HTTPError) -> str:
    try:
        return error.response.json().get("detail", error.response.text)
    except ValueError:
        return error.response.text


def collect_answer(question: dict):
    key = f"elig-{question['question_id']}"
    answer_type = question.get("answer_type")
    label = question["question_text"]
    if answer_type == "boolean":
        return st.checkbox(label, key=key)
    if answer_type == "integer":
        return st.number_input(label, min_value=0, step=1000, key=key)
    if answer_type == "decimal":
        return st.number_input(label, min_value=0.0, step=0.1, key=key)
    if answer_type == "choice":
        options = question.get("options") or []
        return st.selectbox(label, options, key=key) if options else st.text_input(label, key=key)
    if answer_type == "date":
        value = st.date_input(label, key=key)
        return value.isoformat() if value else None
    return st.text_input(label, key=key)


def _parts(text: str, mark: str) -> tuple[str, list[str]]:
    if mark not in text:
        return text, []
    head, tail = text.split(mark, 1)
    items = [part.strip(" .") for part in tail.split(";") if part.strip(" .")]
    return head.rstrip(), items


def split_guidance(explanation: str | None) -> tuple[str, list[str], list[str]]:
    """Format the backend explanation. The meaning of each clause is unchanged."""
    text = (explanation or "").strip()
    text, _missing_in_text = _parts(text, _MISSING_MARK)
    text, uncertain = _parts(text, _UNCERTAIN_MARK)
    text, failed = _parts(text, _FAILED_MARK)
    return text, failed, uncertain


def _bullet_list(items: list[str]) -> None:
    for item in items:
        st.markdown(f"- {item}")


def show_eligibility_result(result: dict, *, slot: str) -> None:
    state = result["result"]
    label = RESULT_LABELS.get(state, state)
    surface_name = RESULT_SURFACES.get(state, "civicai-manual")
    guidance, failed, uncertain = split_guidance(result.get("explanation"))
    missing = list(result.get("missing_documents") or [])

    with surface(f"{surface_name}-{slot}"):
        kicker("Eligibility guidance")
        st.markdown(
            f'<p class="civicai-status-reason">{html.escape(label)}</p>',
            unsafe_allow_html=True,
        )
        if guidance:
            st.write(guidance)
        if failed:
            st.markdown("**Failed criteria**")
            _bullet_list(failed)
        if uncertain:
            st.markdown("**Uncertain criteria**")
            _bullet_list(uncertain)
        if missing:
            st.markdown("**Documents to prepare**")
            st.caption("Missing verified documents:")
            _bullet_list(missing)
            st.caption(
                "This warning is about verified documents on file. "
                "It does not change the eligibility result above."
            )
        st.caption(
            "This is an advisory screening. It is not a final government decision."
        )


if not token:
    st.info("Please sign in from the sidebar to run an eligibility check.")
else:
    try:
        regulations = get("/regulations", token=token)
    except HTTPError as error:
        with surface("civicai-query-error-regulations"):
            st.error(describe_error(error))
        regulations = []
    except Exception:
        with surface("civicai-query-error-regulations"):
            st.error("Backend is not reachable.")
        regulations = []

    if not regulations:
        st.warning("No schemes are registered yet. An administrator can add one.")
    else:
        with surface("civicai-scheme"):
            kicker("Scheme")
            st.subheader("Select a scheme")
            chosen = st.selectbox(
                "Scheme",
                regulations,
                format_func=lambda row: f"#{row['regulation_id']} {row['scheme_name']}",
            )
            if chosen:
                info_rows(
                    (
                        ("Scheme", chosen.get("scheme_name")),
                        ("Regulation ID", f"#{chosen['regulation_id']}"),
                        ("Department", chosen.get("department")),
                    )
                )
        questionnaire = None
        if chosen:
            try:
                questionnaire = get(
                    f"/eligibility/questionnaire/{chosen['regulation_id']}",
                    token=token,
                )
            except HTTPError as error:
                with surface("civicai-query-error-questionnaire"):
                    st.error(describe_error(error))

        if questionnaire:
            with surface("civicai-questions"):
                kicker("Questionnaire")
                st.subheader("Eligibility questions")
                st.info(questionnaire["advisory_notice"])
                if questionnaire.get("unsupported_criteria"):
                    st.caption(
                        "Some criteria need manual review: "
                        + "; ".join(questionnaire["unsupported_criteria"])
                    )
                answers = {}
                for question in questionnaire["questions"]:
                    answers[question["field_name"]] = collect_answer(question)

                if role == "citizen" and st.button("Check eligibility", type="primary"):
                    try:
                        result = post(
                            "/eligibility/check",
                            {
                                "regulation_id": questionnaire["regulation_id"],
                                "answers": answers,
                            },
                            token=token,
                        )
                    except HTTPError as error:
                        with surface("civicai-query-error-check"):
                            st.error(describe_error(error))
                    else:
                        st.session_state["last_eligibility"] = result

            last = st.session_state.get("last_eligibility")
            if last:
                show_eligibility_result(last, slot="latest")

    if role == "citizen":
        with surface("civicai-history"):
            kicker("History")
            st.subheader("Your previous checks")
            try:
                previous = get("/eligibility/checks", token=token)["checks"]
            except HTTPError:
                previous = []
            except Exception:
                previous = []
            if not previous:
                empty_state("No eligibility checks yet.")
            for item in previous:
                with st.expander(
                    f"#{item['check_id']} {item.get('scheme_name') or 'scheme'} "
                    f"({RESULT_LABELS.get(item['result'], item['result'])})"
                ):
                    show_eligibility_result(item, slot=f"history-{item['check_id']}")
    elif role in ("officer", "administrator"):
        st.caption("Citizens submit checks. Staff can review stored results through the API.")
