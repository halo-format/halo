-- ============================================================================
-- agent schema  —  the agent's OWN state, including the audit + evidence record
-- This never changes when you integrate: ext.* was built to the payer's and X12
-- shapes, so swapping the tool bodies to real feeds leaves everything here, the
-- skills, the decision gate, and Halo untouched.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS agent;

CREATE TABLE IF NOT EXISTS agent.sessions (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id   text,                              -- the claim being adjudicated
    channel    text,                              -- 'queue' | 'batch'
    started_at timestamptz DEFAULT now(),
    ended_at   timestamptz,
    status     text DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS agent.messages (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid REFERENCES agent.sessions(id),
    role       text,
    content    jsonb,                             -- envelopes, never raw claims
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent.tool_calls (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    uuid REFERENCES agent.sessions(id),
    tool          text,
    args          jsonb,
    envelope_root text,
    latency_ms    int,
    ok            boolean,
    error         text,
    created_at    timestamptz DEFAULT now()
);

-- Verifiable store: handles are content + integrity --------------------------
CREATE TABLE IF NOT EXISTS agent.halo_nodes (
    handle     text PRIMARY KEY,
    bytes      bytea NOT NULL,
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent.halo_maps (
    session_id uuid REFERENCES agent.sessions(id),
    map_id     text,
    root       text,
    source     jsonb,
    updated_at timestamptz DEFAULT now(),
    PRIMARY KEY (session_id, map_id)
);

-- HITL for denials, reductions, pends, large amounts -------------------------
CREATE TABLE IF NOT EXISTS agent.approvals (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid REFERENCES agent.sessions(id),
    claim_id        text,
    action          text,                         -- 'claim_review'
    payload         jsonb,                        -- proposed per-line decisions + summary
    idempotency_key text UNIQUE,
    status          text DEFAULT 'pending',       -- pending|confirmed|modified|rejected
    is_override     boolean NOT NULL DEFAULT false,
    decided_by      text,
    line_overrides  jsonb,                        -- optional per-line reviewer changes
    justification   text,
    created_at      timestamptz DEFAULT now(),
    decided_at      timestamptz
);

-- The audit + explainability record, one row per claim line ------------------
CREATE TABLE IF NOT EXISTS agent.decisions (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id         uuid REFERENCES agent.sessions(id),
    claim_id           text NOT NULL,
    line_number        int NOT NULL,
    decision           text NOT NULL,             -- 'pay'|'deny'|'reduce'|'pend'
    allowed_cents      int,
    plan_paid_cents    int,
    patient_resp_cents int,
    deductible_cents   int,
    coinsurance_cents  int,
    copay_cents        int,
    carc               jsonb,
    rarc               jsonb,
    rule_basis         jsonb,                     -- which benefit rules / checks fired
    evidence           jsonb,                     -- Halo handles of the exact data this rested on
    computed_by        text DEFAULT 'engine',     -- 'engine' = deterministic, never the model
    status             text DEFAULT 'proposed',   -- 'proposed'|'approved'|'final'
    approver           text,
    rationale          text,
    created_at         timestamptz DEFAULT now(),
    decided_at         timestamptz,
    UNIQUE (claim_id, line_number)                -- idempotency: one decision per line
);

CREATE INDEX IF NOT EXISTS ix_decisions_claim ON agent.decisions(claim_id);
CREATE INDEX IF NOT EXISTS ix_approvals_claim ON agent.approvals(claim_id);
