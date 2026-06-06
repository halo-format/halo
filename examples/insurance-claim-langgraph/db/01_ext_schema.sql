-- ============================================================================
-- ext schema  —  stands in for the PAYER systems
-- Mirrors the payer's claim / member / benefit / accumulator / network /
-- fee-schedule systems and the X12 transaction shapes (837 claim in, 835
-- remittance out, 270/271 eligibility, CARC/RARC reason codes). When you
-- integrate, the MCP tool bodies swap from SQL on these tables to the real
-- feeds and nothing above the tools changes.
--
-- Tables are ordered so foreign keys resolve on a fresh create.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS ext;

-- Plans ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ext.plans (
    id                 text PRIMARY KEY,
    name               text NOT NULL,
    type               text NOT NULL,            -- 'dental_ppo' | 'medical_hmo' | ...
    annual_max_cents   int,
    deductible_cents   int,
    oop_max_cents      int,
    coinsurance        jsonb                     -- { preventive: 100, basic: 80, major: 50 }
);

-- Members --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ext.members (
    id             text PRIMARY KEY,
    first_name     text,
    last_name      text,
    dob            date,
    plan_id        text REFERENCES ext.plans(id),
    group_id       text,
    effective_date date,
    term_date      date,
    status         text                          -- 'active' | 'termed'
);

-- Per-procedure benefit rule for a plan --------------------------------------
CREATE TABLE IF NOT EXISTS ext.benefit_rules (
    id               text PRIMARY KEY,
    plan_id          text REFERENCES ext.plans(id),
    procedure_code   text NOT NULL,              -- CDT / CPT
    category         text,                       -- 'preventive' | 'basic' | 'major'
    covered          boolean,
    coverage_pct     int,
    frequency_limit  text,                       -- e.g. '2/year'
    waiting_months   int,
    requires_preauth boolean DEFAULT false
);

-- Running totals per member per plan year ------------------------------------
CREATE TABLE IF NOT EXISTS ext.accumulators (
    member_id             text REFERENCES ext.members(id),
    plan_year             int,
    deductible_met_cents  int DEFAULT 0,
    annual_max_used_cents int DEFAULT 0,
    oop_met_cents         int DEFAULT 0,
    PRIMARY KEY (member_id, plan_year)
);

-- Providers + network status -------------------------------------------------
CREATE TABLE IF NOT EXISTS ext.providers (
    id        text PRIMARY KEY,
    npi       text,
    name      text,
    specialty text
);

CREATE TABLE IF NOT EXISTS ext.network (
    plan_id     text REFERENCES ext.plans(id),
    provider_id text REFERENCES ext.providers(id),
    in_network  boolean,
    PRIMARY KEY (plan_id, provider_id)
);

-- Allowed amounts (fee schedule) ---------------------------------------------
CREATE TABLE IF NOT EXISTS ext.fee_schedule (
    plan_id        text REFERENCES ext.plans(id),
    procedure_code text,
    allowed_cents  int,
    PRIMARY KEY (plan_id, procedure_code)
);

-- Claims (mirrors an 837 claim header) ---------------------------------------
CREATE TABLE IF NOT EXISTS ext.claims (
    id                  text PRIMARY KEY,
    claim_number        text UNIQUE,
    member_id           text REFERENCES ext.members(id),
    provider_id         text REFERENCES ext.providers(id),
    date_received       date,
    place_of_service    text,
    diagnosis_codes     jsonb,                   -- ICD codes
    attachments         jsonb,                   -- refs to x-rays / notes
    total_charged_cents int,
    status              text DEFAULT 'received'  -- received|adjudicated|pended|denied|paid
);

-- Claim lines (mirrors 837 service lines / 835 SVC) --------------------------
CREATE TABLE IF NOT EXISTS ext.claim_lines (
    id                 text PRIMARY KEY,
    claim_id           text REFERENCES ext.claims(id),
    line_number        int,
    procedure_code     text NOT NULL,            -- CDT / CPT
    tooth              text,
    surface            text,                     -- dental
    date_of_service    date,
    units              int DEFAULT 1,
    charged_cents      int,
    preauth_number     text,                     -- present if a preauth was obtained
    -- filled at adjudication (the 835 / EOB result):
    status             text DEFAULT 'pending',   -- paid|denied|reduced|pended
    allowed_cents      int,
    plan_paid_cents    int,
    patient_resp_cents int,
    carc               jsonb,                    -- [ { code, group } ] group: PR|CO|OA|PI
    rarc               jsonb                     -- remark codes
);

-- CARC / RARC reference (the agent SELECTS from these, never invents) ---------
CREATE TABLE IF NOT EXISTS ext.reason_codes (
    code        text PRIMARY KEY,
    kind        text,                            -- 'CARC' | 'RARC'
    description text
);

CREATE INDEX IF NOT EXISTS ix_claims_member       ON ext.claims(member_id);
CREATE INDEX IF NOT EXISTS ix_claim_lines_claim   ON ext.claim_lines(claim_id);
CREATE INDEX IF NOT EXISTS ix_benefit_rules_plan  ON ext.benefit_rules(plan_id, procedure_code);
CREATE INDEX IF NOT EXISTS ix_fee_schedule_plan   ON ext.fee_schedule(plan_id, procedure_code);
