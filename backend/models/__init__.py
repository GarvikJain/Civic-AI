"""Database models for CivicAI.

Importing every model here registers it on Base.metadata, so
Base.metadata.create_all() creates all tables and relationship() strings
resolve correctly.
"""

from backend.models.appointment import Appointment
from backend.models.citizen import Citizen
from backend.models.citizen_query import CitizenQuery
from backend.models.eligibility_check import EligibilityCheck
from backend.models.feedback import Feedback
from backend.models.government_document import GovernmentDocument
from backend.models.officer import Officer
from backend.models.queue_prediction_record import QueuePredictionRecord
from backend.models.regulation import Regulation
from backend.models.user import User

__all__ = [
    "Appointment",
    "Citizen",
    "CitizenQuery",
    "EligibilityCheck",
    "Feedback",
    "GovernmentDocument",
    "Officer",
    "QueuePredictionRecord",
    "Regulation",
    "User",
]
