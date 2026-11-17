"""Interactive helper: `python -m security_station.set_password` (or `make set-password`)."""
import getpass
import sys

from .auth import PasswordStore

MIN_LENGTH = 4


def main() -> int:
    store = PasswordStore()
    first = getpass.getpass("New station password: ")
    if len(first) < MIN_LENGTH:
        print(f"Password must be at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Repeat password: ") != first:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    store.set_password(first)
    print(f"Password updated in {store.path} (stored as a salted scrypt hash).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
