// Seed the mimic_payer database (ext.* payer mirror + reason-code reference).
// Port of db/seed/seed_payer.py — same plan, members, claims, and outcomes.
//   CLM-1001 (Dana Whitfield): pay/pay/reduce/pend/deny -> human review
//   CLM-2001 (Marco Reyes):    all pay, below ceiling   -> auto-finalize
//   CLM-PROF (Sam Profile):    all pay, no history, PROFILE_ATTACHMENTS-tunable -> A/B fixture
// Run via the admin DSN (never the agent role).
import pg from "pg";

const PLAN = "PLAN-DENTAL-PPO";
const PROV = "PRV-1001";
const M1 = "MBR-1001", M2 = "MBR-2001", MP = "MBR-PROF";
const YEAR = 2026;

function adminDsn(): string {
  const host = process.env.ADMIN_DB_HOST || "localhost";
  const port = process.env.ADMIN_DB_PORT || "5433";
  const user = process.env.ADMIN_DB_USER || "postgres";
  const pw = process.env.ADMIN_DB_PASSWORD || "postgres";
  return `postgresql://${user}:${pw}@${host}:${port}/mimic_payer`;
}

const REASON_CODES: [string, string, string][] = [
  ["1", "CARC", "Deductible amount"],
  ["2", "CARC", "Coinsurance amount"],
  ["3", "CARC", "Co-payment amount"],
  ["16", "CARC", "Claim/service lacks information or has submission/billing error(s)"],
  ["18", "CARC", "Exact duplicate claim/service"],
  ["26", "CARC", "Expenses incurred prior to coverage"],
  ["45", "CARC", "Charge exceeds fee schedule/maximum allowable amount"],
  ["96", "CARC", "Non-covered charge(s)"],
  ["119", "CARC", "Benefit maximum for this time period or occurrence has been reached"],
  ["197", "CARC", "Precertification/authorization/notification/pre-treatment absent"],
  ["242", "CARC", "Services not provided by network/primary care providers"],
  ["N130", "RARC", "Consult plan benefit documents/guidelines for information about restrictions"],
  ["N362", "RARC", "The number of days or units of service exceeds our acceptable maximum"],
  ["N705", "RARC", "Precertification/authorization required"],
  ["M62", "RARC", "Missing/incomplete/invalid treatment authorization"],
];

// code, category, covered, coverage_pct, freq, waiting, preauth, allowed
const CORE: [string, string, boolean, number, string | null, number, boolean, number][] = [
  ["D0120", "preventive", true, 100, "2/year", 0, false, 6500],
  ["D1110", "preventive", true, 100, "2/year", 0, false, 12000],
  ["D2391", "basic", true, 80, null, 0, false, 18000],
  ["D2740", "major", true, 50, "1/5year", 12, false, 100000],
  ["D4341", "basic", true, 80, "2/year", 0, true, 28000],
  ["D9972", "cosmetic", false, 0, null, 0, false, 25000],
];

async function main(): Promise<void> {
  const nAtt = Number(process.env.PROFILE_ATTACHMENTS || "8");
  const c = new pg.Client({ connectionString: adminDsn() });
  await c.connect();
  const x = (sql: string, p: unknown[] = []) => c.query(sql, p);

  for (const tbl of [
    "agent.decisions", "agent.approvals", "agent.tool_calls", "agent.messages", "agent.halo_maps",
    "agent.halo_nodes", "agent.sessions", "ext.claim_lines", "ext.claims", "ext.accumulators",
    "ext.fee_schedule", "ext.benefit_rules", "ext.network", "ext.providers", "ext.members",
    "ext.plans", "ext.reason_codes",
  ]) await x(`DELETE FROM ${tbl}`);

  for (const [code, kind, desc] of REASON_CODES)
    await x("INSERT INTO ext.reason_codes (code, kind, description) VALUES ($1,$2,$3)", [code, kind, desc]);

  await x(
    "INSERT INTO ext.plans (id, name, type, annual_max_cents, deductible_cents, oop_max_cents, coinsurance) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)",
    [PLAN, "Acme Dental PPO", "dental_ppo", 150000, 5000, 300000, JSON.stringify({ preventive: 100, basic: 80, major: 50 })],
  );

  const member = (id: string, fn: string, ln: string, dob: string, eff: string) =>
    x("INSERT INTO ext.members (id, first_name, last_name, dob, plan_id, group_id, effective_date, term_date, status) VALUES ($1,$2,$3,$4,$5,'GRP-ACME',$6,NULL,'active')",
      [id, fn, ln, dob, PLAN, eff]);
  await member(M1, "Dana", "Whitfield", "1987-04-02", "2022-01-01");
  await member(M2, "Marco", "Reyes", "1979-11-20", "2018-03-01");
  await member(MP, "Sam", "Profile", "1990-01-15", "2021-01-01");

  await x("INSERT INTO ext.providers (id, npi, name, specialty) VALUES ($1,'1639021457','Bright Smile Dental','general_dentistry')", [PROV]);
  await x("INSERT INTO ext.network (plan_id, provider_id, in_network) VALUES ($1,$2,true)", [PLAN, PROV]);

  // benefit rules + fee schedule: core + filler (heavy whole-plan pull)
  let nRules = 0;
  for (const [code, cat, cov, pct, freq, wait, pre, allowed] of CORE) {
    await x("INSERT INTO ext.benefit_rules (id, plan_id, procedure_code, category, covered, coverage_pct, frequency_limit, waiting_months, requires_preauth) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
      [`BR-${code}`, PLAN, code, cat, cov, pct, freq, wait, pre]);
    await x("INSERT INTO ext.fee_schedule (plan_id, procedure_code, allowed_cents) VALUES ($1,$2,$3)", [PLAN, code, allowed]);
    nRules++;
  }
  const cats = ["preventive", "basic", "major"]; const pctByCat: Record<string, number> = { preventive: 100, basic: 80, major: 50 };
  for (let i = 0; i < 40; i++) {
    const code = `D${2000 + i * 7}`; const cat = cats[i % 3]; const freq = ["1/year", "2/year", null][i % 3];
    await x("INSERT INTO ext.benefit_rules (id, plan_id, procedure_code, category, covered, coverage_pct, frequency_limit, waiting_months, requires_preauth) VALUES ($1,$2,$3,$4,true,$5,$6,$7,$8)",
      [`BR-${code}`, PLAN, code, cat, pctByCat[cat], freq, [0, 6, 12][i % 3], i % 5 === 0]);
    await x("INSERT INTO ext.fee_schedule (plan_id, procedure_code, allowed_cents) VALUES ($1,$2,$3)", [PLAN, code, [4000, 8000, 15000, 40000, 90000][i % 5]]);
    nRules++;
  }

  // accumulators: Dana near-exhausted (forces the crown's annual-max cap); Marco/Sam fresh.
  await x("INSERT INTO ext.accumulators (member_id, plan_year, deductible_met_cents, annual_max_used_cents, oop_met_cents) VALUES ($1,$2,5000,130000,135000)", [M1, YEAR]);
  await x("INSERT INTO ext.accumulators (member_id, plan_year, deductible_met_cents, annual_max_used_cents, oop_met_cents) VALUES ($1,$2,5000,0,5000)", [M2, YEAR]);
  await x("INSERT INTO ext.accumulators (member_id, plan_year, deductible_met_cents, annual_max_used_cents, oop_met_cents) VALUES ($1,$2,5000,0,5000)", [MP, YEAR]);

  // prior history for Dana (heavy for the Halo demo)
  await x("INSERT INTO ext.claims (id, claim_number, member_id, provider_id, date_received, place_of_service, diagnosis_codes, attachments, total_charged_cents, status) VALUES ('CLM-0900','CN-0900',$1,$2,'2026-01-15','11',$3::jsonb,'[]'::jsonb,40000,'adjudicated')",
    [M1, PROV, JSON.stringify(["K02.9"])]);
  const hist = ["D1110", "D0120", "D0274", "D2391", "D2392", "D4910", "D0220", "D0230", "D1206", "D2750", "D7140", "D0140"];
  for (let i = 0; i < hist.length; i++) {
    const code = hist[i];
    const dos = code === "D1110" || code === "D0120" ? "2026-01-15" : `2025-${String(2 + (i % 10)).padStart(2, "0")}-15`;
    const ch = [6000, 12000, 18000, 28000][i % 4];
    await x("INSERT INTO ext.claim_lines (id, claim_id, line_number, procedure_code, date_of_service, units, charged_cents, status, allowed_cents, plan_paid_cents, patient_resp_cents, carc, rarc) VALUES ($1,'CLM-0900',$2,$3,$4,1,$5,'paid',$6,$7,$8,$9::jsonb,'[]'::jsonb)",
      [`CL-0900-${String(i).padStart(2, "0")}`, i + 1, code, dos, ch, [6000, 12000, 18000][i % 3], [6000, 10000, 14000][i % 3], [0, 2000, 4000][i % 3], JSON.stringify([{ code: "2", group: "PR" }])]);
  }

  // DEMO claim CLM-1001 (Dana) — pay/pay/reduce/pend/deny
  const demo: [number, string, string | null, string | null, number][] = [
    [1, "D1110", null, null, 12000], [2, "D2391", "14", "O", 18000], [3, "D2740", "30", null, 130000],
    [4, "D4341", "UR", null, 28000], [5, "D9972", null, null, 25000],
  ];
  await x("INSERT INTO ext.claims (id, claim_number, member_id, provider_id, date_received, place_of_service, diagnosis_codes, attachments, total_charged_cents, status) VALUES ('CLM-1001','CN-1001',$1,$2,'2026-06-01','11',$3::jsonb,$4::jsonb,$5,'received')",
    [M1, PROV, JSON.stringify(["K02.9", "K05.30"]), JSON.stringify(["ATT-XRAY-01", "ATT-NOTE-01", "ATT-PERIO-01"]), demo.reduce((s, l) => s + l[4], 0)]);
  for (const [ln, code, tooth, surface, ch] of demo)
    await x("INSERT INTO ext.claim_lines (id, claim_id, line_number, procedure_code, tooth, surface, date_of_service, units, charged_cents, status) VALUES ($1,'CLM-1001',$2,$3,$4,$5,'2026-05-20',1,$6,'pending')",
      [`CL-1001-${String(ln).padStart(2, "0")}`, ln, code, tooth, surface, ch]);

  // CLEAN claim CLM-2001 (Marco) — auto-finalize
  const clean: [number, string, number][] = [[1, "D0120", 6500], [2, "D1110", 12000]];
  await x("INSERT INTO ext.claims (id, claim_number, member_id, provider_id, date_received, place_of_service, diagnosis_codes, attachments, total_charged_cents, status) VALUES ('CLM-2001','CN-2001',$1,$2,'2026-06-01','11',$3::jsonb,'[]'::jsonb,$4,'received')",
    [M2, PROV, JSON.stringify(["Z01.20"]), clean.reduce((s, l) => s + l[2], 0)]);
  for (const [ln, code, ch] of clean)
    await x("INSERT INTO ext.claim_lines (id, claim_id, line_number, procedure_code, date_of_service, units, charged_cents, status) VALUES ($1,'CLM-2001',$2,$3,'2026-05-22',1,$4,'pending')",
      [`CL-2001-${String(ln).padStart(2, "0")}`, ln, code, ch]);

  // PROFILING claim CLM-PROF (Sam) — all pay, no history, attachment-tunable
  const prof: [number, string, string | null, string | null, number][] = [
    [1, "D0120", null, null, 6500], [2, "D1110", null, null, 12000], [3, "D2391", "3", "O", 18000],
  ];
  const atts = Array.from({ length: nAtt }, (_, i) => `ATT-${i + 1}`);
  await x("INSERT INTO ext.claims (id, claim_number, member_id, provider_id, date_received, place_of_service, diagnosis_codes, attachments, total_charged_cents, status) VALUES ('CLM-PROF','CN-PROF',$1,$2,'2026-06-01','11',$3::jsonb,$4::jsonb,$5,'received')",
    [MP, PROV, JSON.stringify(["K02.9", "Z01.20"]), JSON.stringify(atts), prof.reduce((s, l) => s + l[4], 0)]);
  for (const [ln, code, tooth, surface, ch] of prof)
    await x("INSERT INTO ext.claim_lines (id, claim_id, line_number, procedure_code, tooth, surface, date_of_service, units, charged_cents, status) VALUES ($1,'CLM-PROF',$2,$3,$4,$5,'2026-04-10',1,$6,'pending')",
      [`CLP-${ln}`, ln, code, tooth, surface, ch]);

  console.log("Seeded mimic_payer:");
  console.log("  demo claim   CLM-1001 (Dana Whitfield) — pay/pay/reduce/pend/deny → human review");
  console.log("  clean claim  CLM-2001 (Marco Reyes)    — all pay, below ceiling → auto-finalize");
  console.log(`  profile claim CLM-PROF (Sam Profile)    — all pay, ${nAtt} attachments → A/B harness`);
  console.log(`  ${nRules} benefit rules, ${REASON_CODES.length} reason codes`);
  await c.end();
}

main().catch((e) => { console.error(e); process.exit(1); });
