"""Officer queue card sorting and display formatting."""

import sys
from datetime import datetime, timezone
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

from zoneinfo import ZoneInfo

from utils.queue_display import (
    format_appointment_date,
    format_predicted_wait,
    office_calendar_date,
    sort_officer_appointments,
)

IST = ZoneInfo("Asia/Kolkata")

QUEUE_PAGE = FRONTEND / "pages" / "3_Queue_Wait_Time.py"


def test_queue_display_does_not_import_the_backend_package():
    text = (FRONTEND / "utils" / "queue_display.py").read_text(encoding="utf-8")
    assert "from backend" not in text
    assert "import backend" not in text
    assert "OFFICE_TIMEZONE" in text


def test_officer_queue_page_shows_date_and_sorted_cards():
    text = QUEUE_PAGE.read_text(encoding="utf-8")
    assert "Appointment date:" in text
    assert "sort_officer_appointments" in text
    assert "format_predicted_wait" in text
    assert "format_appointment_date" in text


def test_appointment_date_is_formatted_from_the_api_timestamp():
    assert (
        format_appointment_date("2026-09-15T10:00:00+00:00") == "15 September 2026"
    )
    assert format_appointment_date("2026-09-05T08:30:00") == "5 September 2026"


def test_predicted_wait_is_shown_to_at_most_two_decimals():
    assert format_predicted_wait(1.4771546416424393) == "1.48"
    assert format_predicted_wait(0.0) == "0.0"
    assert format_predicted_wait(None) == "n/a"


def test_officer_appointments_sort_by_parsed_date_then_queue_number():
    rows = [
        {
            "appointment_id": 9,
            "appointment_date": "2026-09-16T09:00:00+00:00",
            "queue_number": 1,
        },
        {
            "appointment_id": 3,
            "appointment_date": "2026-09-15T16:00:00+00:00",
            "queue_number": 2,
        },
        {
            "appointment_id": 8,
            "appointment_date": "2026-09-15T08:00:00+00:00",
            "queue_number": 2,
        },
        {
            "appointment_id": 4,
            "appointment_date": "2026-09-15T08:00:00+00:00",
            "queue_number": 1,
        },
    ]
    ordered = sort_officer_appointments(rows)
    assert [row["appointment_id"] for row in ordered] == [4, 3, 8, 9]
    dates = [
        office_calendar_date(row["appointment_date"], timezone.utc) for row in ordered
    ]
    assert dates == sorted(dates)
    assert dates[0] == datetime(2026, 9, 15, tzinfo=timezone.utc).date()
    assert dates[-1] == datetime(2026, 9, 16, tzinfo=timezone.utc).date()
    # Same calendar date uses queue_number, then appointment_id — not clock time.
    assert [row["queue_number"] for row in ordered[:3]] == [1, 2, 2]


def test_office_timezone_date_crosses_utc_calendar_boundary():
    """14 Sep 20:00 UTC is 15 Sep in UTC+05:30, matching backend office days."""
    stamp = "2026-09-14T20:00:00+00:00"
    assert format_appointment_date(stamp, zone=IST) == "15 September 2026"
    assert office_calendar_date(stamp, zone=IST) == datetime(2026, 9, 15).date()
    assert office_calendar_date(stamp, zone=timezone.utc) == datetime(2026, 9, 14).date()

    rows = [
        {
            "appointment_id": 2,
            "appointment_date": "2026-09-14T20:00:00+00:00",
            "queue_number": 2,
        },
        {
            "appointment_id": 1,
            "appointment_date": "2026-09-14T10:00:00+00:00",
            "queue_number": 1,
        },
        {
            "appointment_id": 3,
            "appointment_date": "2026-09-15T10:00:00+00:00",
            "queue_number": 1,
        },
    ]
    ordered = sort_officer_appointments(rows, zone=IST)
    assert [row["appointment_id"] for row in ordered] == [1, 3, 2]
