#!/usr/bin/env bash
# A/B token-usage runner: run the agent once without Halo and once with it, on
# the same request and a freshly reset decision state, so the only variable is
# the Halo adapter. Each run writes runs/<label>.json (see agent/main.py).
#
#   scripts/run_token_ab.sh baseline   # HALO off
#   scripts/run_token_ab.sh halo       # HALO on
#
# Requires: docker postgres up + seeded, ANTHROPIC_API_KEY in .env, and (for the
# halo run) halo-format + halo-format-claude installed in $HALO_PY's venv.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a && . ./.env && set +a

PY="${HALO_PY:-/Users/aj/halo/py/.venv/bin/python}"
LABEL="${1:-baseline}"
RID="${2:-11111111-1111-1111-1111-111111111111}"

export RUN_LABEL="$LABEL"
case "$LABEL" in *halo*) export HALO=1 ;; *) export HALO=0 ;; esac

echo "==> [$LABEL] reset decision/approval state for $RID"
docker exec -e PGPASSWORD="${ADMIN_DB_PASSWORD:-postgres}" creditline-pg \
  psql -U postgres -d mimic_creditline -v ON_ERROR_STOP=1 -c \
  "DELETE FROM approvals;
   DELETE FROM decisions WHERE request_id='$RID';
   UPDATE credit_line_requests SET status='pending' WHERE request_id='$RID';" >/dev/null

echo "==> [$LABEL] start auto-officer (resolves the HITL gate as modify 12000)"
"$PY" -m scripts.officer_console auto &
OFFICER=$!

echo "==> [$LABEL] run agent (HALO=$HALO)"
"$PY" -m agent.main "$RID"

wait "$OFFICER" 2>/dev/null || true
echo "==> [$LABEL] done"
