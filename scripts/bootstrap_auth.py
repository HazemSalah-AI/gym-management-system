import argparse
import getpass
import hmac
import warnings

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.repositories.bootstrap import BootstrapRepository
from app.schemas.auth import AdminInput
from app.services.bootstrap import BootstrapConflict, create_first_admin, seed_auth


def read_admin_input() -> AdminInput:
    username = input("Admin username: ")
    email = input("Admin email: ")
    # Abort if secure terminal input is unavailable; never fall back to echoing.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Admin password (12+ characters): ")
        confirmation = getpass.getpass("Confirm password: ")
    if not hmac.compare_digest(password.encode("utf-8"), confirmation.encode("utf-8")):
        raise BootstrapConflict("Passwords do not match.")
    return AdminInput(username=username, email=email, password=password)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed RBAC and securely create the first Admin.")
    parser.add_argument("--seed-only", action="store_true", help="Update roles/permissions without creating an Admin")
    args = parser.parse_args(argv)
    try:
        with SessionLocal() as db:
            seed_auth(db)
            print("Roles and permissions synchronized.")
            if args.seed_only:
                return 0
            if BootstrapRepository(db).has_admin():
                print("An Admin already exists; no account was changed.")
                return 0
            db.rollback()  # Release the read transaction before waiting for input.
            values = read_admin_input()
            create_first_admin(db, values)
            print("Initial Admin created successfully.")
            return 0
    except ValidationError:
        print(
            "Invalid input: username must be 3-50 lowercase letters/digits/._-, email valid, password 12-1024 characters."
        )
    except BootstrapConflict as exc:
        print(str(exc))
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("Admin creation cancelled. Run this command in an interactive terminal with hidden password input.")
    except SQLAlchemyError:
        print("Database operation failed. Check connectivity and migrations; no credentials are printed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
