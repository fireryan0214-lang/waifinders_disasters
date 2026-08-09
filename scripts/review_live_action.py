"""Record a named operator's approval or rejection of one exposure action."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from live_incident_exposure import OUT_PATH, REVIEW_PATH


def main():
    parser = argparse.ArgumentParser(description="Approve or reject a WAIFINDERS exposure action")
    parser.add_argument("--action-id", required=True)
    parser.add_argument("--decision", required=True, choices=["APPROVED", "REJECTED"])
    parser.add_argument("--reviewer", required=True, help="Named trained operator making the decision")
    parser.add_argument("--note", required=True, help="Reason for the approval or rejection")
    args = parser.parse_args()

    if not OUT_PATH.exists():
        raise SystemExit("No live action output found. Run live_incident_exposure.py first.")
    current = json.loads(OUT_PATH.read_text())
    valid_ids = {action["action_id"] for action in current.get("actions", [])}
    if args.action_id not in valid_ids:
        raise SystemExit("Action ID is not in the current live exposure queue; refresh and review the current queue first.")
    records = json.loads(REVIEW_PATH.read_text()) if REVIEW_PATH.exists() else []
    records = [record for record in records if record["action_id"] != args.action_id]
    records.append({"action_id": args.action_id, "decision": args.decision, "reviewer": args.reviewer, "note": args.note, "reviewed_utc": datetime.now(timezone.utc).isoformat()})
    REVIEW_PATH.write_text(json.dumps(records, indent=2))
    print(f"{args.decision}: {args.action_id} by {args.reviewer}. Refresh the live exposure output to apply it.")


if __name__ == "__main__":
    main()
