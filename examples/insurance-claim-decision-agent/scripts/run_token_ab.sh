#!/usr/bin/env bash
# A/B token-usage runner: run the agent once without Halo and once with it, on the
# same claim and a freshly reset decision state, so the only variable is the Halo
# adapter. Each run writes runs/<label>.json (see agent/main.py).
#
#   scripts/run_token_ab.sh baseline   # HALO off
#   scripts/run_token_ab.sh halo       # HALO on
#
# Requires: a seeded mimic_payer database, ANTHROPIC_API_KEY in .env, and (for the
# halo run) halo-format + halo-format-claude installed in $HALO_PY's venv.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a && . ./.env && set +a

# Python with halo-format + halo-format-claude installed. Defaults to this example's
# own .venv, then the monorepo venv, then plain python3. Override with HALO_PY.
PY="${HALO_PY:-$([ -x .venv/bin/python ] && echo .venv/bin/python \
  || ([ -x ../../py/.venv/bin/python ] && echo ../../py/.venv/bin/python || echo python3))}"
LABEL="${1:-baseline}"
CID="${2:-CLM-1001}"

export RUN_LABEL="$LABEL"
case "$LABEL" in *halo*) export HALO=1 ;; *) export HALO=0 ;; esac

echo "==> [$LABEL] reset decision/approval state for $CID"
PGPASSWORD="${ADMIN_DB_PASSWORD:-postgres}" psql \
  -h "${ADMIN_DB_HOST:-localhost}" -p "${ADMIN_DB_PORT:-5433}" -U "${ADMIN_DB_USER:-postgres}" \
  -d mimic_payer -v ON_ERROR_STOP=1 -c \
  "DELETE FROM agent.approvals WHERE claim_id='$CID';
   DELETE FROM agent.decisions WHERE claim_id='$CID';
   UPDATE ext.claims SET status='received' WHERE id='$CID';
   UPDATE ext.claim_lines SET status='pending', allowed_cents=NULL, plan_paid_cents=NULL,
     patient_resp_cents=NULL, carc=NULL, rarc=NULL WHERE claim_id='$CID';" >/dev/null

echo "==> [$LABEL] start auto-examiner (confirms the review gate)"
"$PY" -m scripts.reviewer_console auto &
EXAMINER=$!

echo "==> [$LABEL] run agent (HALO=$HALO)"
"$PY" -m agent.main "$CID"

wait "$EXAMINER" 2>/dev/null || true
echo "==> [$LABEL] done"
