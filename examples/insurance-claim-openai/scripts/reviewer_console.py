"""Claims-examiner console — the human side of the review gate.

Lists pending claim reviews with the agent's proposed per-line adjudication and
lets an examiner resolve them. A *reject* or *modify* against the agent's proposal
sets ``is_override = true`` — the appeal / audit evidence that a human owned the
denial, reduction, or pend.

Run in a second terminal while the agent (or scripts/run_demo.py) is blocked on
the gate:

    python -m scripts.reviewer_console          # interactive
    python -m scripts.reviewer_console auto      # unattended: confirm the next one

Uses the admin DSN: the human examiner is a distinct actor from the agent and
must be able to write the final disposition the agent's role only proposes.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys

import asyncpg
from dotenv import load_dotenv

load_dotenv()


def _admin_dsn() -> str:
    host = os.environ.get("ADMIN_DB_HOST", "localhost")
    port = os.environ.get("ADMIN_DB_PORT", "5433")
    user = os.environ.get("ADMIN_DB_USER", "postgres")
    pw = os.environ.get("ADMIN_DB_PASSWORD", "postgres")
    return f"postgresql://{user}:{pw}@{host}:{port}/mimic_payer"


async def _pending(conn) -> list:
    return await conn.fetch(
        "SELECT id, claim_id, payload FROM agent.approvals WHERE status = 'pending' "
        "ORDER BY created_at"
    )


async def _lines_for(conn, claim_id: str) -> list:
    return await conn.fetch(
        "SELECT line_number, decision, plan_paid_cents, patient_resp_cents, carc, rationale "
        "FROM agent.decisions WHERE claim_id = $1 ORDER BY line_number", claim_id
    )


async def resolve(
    *,
    approval_id: str,
    action: str,                       # confirm | reject | modify
    decided_by: str,
    justification: str,
    line_overrides: dict | None = None,
) -> None:
    """Programmatic resolver (used by the console and by the demo)."""
    conn = await asyncpg.connect(_admin_dsn())
    try:
        appr = await conn.fetchrow(
            "SELECT claim_id FROM agent.approvals WHERE id = $1",
            __import__("uuid").UUID(approval_id),
        )
        if appr is None:
            raise SystemExit(f"approval {approval_id} not found")
        claim_id = appr["claim_id"]

        if action == "confirm":
            status, is_override, overrides = "confirmed", False, {}
        elif action == "modify":
            status, is_override, overrides = "modified", True, (line_overrides or {})
        elif action == "reject":
            status, is_override = "rejected", True
            rows = await _lines_for(conn, claim_id)
            overrides = {str(r["line_number"]): {"decision": "deny", "plan_paid_cents": 0}
                         for r in rows}
        else:
            raise SystemExit(f"unknown action {action!r}")

        async with conn.transaction():
            await conn.execute(
                """UPDATE agent.approvals SET status=$1, is_override=$2, decided_by=$3,
                   justification=$4, line_overrides=$5::jsonb, decided_at=$6 WHERE id=$7""",
                status, is_override, decided_by, justification, json.dumps(overrides),
                dt.datetime.now(dt.timezone.utc), __import__("uuid").UUID(approval_id),
            )
            # The human's resolution promotes the proposed decisions to 'approved';
            # post_adjudication then commits them (with overrides) to ext.claim_lines.
            await conn.execute(
                "UPDATE agent.decisions SET status='approved', approver=$1 WHERE claim_id=$2",
                decided_by, claim_id,
            )
    finally:
        await conn.close()


async def interactive() -> None:
    conn = await asyncpg.connect(_admin_dsn())
    try:
        rows = await _pending(conn)
        if not rows:
            print("No pending claim reviews.")
            return
        print("Pending claim reviews:\n")
        for i, r in enumerate(rows):
            payload = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
            print(f"[{i}] approval {r['id']}  claim {r['claim_id']}")
            print(f"    summary : {payload.get('summary')}")
            lines = await _lines_for(conn, r["claim_id"])
            for ln in lines:
                carc = ln["carc"] if isinstance(ln["carc"], (list, dict)) else json.loads(ln["carc"] or "[]")
                print(f"      line {ln['line_number']}: {ln['decision']:<7} "
                      f"plan_paid={ln['plan_paid_cents']} patient={ln['patient_resp_cents']} "
                      f"carc={carc}")
            print()
    finally:
        await conn.close()

    idx = int(input("Select review index: ").strip())
    chosen = rows[idx]
    action = input("Action [confirm/reject/modify]: ").strip().lower()
    decided_by = input("Your examiner id: ").strip() or "examiner-unknown"
    overrides = None
    if action == "modify":
        raw = input('Line overrides JSON (e.g. {"4": {"decision": "pay", "plan_paid_cents": 20000}}): ').strip()
        overrides = json.loads(raw) if raw else {}
    justification = input("Justification: ").strip()

    await resolve(approval_id=str(chosen["id"]), action=action, decided_by=decided_by,
                  justification=justification, line_overrides=overrides)
    print(f"\nResolved approval {chosen['id']} as {action!r}.")


async def auto_resolve(action: str = "confirm") -> None:
    """Unattended resolver: wait for the next pending review and resolve it.

    For hands-off demos of the live agent — stands in for the human examiner so the
    blocking gate gets unblocked without an interactive console.
    """
    print(f"[auto-examiner] waiting for a pending claim review (will {action})…")
    while True:
        conn = await asyncpg.connect(_admin_dsn())
        try:
            rows = await _pending(conn)
        finally:
            await conn.close()
        if rows:
            chosen = rows[0]
            await resolve(
                approval_id=str(chosen["id"]), action=action, decided_by="ex-204-rkhan",
                justification=("Auto-examiner: reviewed proposed adjudication; reduction is the "
                               "annual-maximum cap, the pend awaits preauth, the denial is the "
                               "non-covered cosmetic line. Confirmed as proposed."),
            )
            print(f"[auto-examiner] resolved {chosen['id']} ({chosen['claim_id']}) as {action!r}")
            return
        await asyncio.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        asyncio.run(auto_resolve())
    else:
        asyncio.run(interactive())
