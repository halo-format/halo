-- ============================================================================
-- LEAST-PRIVILEGE AGENT ROLE
-- The MCP server connects as this role. It can read ext.* (the payer mirror)
-- and read/write agent.* (its own state), but holds no superuser rights and
-- cannot post final adjudication itself — post_adjudication writes ext.claim_lines
-- only after a human has resolved the review gate. Seeding/initialisation use a
-- separate admin DSN that is never handed to the agent.
-- Run while connected to the mimic_payer database.
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'payer_agent') THEN
        CREATE ROLE payer_agent LOGIN PASSWORD 'agent_demo_pw';
    END IF;
END $$;

GRANT USAGE ON SCHEMA ext, agent TO payer_agent;

-- ext.* is the payer mirror: the agent reads it, and post_adjudication writes
-- the 835/EOB result back onto ext.claim_lines / ext.claims.
GRANT SELECT ON ALL TABLES IN SCHEMA ext TO payer_agent;
GRANT UPDATE ON ext.claim_lines, ext.claims TO payer_agent;

-- agent.* is the agent's own state: full read/write.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA agent TO payer_agent;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA agent TO payer_agent;

ALTER DEFAULT PRIVILEGES IN SCHEMA ext   GRANT SELECT ON TABLES TO payer_agent;
ALTER DEFAULT PRIVILEGES IN SCHEMA agent GRANT SELECT, INSERT, UPDATE ON TABLES TO payer_agent;
