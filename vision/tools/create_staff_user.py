"""Create or reset a PostgreSQL-backed staff login."""
from __future__ import annotations

import argparse
import getpass
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from o2gauge import postgres_store as store
from o2gauge.postgres_api import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=("staff", "admin"), default="staff")
    parser.add_argument("--name", default="")
    parser.add_argument("--order", type=int, default=1)
    parser.add_argument("--off-duty", action="store_true")
    args = parser.parse_args()
    if args.order < 1:
        parser.error("--order must be a positive integer")
    if not store.configured():
        parser.error("Set DATABASE_URL and install vision/requirements-run.txt first")
    if len(os.getenv("AUTH_SECRET", "")) < 32:
        parser.error("Set AUTH_SECRET to a random value of at least 32 characters in the backend .env")
    password = getpass.getpass("Set staff password (minimum 10 characters): ")
    confirm = getpass.getpass("Repeat password: ")
    if password != confirm:
        parser.error("Passwords do not match")
    encoded = hash_password(password)
    email = args.email.strip().lower()
    if not email or "@" not in email:
        parser.error("Enter a valid email address")
    with store.connection() as conn:
        existing = conn.execute("SELECT uid FROM staff WHERE lower(email)=lower(%s)", (email,)).fetchone()
        uid = existing["uid"] if existing else str(uuid.uuid4())
        conn.execute(
            """INSERT INTO staff(uid,email,display_name,role,password_hash,is_active,on_duty,escalation_order)
               VALUES (%s,%s,%s,%s,%s,TRUE,%s,%s)
               ON CONFLICT(uid) DO UPDATE SET email=EXCLUDED.email,display_name=EXCLUDED.display_name,
                 role=EXCLUDED.role,password_hash=EXCLUDED.password_hash,is_active=TRUE,
                 on_duty=EXCLUDED.on_duty,escalation_order=EXCLUDED.escalation_order,updated_at=NOW()""",
            (uid, email, args.name.strip(), args.role, encoded, not args.off_duty, args.order),
        )
    print(f"PostgreSQL {args.role} account ready: {email} (escalation order {args.order}).")


if __name__ == "__main__":
    main()
