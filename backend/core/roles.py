"""User roles used for access control.

Keeping the roles in one enum means routes never compare raw strings.
"""

from enum import Enum


class Role(str, Enum):
    CITIZEN = "citizen"
    OFFICER = "officer"
    ADMINISTRATOR = "administrator"
