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

    info "Seeding demo data (safe to re-run)..."
    uv run --env-file .env python app/initial_data.py || warn "Seeding skipped (likely already seeded)"
fi

# Non-secret display values only, read from .env at runtime.
set -a
# shellcheck disable=SC1091
source .env
set +a

API_PORT="${API_PORT:-8000}"

echo ""
echo "────────────────────────────────────────────────────────────"
echo -e "${CYAN}Ensights is ready to showcase.${NC}"
echo ""
echo "  API, Swagger 'try it out':  http://localhost:${API_PORT}/try"
echo "  API, ReDoc reference:       http://localhost:${API_PORT}/documentation"
echo "  Metabase, BI dashboards:    http://localhost:${METABASE_PORT:-3000}"
echo ""
echo "  Demo login: ${FIRST_SUPERUSER_EMAIL:-admin@ensights.com}"
echo "  Password:   see FIRST_SUPERUSER_PASSWORD in .env (not printed here)"
echo "────────────────────────────────────────────────────────────"
echo ""

if command -v open >/dev/null 2>&1; then
    (sleep 2 && open "http://localhost:${API_PORT}/try") &
fi

info "Starting API server, Ctrl+C stops it, containers keep running..."
uv run fastapi dev app/main.py --host 0.0.0.0 --port "${API_PORT}"
