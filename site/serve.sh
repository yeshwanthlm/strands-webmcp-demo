#!/usr/bin/env bash
# Serve the canteen site on localhost only.
# WebMCP's flag works on 127.0.0.1, so no deployment is needed to demo.
set -euo pipefail
PORT="${1:-8787}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "plain site   http://127.0.0.1:${PORT}/"
echo "webmcp site  http://127.0.0.1:${PORT}/?webmcp=1"
exec python3 -m http.server "${PORT}" --bind 127.0.0.1 --directory "${DIR}"
