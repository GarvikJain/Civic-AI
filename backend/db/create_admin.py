"""Create the first administrator account.

Administrator and officer accounts can only be created by an administrator, so
the very first administrator has to be made from the command line:

    python -m backend.db.create_admin "Full Name" admin@example.com

The password is asked for interactively so it does not end up in the shell
history.
"""

import sys
from getpass import getpass

from backend.core.roles import Role
from backend.db.init_db import init_db
from backend.db.session import SessionLocal
from backend.schemas.user import UserRegister
from backend.services import auth_service


def create_administrator(full_name: str, email: str, password: str) -> None:
    """Add one administrator, unless the email is already taken."""
    init_db()
    db = SessionLocal()
    try:
        if auth_service.get_user_by_email(db, email):
            print(f"A user with email {email} already exists.")
            return
        data = UserRegister(full_name=full_name, email=email, password=password)
        user = auth_service.create_user(db, data, role=Role.ADMINISTRATOR)
        print(f"Administrator created: {user.email}")
    finally:
        db.close()


def main() -> None:
    if len(sys.argv) != 3:
        print('Usage: python -m backend.db.create_admin "Full Name" email@example.com')
        raise SystemExit(1)

    full_name, email = sys.argv[1], sys.argv[2]
    password = getpass("Password (at least 8 characters): ")
    create_administrator(full_name, email, password)


if __name__ == "__main__":
    main()
