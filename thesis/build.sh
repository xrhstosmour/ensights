#!/bin/sh
# Thin wrapper around latexmk. Inside the TeX Live container the staged Arial
# and Courier New faces are mounted into the system font path, which
# fontconfig only sees after its cache is rebuilt. On a local build fc-cache
# is absent and the step is skipped.
set -e
command -v fc-cache >/dev/null 2>&1 && fc-cache -f >/dev/null 2>&1 || true
exec latexmk "$@"
