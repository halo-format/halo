#!/usr/bin/env bash
# Initialise the mimic_payer database: create it, apply the ext + agent schemas,
# create the least-privilege agent role, then seed. Uses the ADMIN_* connection;
# the agent role is never used here.
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${ADMIN_DB_HOST:-localhost}"
PORT="${ADMIN_DB_PORT:-5433}"
USER="${ADMIN_DB_USER:-postgres}"
export PGPASSWORD="${ADMIN_DB_PASSWORD:-postgres}"

psql_admin() { psql -h "$HOST" -p "$PORT" -U "$USER" "$@"; }

echo "==> creating database mimic_payer (if absent)"
psql_admin -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='mimic_payer'" \
  | grep -q 1 || psql_admin -d postgres -c "CREATE DATABASE mimic_payer"

echo "==> applying ext schema (payer mirror / X12 shapes)"
psql_admin -d mimic_payer -v ON_ERROR_STOP=1 -f db/01_ext_schema.sql

echo "==> applying agent schema (state + audit + evidence)"
psql_admin -d mimic_payer -v ON_ERROR_STOP=1 -f db/02_agent_schema.sql

echo "==> creating role + grants"
psql_admin -d mimic_payer -v ON_ERROR_STOP=1 -f db/03_roles_and_grants.sql

echo "==> seeding data"
python -m db.seed.seed_payer

echo "==> done."
