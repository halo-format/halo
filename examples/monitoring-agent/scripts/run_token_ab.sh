#!/usr/bin/env bash
# A/B token runner for the monitoring agent. The MCP server always runs RAW
# (MONITORING_HALO=0); the only variable is whether OUR consumer-side adapter
# (@halo-format/claude, installHalo) is on. Each run writes runs/<label>.json.
#
#   scripts/run_token_ab.sh baseline   # raw server, no adapter
#   scripts/run_token_ab.sh halo       # raw server + our adapter (PostToolUse hook)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a && . ./.env && set +a

LABEL="${1:-baseline}"
export RUN_LABEL="$LABEL"
case "$LABEL" in
  *halo*) export HALO=1; export MONITORING_FORMAT=json ;;
  *toon*) export HALO=0; export MONITORING_FORMAT=toon ;;
  *)      export HALO=0; export MONITORING_FORMAT=json ;;
esac

PG() { docker exec -e PGPASSWORD=postgres creditline-pg psql -U postgres -d monitoring "$@"; }

echo "==> [$LABEL] reset agent state + agent-declared incidents"
PG -v ON_ERROR_STOP=1 -c "
  TRUNCATE agent.approvals, agent.incident_links, agent.triage_state,
           agent.tool_calls, agent.halo_maps, agent.halo_nodes CASCADE;
  DELETE FROM ext.incident_notes WHERE incident_id <> 'INC-legacy01';
  DELETE FROM ext.incidents WHERE dedup_key ~ '^[0-9]';" >/dev/null

echo "==> [$LABEL] start background auto-approver (approves any gated write)"
( for _ in $(seq 1 240); do
    PG -c "UPDATE agent.approvals SET status='approved', decided_by='oncall-auto', decided_at=now() WHERE status='pending';" >/dev/null 2>&1 || true
    sleep 2
  done ) &
APPROVER=$!
trap 'kill $APPROVER 2>/dev/null || true' EXIT

echo "==> [$LABEL] run agent (HALO adapter=$HALO, server raw)"
npm run agent

kill $APPROVER 2>/dev/null || true
echo "==> [$LABEL] done"
