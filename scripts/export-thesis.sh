#!/usr/bin/env bash
set -euo pipefail

# Build the thesis PDF and drop a copy at documents/<author>-thesis.pdf for
# handoff.
#
#   ./scripts/export-thesis.sh            # requires local XeLaTeX + biber
#   ./scripts/export-thesis.sh --docker   # build inside the TeX Live container

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR/thesis"

ENGINE=local
[ "${1:-}" = "--docker" ] && ENGINE=docker

if [ "$ENGINE" = "local" ] && ! command -v latexmk >/dev/null 2>&1; then
    error "latexmk not found, so there is no local TeX Live to build with.
        Either install TeX Live with XeLaTeX and biber, or build in a
        container instead, which needs no local TeX:

          ./scripts/export-thesis.sh --docker"
fi

if [ "$ENGINE" = "docker" ] && ! docker info >/dev/null 2>&1; then
    error "Docker is not running, start it and try again."
fi

info "Building thesis (ENGINE=${ENGINE})..."
make ENGINE="$ENGINE" || error "Thesis build failed, check thesis/main.log"

AUTHOR_SLUG=$(sed -n 's/.*\\thesisauthorlatin}{\(.*\)}/\1/p' metadata.tex | tr -d ',' | tr ' ' '-')
DEST="$PROJECT_DIR/documents/${AUTHOR_SLUG:-thesis}-thesis.pdf"
cp main.pdf "$DEST"

info "Thesis exported to ${DEST}"
