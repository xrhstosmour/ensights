#!/usr/bin/env bash
set -euo pipefail

# One-command showcase: brings up infrastructure, applies migrations, seeds
# demo data, then starts the API server and prints every URL a viewer needs.
#
#   ./scripts/demo.sh

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ ! -f .env ]; then
    info "No .env found, running full setup first..."
    ./scripts/setup.sh
else
    command -v docker >/dev/null 2>&1 || error "Docker is required!"
    if ! docker info >/dev/null 2>&1; then
        info "Starting containerization daemon..."
        case "$OSTYPE" in
            darwin*) open -a Docker ;;
            linux*)  sudo systemctl start docker 2>/dev/null || true ;;
        esac
        for i in $(seq 1 30); do
            docker info >/dev/null 2>&1 && break
            [ "$i" -eq 30 ] && error "Docker did not become ready in time"
            sleep 2
        done
    fi

    info "Starting infrastructure services..."
    docker network create internal 2>/dev/null || true
    docker compose up -d

    info "Waiting for database readiness..."
    for i in $(seq 1 30); do
        docker compose exec -T postgresql pg_isready >/dev/null 2>&1 && break
        [ "$i" -eq 30 ] && error "Database did not become ready in time"
        sleep 2
    done

    info "Applying migrations..."
    uv run alembic upgrade head

    info "Creating the tenant, superuser and Metabase role (safe to re-run)..."
    uv run --env-file .env python app/initial_data.py || warn "Initial data skipped (likely already present)"

    info "Seeding demo transactions and mining baskets (safe to re-run)..."
    uv run --env-file .env python scripts/seed_demo.py || warn "Demo seeding skipped"
fi

# Non-secret display values only. Sourcing the whole file would export every
# secret in it into this shell and into everything it starts, so the two values
# actually printed are read out one at a time instead.
read_env() { grep -m1 "^$1=" .env | cut -d= -f2- | sed -e 's/^"//' -e "s/^'//" -e 's/"$//' -e "s/'$//"; }

API_PORT="${API_PORT:-8000}"
METABASE_PORT="$(read_env METABASE_PORT)"
METABASE_PORT="${METABASE_PORT:-3000}"
FIRST_SUPERUSER_EMAIL="$(read_env FIRST_SUPERUSER_EMAIL)"

# Metabase migrates its own application database on first boot, which takes a
# couple of minutes, and its container declares no health check. Printing the
# URL before it answers is how a crash loop stays invisible, so wait for it.
info "Waiting for Metabase to answer on port ${METABASE_PORT}..."
metabase_ready="false"
for i in $(seq 1 60); do
    if curl -fsS -m 3 "http://localhost:${METABASE_PORT}/api/health" >/dev/null 2>&1; then
        metabase_ready="true"
        break
    fi
    sleep 3
done
if [ "$metabase_ready" != "true" ]; then
    warn "Metabase never became healthy. The API below still works."
    warn "Look at why with: docker compose logs metabase --tail 50"
fi

echo ""
echo "────────────────────────────────────────────────────────────"
echo -e "${CYAN}Ensights is ready to showcase.${NC}"
echo ""
echo "  API, Swagger 'try it out':  http://localhost:${API_PORT}/try"
echo "  API, ReDoc reference:       http://localhost:${API_PORT}/documentation"
if [ "$metabase_ready" = "true" ]; then
    echo "  Metabase, BI dashboards:    http://localhost:${METABASE_PORT}"
else
    echo -e "  Metabase, BI dashboards:    ${RED}not responding${NC} on port ${METABASE_PORT}"
fi
echo ""
echo "  Demo login: ${FIRST_SUPERUSER_EMAIL:-admin@ensights.com}"
echo "  Password:   see FIRST_SUPERUSER_PASSWORD in .env (not printed here)"
echo ""
echo "  Check it all works: ./scripts/verify.sh, from another terminal"
echo "────────────────────────────────────────────────────────────"
echo ""

# Opened once the server actually answers, rather than after a fixed wait that
# is unrelated to how long it takes to come up.
open_when_ready() {
    for i in $(seq 1 40); do
        curl -fsS -m 2 "http://localhost:${API_PORT}/api/v1/live" >/dev/null 2>&1 && break
        sleep 1
    done
    local url="http://localhost:${API_PORT}/try"
    if command -v open >/dev/null 2>&1; then
        open "$url"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url"
    elif command -v start >/dev/null 2>&1; then
        start "" "$url"
    fi
}
# A server left running from an earlier run still holds the port. Starting a
# second one dies with a bare "Address already in use" after every step above
# has already succeeded, which reads like the whole showcase broke. Say what
# actually happened instead, and keep the promise that re-running is safe.
if curl -fsS -m 3 "http://localhost:${API_PORT}/api/v1/live" >/dev/null 2>&1; then
    info "An API server already answers on port ${API_PORT}, leaving it running."
    open_when_ready
    exit 0
fi

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"${API_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    error "Port ${API_PORT} is taken by something that is not the API. Free it, or set API_PORT."
fi

open_when_ready &

info "Starting API server, Ctrl+C stops it, containers keep running..."
uv run fastapi dev app/main.py --host 0.0.0.0 --port "${API_PORT}"
