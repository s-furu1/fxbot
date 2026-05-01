#!/usr/bin/env bash
#
# fxbot environment switcher.
# Usage:
#   ./switch-env.sh practice
#   ./switch-env.sh live
#
# Switches between practice and live environments by validating
# .env.{mode} BEFORE touching the symlink. This ensures that a
# validation failure leaves the currently running environment intact.
#
# Order of operations (do not change):
#   1. Validate mode argument
#   2. Verify .env.{mode} exists
#   3. Extract values from .env.{mode} for verification
#   4. Verify EXPECTED_* / OANDA_* consistency
#   5. Verify zero open positions on the target account
#   6. Create data/{mode}/ directory
#   7. For 'live' only: require confirmation phrase
#   8. Re-link .env -> .env.{mode}
#   9. docker compose up -d with FXBOT_MODE={mode}

set -euo pipefail

log()  { echo "[switch-env] $*" >&2; }
fail() { echo "[switch-env] ERROR: $*" >&2; exit 1; }

# 1. Validate mode argument
MODE="${1:-}"
if [[ -z "${MODE}" ]]; then
    fail "usage: $0 practice|live"
fi
case "${MODE}" in
    practice|live) ;;
    *) fail "invalid mode: ${MODE} (must be 'practice' or 'live')" ;;
esac

cd "$(dirname "$0")/.." || fail "failed to cd to project root"
PROJECT_ROOT="$(pwd)"
log "project root: ${PROJECT_ROOT}"

ENV_FILE=".env.${MODE}"

# 2. Verify .env.{mode} exists
if [[ ! -f "${ENV_FILE}" ]]; then
    fail "${ENV_FILE} not found"
fi


# .env.{mode} format is intentionally restricted.
# Allowed:  KEY=value
# Forbidden: export KEY=value, KEY = value, KEY="value", inline comments.
if grep -nE '^(export[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*[[:space:]]+=|[A-Za-z_][A-Za-z0-9_]*=.*#|[A-Za-z_][A-Za-z0-9_]*=")' "${ENV_FILE}" >&2; then
    fail "${ENV_FILE}: invalid .env format. use plain KEY=value only."
fi

# 3. Extract values from .env.{mode} without exporting them globally
extract_var() {
    local name="$1"
    local value
    value=$(grep -E "^${name}=" "${ENV_FILE}" | head -n1 | cut -d= -f2- || true)
    if [[ -z "${value}" ]]; then
        fail "${ENV_FILE}: ${name} not set"
    fi
    echo "${value}"
}

EXPECTED_MODE=$(extract_var FXBOT_EXPECTED_MODE)
ACTUAL_MODE=$(extract_var FXBOT_MODE)
ACTUAL_ENV=$(extract_var OANDA_ENV)
EXPECTED_ACCOUNT_ID=$(extract_var FXBOT_EXPECTED_ACCOUNT_ID)
ACTUAL_ACCOUNT_ID=$(extract_var OANDA_ACCOUNT_ID)
DB_ENV=$(extract_var FXBOT_DB_ENV)
API_KEY=$(extract_var OANDA_API_KEY)

# 4. Verify EXPECTED_* / OANDA_* consistency
if [[ "${EXPECTED_MODE}" != "${MODE}" ]]; then
    fail "${ENV_FILE}: FXBOT_EXPECTED_MODE='${EXPECTED_MODE}' but switching to '${MODE}'"
fi
if [[ "${ACTUAL_MODE}" != "${MODE}" ]]; then
    fail "${ENV_FILE}: FXBOT_MODE='${ACTUAL_MODE}' but switching to '${MODE}'"
fi
if [[ "${ACTUAL_ENV}" != "${MODE}" ]]; then
    fail "${ENV_FILE}: OANDA_ENV='${ACTUAL_ENV}' but switching to '${MODE}'"
fi
if [[ "${EXPECTED_ACCOUNT_ID}" != "${ACTUAL_ACCOUNT_ID}" ]]; then
    fail "${ENV_FILE}: FXBOT_EXPECTED_ACCOUNT_ID and OANDA_ACCOUNT_ID mismatch"
fi
if [[ "${DB_ENV}" != "${MODE}" ]]; then
    fail "${ENV_FILE}: FXBOT_DB_ENV='${DB_ENV}' but switching to '${MODE}'"
fi
log "env file consistency OK"

# 5. Verify zero open positions on the target account
verify_zero_positions() {
    local oanda_host
    if [[ "${MODE}" == "live" ]]; then
        oanda_host="api-fxtrade.oanda.com"
    else
        oanda_host="api-fxpractice.oanda.com"
    fi

    local response
    response=$(curl -sS \
        -H "Authorization: Bearer ${API_KEY}" \
        -H "Content-Type: application/json" \
        "https://${oanda_host}/v3/accounts/${ACTUAL_ACCOUNT_ID}/openPositions" \
        || fail "failed to query OANDA API")

    local count
    count=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    positions = data.get('positions', [])
    active = [p for p in positions
              if int(p.get('long', {}).get('units', '0')) != 0
              or int(p.get('short', {}).get('units', '0')) != 0]
    print(len(active))
except Exception as e:
    print(f'PARSE_ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" <<< "${response}")

    if [[ "${count}" != "0" ]]; then
        fail "target account (${MODE}) has ${count} open position(s). close them before switching."
    fi
    log "target account has 0 open positions"
}
verify_zero_positions

# 6. Create data/{mode}/ directory
mkdir -p "data/${MODE}"
chmod 750 "data/${MODE}" 2>/dev/null || true
log "data/${MODE}/ ready"

# 7. For 'live' only: require confirmation phrase
if [[ "${MODE}" == "live" ]]; then
    current_target="(none)"
    if [[ -L .env ]]; then
        current_target=$(readlink .env)
    fi
    masked_id="***-${ACTUAL_ACCOUNT_ID: -4}"

    cat <<EOF >&2

===========================================
  Switching environment to LIVE.

  current env  : ${current_target}
  target env   : .env.live
  db dir       : ./data/live
  account id   : ${masked_id}

  Type 'I CONFIRM FXBOT LIVE' to continue:
===========================================
EOF
    read -r CONFIRMATION
    if [[ "${CONFIRMATION}" != "I CONFIRM FXBOT LIVE" ]]; then
        fail "confirmation phrase mismatch. aborting."
    fi
    log "confirmation accepted"
fi

# 8. Re-link .env -> .env.{mode}
ln -sfn "${ENV_FILE}" .env
log ".env -> ${ENV_FILE}"

# 9. docker compose up -d
log "starting docker compose with FXBOT_MODE=${MODE}..."
FXBOT_MODE="${MODE}" docker compose up -d

log "switched to ${MODE}. tail logs with: docker compose logs -f fxbot"
