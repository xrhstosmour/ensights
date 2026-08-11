#!/usr/bin/env bash
set -euo pipefail

# Build the thesis PDF and drop a copy at dist/<author>.pdf for handoff.
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

info "Building thesis (ENGINE=${ENGINE})..."
make ENGINE="$ENGINE" || error "Thesis build failed, check thesis/main.log"

AUTHOR_SLUG=$(sed -n 's/.*\\thesisauthorlatin}{\(.*\)}/\1/p' metadata.tex | tr -d ',' | tr ' ' '-')
DEST="$PROJECT_DIR/dist/${AUTHOR_SLUG:-thesis}.pdf"
mkdir -p "$PROJECT_DIR/dist"
cp main.pdf "$DEST"

info "Thesis exported to ${DEST}"
