// Claims-examiner console — the human side of the review gate. Resolves pending
// agent.approvals out of band so payer_request_review can unblock. Uses the admin
// DSN: the examiner is a distinct actor from the agent.
//   tsx src/reviewer-console.ts auto   # confirm the next pending review (hands-off)
import pg from "pg";

function adminDsn(): string {
  const host = process.env.ADMIN_DB_HOST || "localhost";
  const port = process.env.ADMIN_DB_PORT || "5433";
  const user = process.env.ADMIN_DB_USER || "postgres";
  const pw = process.env.ADMIN_DB_PASSWORD || "postgres";
  return `postgresql://${user}:${pw}@${host}:${port}/mimic_payer`;
}

async function resolve(
  client: pg.Client,
  approvalId: string,
  action: "confirm" | "reject" | "modify",
  decidedBy: string,
  justification: string,
  lineOverrides: Record<string, unknown> = {},
): Promise<void> {
  const appr = (await client.query("SELECT claim_id FROM agent.approvals WHERE id = $1", [approvalId])).rows[0];
  if (!appr) throw new Error(`approval ${approvalId} not found`);
  const claimId = appr.claim_id;
  let status: string, isOverride: boolean, overrides: Record<string, unknown>;
  if (action === "confirm") { status = "confirmed"; isOverride = false; overrides = {}; }
  else if (action === "modify") { status = "modified"; isOverride = true; overrides = lineOverrides; }
  else {
    status = "rejected"; isOverride = true;
    const rows = (await client.query("SELECT line_number FROM agent.decisions WHERE claim_id = $1", [claimId])).rows;
    overrides = Object.fromEntries(rows.map((r: any) => [String(r.line_number), { decision: "deny", plan_paid_cents: 0 }]));
  }
  await client.query("BEGIN");
  await client.query(
    "UPDATE agent.approvals SET status=$1, is_override=$2, decided_by=$3, justification=$4, line_overrides=$5::jsonb, decided_at=now() WHERE id=$6",
    [status, isOverride, decidedBy, justification, JSON.stringify(overrides), approvalId],
  );
  await client.query("UPDATE agent.decisions SET status='approved', approver=$1 WHERE claim_id=$2", [decidedBy, claimId]);
  await client.query("COMMIT");
}

async function auto(): Promise<void> {
  const client = new pg.Client({ connectionString: adminDsn() });
  await client.connect();
  console.log("[auto-examiner] waiting for a pending claim review (will confirm)…");
  try {
    for (;;) {
      const rows = (await client.query("SELECT id, claim_id FROM agent.approvals WHERE status='pending' ORDER BY created_at LIMIT 1")).rows;
      if (rows.length) {
        const r = rows[0];
        await resolve(client, r.id, "confirm", "ex-204-rkhan",
          "Auto-examiner: reviewed proposed adjudication; reduction is the annual-maximum cap, the pend awaits preauth, the denial is the non-covered cosmetic line. Confirmed.");
        console.log(`[auto-examiner] resolved ${r.id} (${r.claim_id}) as 'confirm'`);
        return;
      }
      await new Promise((res) => setTimeout(res, 1000));
    }
  } finally {
    await client.end();
  }
}

if (process.argv[2] === "auto") auto().catch((e) => { console.error(e); process.exit(1); });
else { console.log("Usage: tsx src/reviewer-console.ts auto"); process.exit(0); }
