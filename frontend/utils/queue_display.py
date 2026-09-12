"""Officer queue presentation helpers.

These format and order appointment cards. They do not call the API or change
stored predicted_wait_time values. Calendar dates use OFFICE_TIMEZONE from the
same .env file the rest of the frontend reads.
"""

import os
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def office_tz() -> tzinfo:
    """The configured office timezone. Appointment instants stay UTC."""
    name = (os.getenv("OFFICE_TIMEZONE") or "UTC").strip()
    if name.upper() == "UTC":
        return timezone.utc
    return ZoneInfo(name)


def parse_appointment_date(value: Any) -> datetime:
    """Parse appointment_date to a timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = datetime.max.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def office_local_datetime(value: Any, zone: tzinfo | None = None) -> datetime:
    """API timestamp converted to the office's local clock."""
    return parse_appointment_date(value).astimezone(zone or office_tz())


def office_calendar_date(value: Any, zone: tzinfo | None = None):
    """Office-local calendar date used for display and sorting."""
    return office_local_datetime(value, zone).date()


def format_appointment_date(value: Any, zone: tzinfo | None = None) -> str:
    """Human date such as '15 September 2026' in OFFICE_TIMEZONE."""
    local = office_local_datetime(value, zone)
    if local.year >= datetime.max.year:
        return "Unknown"
    return f"{local.day} {local.strftime('%B %Y')}"


def format_predicted_wait(value: Any) -> str:
    """Display at most two decimal places without changing the stored number."""
    if value is None:
        return "n/a"
    number = round(float(value), 2)
    if number == int(number):
        return f"{number:.1f}"
    return f"{number:.2f}"


def _sort_appointments(
    rows: list[dict], zone: tzinfo | None = None
) -> list[dict]:
    """Office-local calendar date, then queue_number, then appointment_id."""
    local_zone = zone or office_tz()

    def sort_key(row: dict) -> tuple:
        queue_number = row.get("queue_number")
        appointment_id = row.get("appointment_id")
        return (
            office_calendar_date(row.get("appointment_date"), local_zone),
            queue_number if queue_number is not None else float("inf"),
            appointment_id if appointment_id is not None else 0,
        )

    return sorted(rows, key=sort_key)


def sort_officer_appointments(
    rows: list[dict], zone: tzinfo | None = None
) -> list[dict]:
    """Order officer live-queue cards by office-local date."""
    return _sort_appointments(rows, zone)


def sort_citizen_appointments(
    rows: list[dict], zone: tzinfo | None = None
) -> list[dict]:
    """Order citizen appointment cards by office-local date."""
    return _sort_appointments(rows, zone)
