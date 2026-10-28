"""Manage approver identities for the workbench's L1/L2 approvals.

    python scripts/approvers.py add --name "Asha Rao" --role L1    # prints the key once
    python scripts/approvers.py list

Only a SHA-256 of each key is stored (secrets/approvers.json, git-ignored). Hand the printed key to
the approver; it cannot be recovered later, only replaced by adding a new approver.
"""

import argparse

from redthread.api import auth


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--name", required=True)
    add.add_argument("--role", required=True, choices=auth.ROLES)
    sub.add_parser("list")
    args = parser.parse_args()

    if args.command == "add":
        approver, key = auth.add(args.name, args.role)
        print(f"{approver.id}  {approver.name}  {approver.role}")
        print(f"key (shown once): {key}")
    else:
        import json
        f = auth.approvers_file()
        for e in (json.loads(f.read_text(encoding="utf-8")) if f.exists() else []):
            print(f"{e['id']}  {e['name']}  {e['role']}")


if __name__ == "__main__":
    main()
