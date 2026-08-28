#!/usr/bin/env bash
set -uo pipefail

# End-to-end check of a running system: every API surface answers with real
# data, Metabase is up, and every dashboard card runs as the read-only user
# and returns rows.
#
# Run it in a second terminal while `./scripts/demo.sh` holds the first:
#
#   ./scripts/verify.sh
#
# Exits non-zero on the first failing check, and prints what to look at.
# An empty database fails rather than passes, which is the point: the checks
# assert a non-empty payload, not merely HTTP 200.

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
pass()  { echo -e "${GREEN}  ok  ${NC} $*"; }
fail()  { echo -e "${RED} fail ${NC} $*"; FAILURES=$((FAILURES + 1)); }
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

FAILURES=0
BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

[ -f .env ] || { echo "No .env found, run ./scripts/setup.sh first."; exit 1; }

# Read only the keys needed, rather than sourcing the whole file and exporting
# every secret into this shell and its children.
read_env() { grep -m1 "^$1=" .env | cut -d= -f2- | sed -e 's/^"//' -e "s/^'//" -e 's/"$//' -e "s/'$//"; }

API_PORT="${API_PORT:-8000}"
API="http://localhost:${API_PORT}"
METABASE_PORT="$(read_env METABASE_PORT)"
METABASE_PORT="${METABASE_PORT:-3000}"
DATABASE_NAME="$(read_env POSTGRESQL_DATABASE)"
READ_ONLY_PASSWORD="$(read_env METABASE_READ_ONLY_PASSWORD)"

# JSON emptiness test, so a 200 over an empty database still fails. Treats
# `[]`, `{}`, `null` and a response whose every list-valued field is empty as
# no data.
is_empty() {
    python3 - "$1" <<'PYEOF'
import json
import sys

try:
    with open(sys.argv[1]) as handle:
        payload = json.load(handle)
except (OSError, ValueError):
    sys.exit(0)

if payload in (None, [], {}, ""):
    sys.exit(0)
if isinstance(payload, dict):
    lists = [value for value in payload.values() if isinstance(value, list)]
    if lists and not any(lists):
        sys.exit(0)
sys.exit(1)
PYEOF
}

check_json() {
    local label="$1" path="$2" expect_data="${3:-data}"
    local code
    code=$(curl -s -o "$BODY" -w '%{http_code}' -m 60 \
        -H "Authorization: Bearer ${TOKEN}" "${API}${path}")
    if [ "$code" != "200" ]; then
        fail "${label} (${path}) returned HTTP ${code}"
        head -c 300 "$BODY"; echo
        return
    fi
    if [ "$expect_data" = "data" ] && is_empty "$BODY"; then
        fail "${label} (${path}) returned 200 but no data"
        head -c 300 "$BODY"; echo
        return
    fi
    pass "${label}"
}

echo ""
info "Checking the API on ${API}"

for endpoint in health ready live; do
    code=$(curl -s -o "$BODY" -w '%{http_code}' -m 15 "${API}/api/v1/${endpoint}")
    [ "$code" = "200" ] && pass "/api/v1/${endpoint}" || fail "/api/v1/${endpoint} returned HTTP ${code}"
done

if [ "$FAILURES" -gt 0 ]; then
    echo ""
    fail "The API is not answering. Start it with ./scripts/demo.sh and re-run."
    exit 1
fi

info "Authenticating as the demo superuser"
SUPERUSER_EMAIL="$(read_env FIRST_SUPERUSER_EMAIL)"
SUPERUSER_PASSWORD="$(read_env FIRST_SUPERUSER_PASSWORD)"
TOKEN=$(curl -s -m 30 -X POST "${API}/api/v1/auth/login" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode "username=${SUPERUSER_EMAIL}" \
    --data-urlencode "password=${SUPERUSER_PASSWORD}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)

if [ -z "$TOKEN" ]; then
    fail "Could not log in as ${SUPERUSER_EMAIL}. Check FIRST_SUPERUSER_* in .env."
    exit 1
fi
pass "POST /api/v1/auth/login"
check_json "GET /api/v1/auth/me" "/api/v1/auth/me"

echo ""
info "Checking analytics responses carry data"
check_json "Top products"        "/api/v1/analytics/top-products?limit=5"
check_json "Top customers"       "/api/v1/analytics/top-customers?limit=5"
check_json "Top regions"         "/api/v1/analytics/top-regions?limit=5"
check_json "Sales over time"     "/api/v1/analytics/sales-over-time?granularity=month"
check_json "Sales by weekday"    "/api/v1/analytics/sales-by-weekday"
check_json "Top returns"         "/api/v1/analytics/top-returned-products?limit=5"
check_json "Sales by price band" "/api/v1/analytics/sales-by-price-band"
check_json "Sales by characteristic" "/api/v1/analytics/sales-by-characteristic"

echo ""
info "Checking business metrics, models and derived analyses"
check_json "GMV"                 "/api/v1/business-metrics/gross-merchandise-value"
check_json "Customer summary"    "/api/v1/business-metrics/customer-summary"
check_json "Cohort retention"    "/api/v1/business-metrics/cohort-retention"
check_json "Cohort shape"        "/api/v1/business-metrics/cohort-shape"
check_json "RFM"                 "/api/v1/business-metrics/rfm"
check_json "Association rules"   "/api/v1/market-basket/rules?limit=10"
check_json "Segmentation"        "/api/v1/segmentation"
check_json "Revenue forecast"    "/api/v1/forecasting/revenue?horizon=3"
check_json "Growth accounting"   "/api/v1/growth-accounting"
check_json "Unit economics"      "/api/v1/profitability/unit-economics"
check_json "Profitability projection" "/api/v1/profitability/projection"
check_json "Sensitivity grid"    "/api/v1/profitability/sensitivity"

echo ""
info "Checking Metabase on http://localhost:${METABASE_PORT}"
status=$(curl -s -m 15 "http://localhost:${METABASE_PORT}/api/health" | tr -d ' ')
if [ "$status" = '{"status":"ok"}' ]; then
    pass "Metabase /api/health"
else
    fail "Metabase is not healthy, got '${status}'. Try: docker compose logs metabase --tail 50"
fi

echo ""
info "Running every dashboard card as metabase_readonly"
if [ -z "$READ_ONLY_PASSWORD" ]; then
    warn "METABASE_READ_ONLY_PASSWORD is unset, skipping the card checks."
else
    for query in metabase/queries/*.sql; do
        name="$(basename "$query")"
        # Metabase's optional-clause syntax is not valid SQL, so the
        # `[[AND ... {{start}}]]` blocks are stripped before the card is run
        # here. Metabase itself drops them the same way when no value is
        # supplied for the variable.
        sql=$(python3 -c 'import re,sys; print(re.sub(r"\[\[.*?\]\]", "", open(sys.argv[1]).read(), flags=re.S))' "$query")
        rows=$(printf '%s' "$sql" \
            | docker compose exec -T -e PGPASSWORD="$READ_ONLY_PASSWORD" postgresql \
                psql -U metabase_readonly -d "$DATABASE_NAME" -t -A -f - 2>&1)
        if [ $? -ne 0 ] || printf '%s' "$rows" | grep -qi '^ERROR\|error:'; then
            fail "${name} failed to run"
            printf '%s\n' "$rows" | head -3
        elif [ -z "$(printf '%s' "$rows" | tr -d '[:space:]')" ]; then
            fail "${name} ran but returned no rows"
        else
            pass "${name} ($(printf '%s\n' "$rows" | grep -c . ) rows)"
        fi
    done
fi

echo ""
echo "────────────────────────────────────────────────────────────"
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}Everything checks out.${NC}"
    echo "────────────────────────────────────────────────────────────"
    exit 0
fi
echo -e "${RED}${FAILURES} check(s) failed.${NC}"
echo "────────────────────────────────────────────────────────────"
exit 1
