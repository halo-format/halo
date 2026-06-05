"""Seed the mimic_payer database (ext.* payer mirror + reason-code reference).

Builds a dental PPO plan, two members, an in-network provider, the per-code
benefit rules and fee schedule (plus filler codes so a whole-plan rule pull is
genuinely large), accumulators, prior claim history, and two inbound claims:

  * CLM-1001 (Dana Whitfield) — five lines engineered to sweep every outcome:
        pay, pay, reduce (annual-maximum cap), pend (missing preauth), deny
        (non-covered). Total charged is above the auto-finalize ceiling, so the
        claim goes to a human examiner regardless.
  * CLM-2001 (Marco Reyes) — two clean preventive lines, in network, within
        limits, below the ceiling: the auto-finalize path (no human gate).

Run via the admin DSN (never the agent role):
    python -m db.seed.seed_payer
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import random

import asyncpg

PLAN_ID = "PLAN-DENTAL-PPO"
PROVIDER_ID = "PRV-1001"
M1 = "MBR-1001"   # Dana Whitfield — the multi-outcome / human-review case
M2 = "MBR-2001"   # Marco Reyes — the clean auto-finalize case
DEMO_CLAIM = "CLM-1001"
CLEAN_CLAIM = "CLM-2001"
PLAN_YEAR = 2026


def _admin_dsn() -> str:
    host = os.environ.get("ADMIN_DB_HOST", "localhost")
    port = os.environ.get("ADMIN_DB_PORT", "5433")
    user = os.environ.get("ADMIN_DB_USER", "postgres")
    pw = os.environ.get("ADMIN_DB_PASSWORD", "postgres")
    return f"postgresql://{user}:{pw}@{host}:{port}/mimic_payer"


# Reference reason codes the agent selects from (never invents).
REASON_CODES = [
    ("1", "CARC", "Deductible amount"),
    ("2", "CARC", "Coinsurance amount"),
    ("3", "CARC", "Co-payment amount"),
    ("16", "CARC", "Claim/service lacks information or has submission/billing error(s)"),
    ("18", "CARC", "Exact duplicate claim/service"),
    ("26", "CARC", "Expenses incurred prior to coverage"),
    ("45", "CARC", "Charge exceeds fee schedule/maximum allowable amount"),
    ("96", "CARC", "Non-covered charge(s)"),
    ("119", "CARC", "Benefit maximum for this time period or occurrence has been reached"),
    ("197", "CARC", "Precertification/authorization/notification/pre-treatment absent"),
    ("242", "CARC", "Services not provided by network/primary care providers"),
    ("N130", "RARC", "Consult plan benefit documents/guidelines for information about restrictions"),
    ("N362", "RARC", "The number of days or units of service exceeds our acceptable maximum"),
    ("N705", "RARC", "Precertification/authorization required"),
    ("M62", "RARC", "Missing/incomplete/invalid treatment authorization"),
]

# Core per-code benefit rules: (code, category, covered, coverage_pct, freq, waiting, preauth, allowed)
CORE_CODES = [
    ("D0120", "preventive", True, 100, "2/year", 0, False, 6500),
    ("D1110", "preventive", True, 100, "2/year", 0, False, 12000),
    ("D2391", "basic",      True,  80, None,     0, False, 18000),
    ("D2740", "major",      True,  50, "1/5year", 12, False, 100000),  # crown
    ("D4341", "basic",      True,  80, "2/year", 0, True,  28000),     # perio scaling — needs preauth
    ("D9972", "cosmetic",   False,  0, None,     0, False, 25000),     # external bleaching — not covered
]


async def seed() -> None:
    conn = await asyncpg.connect(_admin_dsn())
    try:
        # Idempotent reseed in FK-safe order (agent.* then ext.*).
        for tbl in (
            "agent.decisions", "agent.approvals", "agent.tool_calls", "agent.messages",
            "agent.halo_maps", "agent.halo_nodes", "agent.sessions",
            "ext.claim_lines", "ext.claims", "ext.accumulators", "ext.fee_schedule",
            "ext.benefit_rules", "ext.network", "ext.providers", "ext.members",
            "ext.plans", "ext.reason_codes",
        ):
            await conn.execute(f"DELETE FROM {tbl}")

        # ── reason codes ──────────────────────────────────────────────────────
        await conn.executemany(
            "INSERT INTO ext.reason_codes (code, kind, description) VALUES ($1,$2,$3)", REASON_CODES
        )

        # ── plan ──────────────────────────────────────────────────────────────
        await conn.execute(
            """INSERT INTO ext.plans (id, name, type, annual_max_cents, deductible_cents,
               oop_max_cents, coinsurance) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)""",
            PLAN_ID, "Acme Dental PPO", "dental_ppo", 150000, 5000, 300000,
            json.dumps({"preventive": 100, "basic": 80, "major": 50}),
        )

        # ── members ───────────────────────────────────────────────────────────
        await conn.execute(
            """INSERT INTO ext.members (id, first_name, last_name, dob, plan_id, group_id,
               effective_date, term_date, status) VALUES ($1,$2,$3,$4,$5,$6,$7,NULL,'active')""",
            M1, "Dana", "Whitfield", dt.date(1987, 4, 2), PLAN_ID, "GRP-ACME",
            dt.date(2022, 1, 1),
        )
        await conn.execute(
            """INSERT INTO ext.members (id, first_name, last_name, dob, plan_id, group_id,
               effective_date, term_date, status) VALUES ($1,$2,$3,$4,$5,$6,$7,NULL,'active')""",
            M2, "Marco", "Reyes", dt.date(1979, 11, 20), PLAN_ID, "GRP-ACME",
            dt.date(2018, 3, 1),
        )

        # ── provider + network (in network) ──────────────────────────────────
        await conn.execute(
            "INSERT INTO ext.providers (id, npi, name, specialty) VALUES ($1,$2,$3,$4)",
            PROVIDER_ID, "1639021457", "Bright Smile Dental", "general_dentistry",
        )
        await conn.execute(
            "INSERT INTO ext.network (plan_id, provider_id, in_network) VALUES ($1,$2,true)",
            PLAN_ID, PROVIDER_ID,
        )

        # ── benefit rules + fee schedule: core codes + filler (heavy whole-plan)
        rng = random.Random(42)
        rule_rows, fee_rows = [], []
        for i, (code, cat, cov, pct, freq, wait, pre, allowed) in enumerate(CORE_CODES):
            rule_rows.append((f"BR-{code}", PLAN_ID, code, cat, cov, pct, freq, wait, pre))
            fee_rows.append((PLAN_ID, code, allowed))
        # Filler codes so payer_get_benefit_rules(plan) with no code list is genuinely large.
        for i in range(40):
            code = f"D{2000 + i * 7}"
            cat = rng.choice(["preventive", "basic", "major"])
            pct = {"preventive": 100, "basic": 80, "major": 50}[cat]
            rule_rows.append((f"BR-{code}", PLAN_ID, code, cat, True, pct,
                              rng.choice(["1/year", "2/year", None]), rng.choice([0, 6, 12]),
                              rng.choice([False, False, True])))
            fee_rows.append((PLAN_ID, code, rng.choice([4000, 8000, 15000, 40000, 90000])))
        await conn.executemany(
            """INSERT INTO ext.benefit_rules (id, plan_id, procedure_code, category, covered,
               coverage_pct, frequency_limit, waiting_months, requires_preauth)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            rule_rows,
        )
        await conn.executemany(
            "INSERT INTO ext.fee_schedule (plan_id, procedure_code, allowed_cents) VALUES ($1,$2,$3)",
            fee_rows,
        )

        # ── accumulators ──────────────────────────────────────────────────────
        # Dana: deductible met, $1300 of the $1500 annual max already used → the
        # crown's 50% share will exceed the $200 remaining benefit (annual-max cap).
        await conn.execute(
            """INSERT INTO ext.accumulators (member_id, plan_year, deductible_met_cents,
               annual_max_used_cents, oop_met_cents) VALUES ($1,$2,5000,130000,135000)""",
            M1, PLAN_YEAR,
        )
        # Marco: deductible met, nothing used yet → clean.
        await conn.execute(
            """INSERT INTO ext.accumulators (member_id, plan_year, deductible_met_cents,
               annual_max_used_cents, oop_met_cents) VALUES ($1,$2,5000,0,5000)""",
            M2, PLAN_YEAR,
        )

        # ── prior claim history for Dana (adjudicated; heavy for the Halo demo) ─
        await conn.execute(
            """INSERT INTO ext.claims (id, claim_number, member_id, provider_id, date_received,
               place_of_service, diagnosis_codes, attachments, total_charged_cents, status)
               VALUES ($1,$2,$3,$4,$5,'11',$6::jsonb,$7::jsonb,$8,'adjudicated')""",
            "CLM-0900", "CN-0900", M1, PROVIDER_ID, dt.date(2026, 1, 15),
            json.dumps(["K02.9"]), json.dumps([]), 40000,
        )
        hist_codes = ["D1110", "D0120", "D0274", "D2391", "D2392", "D4910",
                      "D0220", "D0230", "D1206", "D2750", "D7140", "D0140"]
        hist_rows = []
        for i, code in enumerate(hist_codes):
            dos = dt.date(2026, 1, 15) if code in ("D1110", "D0120") else dt.date(2025, rng.randint(2, 11), rng.randint(1, 28))
            hist_rows.append((
                f"CL-0900-{i:02d}", "CLM-0900", i + 1, code, None, None, dos, 1,
                rng.choice([6000, 12000, 18000, 28000]), None, "paid",
                rng.choice([6000, 12000, 18000]), rng.choice([6000, 10000, 14000]),
                rng.choice([0, 2000, 4000]), json.dumps([{"code": "2", "group": "PR"}]), json.dumps([]),
            ))
        await conn.executemany(
            """INSERT INTO ext.claim_lines (id, claim_id, line_number, procedure_code, tooth, surface,
               date_of_service, units, charged_cents, preauth_number, status, allowed_cents,
               plan_paid_cents, patient_resp_cents, carc, rarc)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb,$16::jsonb)""",
            hist_rows,
        )

        # ── DEMO claim CLM-1001 (Dana) — pay/pay/reduce/pend/deny ─────────────
        demo_lines = [
            # (line_no, code, tooth, surface, charged, preauth_number)
            (1, "D1110", None, None, 12000, None),     # prophylaxis → pay
            (2, "D2391", "14", "O", 18000, None),      # filling → pay (20% coinsurance)
            (3, "D2740", "30", None, 130000, None),    # crown → reduce (annual-max cap; CO-45 write-off)
            (4, "D4341", "UR", None, 28000, None),     # perio scaling, preauth required, none → pend
            (5, "D9972", None, None, 25000, None),     # bleaching, non-covered → deny
        ]
        total = sum(c for *_, c, _ in demo_lines)
        await conn.execute(
            """INSERT INTO ext.claims (id, claim_number, member_id, provider_id, date_received,
               place_of_service, diagnosis_codes, attachments, total_charged_cents, status)
               VALUES ($1,$2,$3,$4,$5,'11',$6::jsonb,$7::jsonb,$8,'received')""",
            DEMO_CLAIM, "CN-1001", M1, PROVIDER_ID, dt.date(2026, 6, 1),
            json.dumps(["K02.9", "K05.30"]),
            json.dumps(["ATT-XRAY-01", "ATT-NOTE-01", "ATT-PERIO-01"]), total,
        )
        for ln, code, tooth, surface, charged, preauth in demo_lines:
            await conn.execute(
                """INSERT INTO ext.claim_lines (id, claim_id, line_number, procedure_code, tooth,
                   surface, date_of_service, units, charged_cents, preauth_number, status)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,1,$8,$9,'pending')""",
                f"CL-1001-{ln:02d}", DEMO_CLAIM, ln, code, tooth, surface, dt.date(2026, 5, 20),
                charged, preauth,
            )

        # ── CLEAN claim CLM-2001 (Marco) — auto-finalize ──────────────────────
        clean_lines = [(1, "D0120", 6500), (2, "D1110", 12000)]
        total2 = sum(c for _, _, c in clean_lines)
        await conn.execute(
            """INSERT INTO ext.claims (id, claim_number, member_id, provider_id, date_received,
               place_of_service, diagnosis_codes, attachments, total_charged_cents, status)
               VALUES ($1,$2,$3,$4,$5,'11',$6::jsonb,$7::jsonb,$8,'received')""",
            CLEAN_CLAIM, "CN-2001", M2, PROVIDER_ID, dt.date(2026, 6, 1),
            json.dumps(["Z01.20"]), json.dumps([]), total2,
        )
        for ln, code, charged in clean_lines:
            await conn.execute(
                """INSERT INTO ext.claim_lines (id, claim_id, line_number, procedure_code,
                   date_of_service, units, charged_cents, status)
                   VALUES ($1,$2,$3,$4,$5,1,$6,'pending')""",
                f"CL-2001-{ln:02d}", CLEAN_CLAIM, ln, code, dt.date(2026, 5, 22), charged,
            )

        # ── PROFILING claim CLM-PROF — all-pay, no history, Halo-heavy ─────────
        # A fresh member with no claim history (so no duplicate/frequency pends),
        # all clean PAY lines, below the auto-finalize ceiling → no human gate, so
        # scripts/profile_ab.py can run both arms unattended. PROFILE_ATTACHMENTS
        # controls how bulky get_claim is (the attachment bodies the decision never
        # reads) — the payload Halo keeps out of context. Bump it to scale the test.
        n_att = int(os.environ.get("PROFILE_ATTACHMENTS", "8"))
        await conn.execute(
            """INSERT INTO ext.members (id, first_name, last_name, dob, plan_id, group_id,
               effective_date, term_date, status) VALUES ($1,'Sam','Profile','1990-01-15',$2,
               'GRP-ACME','2021-01-01',NULL,'active')""",
            "MBR-PROF", PLAN_ID,
        )
        await conn.execute(
            """INSERT INTO ext.accumulators (member_id, plan_year, deductible_met_cents,
               annual_max_used_cents, oop_met_cents) VALUES ('MBR-PROF',$1,5000,0,5000)""",
            PLAN_YEAR,
        )
        prof_lines = [(1, "D0120", None, None, 6500), (2, "D1110", None, None, 12000),
                      (3, "D2391", "3", "O", 18000)]   # all covered, in-network, within limits
        total3 = sum(c for *_, c in prof_lines)
        await conn.execute(
            """INSERT INTO ext.claims (id, claim_number, member_id, provider_id, date_received,
               place_of_service, diagnosis_codes, attachments, total_charged_cents, status)
               VALUES ('CLM-PROF','CN-PROF','MBR-PROF',$1,$2,'11',$3::jsonb,$4::jsonb,$5,'received')""",
            PROVIDER_ID, dt.date(2026, 6, 1), json.dumps(["K02.9", "Z01.20"]),
            json.dumps([f"ATT-{i}" for i in range(1, n_att + 1)]), total3,
        )
        for ln, code, tooth, surface, charged in prof_lines:
            await conn.execute(
                """INSERT INTO ext.claim_lines (id, claim_id, line_number, procedure_code, tooth,
                   surface, date_of_service, units, charged_cents, status)
                   VALUES ($1,'CLM-PROF',$2,$3,$4,$5,'2026-04-10',1,$6,'pending')""",
                f"CLP-{ln}", ln, code, tooth, surface, charged,
            )

        print("Seeded mimic_payer:")
        print(f"  demo claim   {DEMO_CLAIM} (Dana Whitfield) — pay/pay/reduce/pend/deny → human review")
        print(f"  clean claim  {CLEAN_CLAIM} (Marco Reyes)   — all pay, below ceiling → auto-finalize")
        print(f"  profile claim CLM-PROF (Sam Profile)      — all pay, {n_att} attachments → A/B harness")
        print(f"  plan {PLAN_ID}: annual max $1500, deductible $50, coins 100/80/50")
        print(f"  {len(rule_rows)} benefit rules, {len(REASON_CODES)} reason codes")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
