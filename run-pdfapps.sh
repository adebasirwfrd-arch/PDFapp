#!/usr/bin/env bash
# PDFApps patched — font/size/warna otomatis mengikuti teks asli saat edit
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/venv/bin/python"
cd "$DIR"

if [ -d "/opt/homebrew/opt/expat/lib" ]; then
  export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
fi

exec "$PY" pdfapps.py "$@"
