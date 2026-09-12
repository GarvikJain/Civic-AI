"""Frontend presentation checks for Queue Wait Time."""

import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

from utils.auth_store import COOKIE_NAME, DictTokenStore

PAGE = FRONTEND / "pages" / "3_Queue_Wait_Time.py"


def test_page_source_keeps_booking_and_officer_contracts():
    page = PAGE.read_text(encoding="utf-8")
    assert 'st.selectbox("Service", SERVICE_TYPES)' in page
    assert 'st.date_input("Visit date", value=default.date())' in page
    assert 'st.time_input("Visit time", value=time(10, 0))' in page
    assert 'st.button("Create appointment", type="primary")' in page
    assert '"/queue/appointments"' in page
    assert '"appointment_date": when.isoformat()' in page
    assert "sort_citizen_appointments" in page
    assert "sort_officer_appointments" in page
    assert "Start service" in page
    assert "Complete service" in page
    assert "Cancel" in page
    assert 'st.error("Backend is not reachable.")' in page


def test_page_source_uses_civic_queue_surfaces():
    page = PAGE.read_text(encoding="utf-8")
    assert "page_hero" in page
    assert "Queue Wait Time" in page
    assert "Live queue prediction" in page
    assert "Book a visit" in page
    assert "Your appointments" in page
    assert "civicai-book" in page
    assert "civicai-appointments" in page
    assert "civicai-officer" in page


def test_streamlit_theme_keeps_light_form_controls():
    config = (FRONTEND.parent / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'base = "light"' in config
    assert 'secondaryBackgroundColor = "#FFFFFF"' in config
    assert "maxUploadSize = 10" in config


def _identity(role: str, email: str, name: str, user_id: int = 1) -> dict:
    return {
        "id": user_id,
        "email": email,
        "role": role,
        "full_name": name,
        "is_active": True,
    }


def _run_page(monkeypatch, *, role: str, get_impl):
    from streamlit.testing.v1 import AppTest

    import utils.api_client as api_client
    import utils.auth as auth

    store = DictTokenStore({COOKIE_NAME: f"jwt-{role}"})
    monkeypatch.setattr(auth, "get_browser_token_store", lambda: store)

    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/auth/me":
            return _identity(role, f"{role}@example.com", f"Test {role.title()}")
        return get_impl(path, token=token, params=params, timeout=timeout)

    monkeypatch.setattr(auth, "get", fake_get)
    monkeypatch.setattr(api_client, "get", fake_get)
    monkeypatch.setattr(api_client, "post", lambda *args, **kwargs: {})
    monkeypatch.setattr(auth, "post", lambda *args, **kwargs: {"access_token": "x"})

    at = AppTest.from_file(str(PAGE), default_timeout=10)
    at.run()
    assert not at.exception
    return at


def test_apptest_logged_out_shows_hero(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import utils.auth as auth

    monkeypatch.setattr(auth, "get_browser_token_store", lambda: DictTokenStore())
    at = AppTest.from_file(str(PAGE), default_timeout=10)
    at.run()
    assert not at.exception
    body = " ".join(str(item.value) for item in at.markdown)
    assert "Queue Wait Time" in body
    assert "Live queue prediction" in body
    assert any("Please sign in from the sidebar to use the queue." in str(item.value) for item in at.info)


def test_apptest_citizen_booking_controls_and_empty_list(monkeypatch):
    at = _run_page(monkeypatch, role="citizen", get_impl=lambda *args, **kwargs: [])
    assert any(item.value == "Book a visit" for item in at.subheader)
    assert any(item.value == "Your appointments" for item in at.subheader)
    assert any(button.label == "Create appointment" for button in at.button)
    assert at.selectbox
    assert at.date_input
    assert at.time_input
    body = " ".join(str(item.value) for item in at.markdown)
    assert "You have no appointments yet." in body


def test_apptest_citizen_appointment_shows_prediction_and_date(monkeypatch):
    appointments = [
        {
            "appointment_id": 4,
            "service_type": "Income Certificate",
            "appointment_date": "2026-09-15T10:00:00+00:00",
            "queue_number": 2,
            "predicted_wait_time": 12.35,
            "current_queue_depth": 3,
            "status": "scheduled",
            "officer_id": None,
        }
    ]
    at = _run_page(monkeypatch, role="citizen", get_impl=lambda *args, **kwargs: appointments)
    assert any("Predicted wait" in str(item.value) for item in at.markdown)
    assert any("12.35 minutes" in str(item.value) for item in at.markdown)
    assert any("Appointment date: 15 September 2026" in str(item.value) for item in at.markdown)
    assert any("Queue number: 2" in str(item.value) for item in at.text) or any(
        "Queue number: 2" in str(item.value) for item in at.markdown
    )
    assert any(button.label == "Cancel" for button in at.button)
    assert any("Scheduled" in str(item.value) for item in at.markdown)


def test_apptest_officer_queue_preserves_actions(monkeypatch):
    def fake_get(path, token=None, params=None, timeout=None):
        if path == "/queue/status":
            return {
                "appointments": [
                    {
                        "appointment_id": 8,
                        "service_type": "Birth Certificate",
                        "appointment_date": "2026-09-16T09:00:00+00:00",
                        "queue_number": 1,
                        "predicted_wait_time": 4.0,
                        "current_queue_depth": 1,
                        "status": "scheduled",
                    }
                ],
                "queues": [
                    {
                        "service_type": "Birth Certificate",
                        "appointment_date": "2026-09-16",
                        "current_queue_depth": 1,
                    }
                ],
            }
        return {}

    at = _run_page(monkeypatch, role="officer", get_impl=fake_get)
    assert any(item.value == "Live office queue" for item in at.subheader)
    assert any(button.label == "Start service" for button in at.button)
    assert any(button.label == "Complete service" for button in at.button)
    assert not any(button.label == "Create appointment" for button in at.button)
    assert any("Appointment date: 16 September 2026" in str(item.value) for item in at.markdown)
