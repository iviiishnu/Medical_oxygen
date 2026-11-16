"""Set a Firebase Auth custom role and provision its PostgreSQL staff profile.

Example:
  python vision/tools/set_staff_role.py --email nurse@example.org --role staff --name "Nurse 1" --order 1
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import firebase_admin
from firebase_admin import auth
from o2gauge import postgres_store as store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=("staff", "admin"), required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--order", type=int, default=1)
    parser.add_argument("--off-duty", action="store_true")
    args = parser.parse_args()
    if args.order < 1:
        parser.error("--order must be a positive integer")
    if not store.configured():
        parser.error("Set DATABASE_URL and install vision/requirements-run.txt first")

    project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCLOUD_PROJECT")
    firebase_admin.initialize_app(options={"projectId": project_id} if project_id else None)
    user = auth.get_user_by_email(args.email)
    if args.name:
        user = auth.update_user(user.uid, display_name=args.name)
    claims = dict(user.custom_claims or {})
    claims["role"] = args.role
    auth.set_custom_user_claims(user.uid, claims)

    display_name = args.name or user.display_name or ""
    with store.connection() as conn:
        conn.execute(
            """INSERT INTO staff(uid,email,display_name,role,on_duty,escalation_order)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT(uid) DO UPDATE SET email=EXCLUDED.email,display_name=EXCLUDED.display_name,
                 role=EXCLUDED.role,on_duty=EXCLUDED.on_duty,escalation_order=EXCLUDED.escalation_order,updated_at=NOW()""",
            (user.uid, user.email or args.email, display_name, args.role, not args.off_duty, args.order),
        )
    print(f"Provisioned {args.role} {args.email} in Firebase Auth and PostgreSQL (escalation order {args.order}).")
    print("The user must sign out and sign in again for the updated custom role to appear in their ID token.")


if __name__ == "__main__":
    main()
