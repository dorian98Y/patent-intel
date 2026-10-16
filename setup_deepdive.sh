#!/usr/bin/env bash
# Optional: per-patent deep dive (claims, description, PDF, inventors)
# Creates a throwaway virtualenv with an async patent data library.
set -euo pipefail
DIR="${1:-.venv-deepdive}"
python3 -m venv "$DIR"
"$DIR/bin/pip" install -q patent-client-agents 'httpx[socks]'
cat <<'TIP'
Usage (route through a SOCKS proxy if needed):
  ALL_PROXY=socks5h://127.0.0.1:9050     $DIR/bin/python -c "import asyncio; from patent_client_agents.google_patents import fetch; print(asyncio.run(fetch('US2668287A')))"

Alternative (citations/events, sequential, ~3.5 s/patent):
  "$DIR/bin/pip" install google_patent_scraper beautifulsoup4 lxml pysocks
TIP
