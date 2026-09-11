"""Streamlit page for Module 5: Proactive Eligibility Nudge."""

import streamlit as st
from requests import HTTPError

from utils.api_client import get, post
from utils.auth import current_role, sidebar_login

st.title("Proactive Eligibility Nudge")
st.write(
    "Answer the server-defined questionnaire for a scheme. The result is "
    "advisory and does not block appointments or document upload."
)

token = sidebar_login()
role = current_role()


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


if not token:
    st.info("Please sign in from the sidebar to run an eligibility check.")
else:
    try:
        regulations = get("/regulations", token=token)
    except HTTPError as error:
        st.error(describe_error(error))
        regulations = []
    except Exception:
        st.error("Backend is not reachable.")
        regulations = []

    if not regulations:
        st.warning("No schemes are registered yet. An administrator can add one.")
    else:
        chosen = st.selectbox(
            "Scheme",
            regulations,
            format_func=lambda row: f"#{row['regulation_id']} {row['scheme_name']}",
        )
        questionnaire = None
        if chosen:
            try:
                questionnaire = get(
                    f"/eligibility/questionnaire/{chosen['regulation_id']}",
                    token=token,
                )
            except HTTPError as error:
                st.error(describe_error(error))

        if questionnaire:
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
                    st.error(describe_error(error))
                else:
                    st.session_state["last_eligibility"] = result

            last = st.session_state.get("last_eligibility")
            if last:
                st.subheader("Latest result")
                st.write(last["result"])
                st.write(last.get("explanation") or "")
                if last.get("missing_documents"):
                    st.warning(
                        "Missing verified documents: "
                        + ", ".join(last["missing_documents"])
                    )
                st.caption(
                    "This is an advisory screening. It is not a final government decision."
                )

    if role == "citizen":
        st.subheader("Your previous checks")
        try:
            previous = get("/eligibility/checks", token=token)["checks"]
        except HTTPError:
            previous = []
        except Exception:
            previous = []
        if not previous:
            st.caption("No eligibility checks yet.")
        for item in previous:
            with st.expander(
                f"#{item['check_id']} {item.get('scheme_name') or 'scheme'} ({item['result']})"
            ):
                st.write(item.get("explanation") or "")
                if item.get("missing_documents"):
                    st.caption("Missing: " + ", ".join(item["missing_documents"]))
    elif role in ("officer", "administrator"):
        st.caption("Citizens submit checks. Staff can review stored results through the API.")
