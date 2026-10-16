# Existing open-source options: what was tested, and what was chosen

**Summary:** no single project covers "fast bulk fetch + family-aware comparison + verification of an existing list". The practical stack is a small self-built bulk layer plus an existing library for per-patent deep dives.

| Project | Status | What was measured | Verdict |
|---|---|---|---|
| `google_patent_scraper` (MIT) | Usable; last pushed 2023 | With a SOCKS proxy wired through the socket layer: ~3.5 s/patent; returns title, application number, inventors, assignees, publication/filing/grant dates, citations. Single-threaded, no proxy argument, and inverted error signalling (a successful fetch reports as an error string) | Good for **single-patent deep dives**; too slow for list-level checks |
| `patent_client` | **Archived** by its author | README states it is archived in favour of a successor | Do not build on it |
| `patent-client-agents` (successor, active) | Active | Async `fetch("<number>")` returned title, filing/publication dates, inventors, assignees, claims, description and a PDF URL in ~3.8 s | Best **deep-dive** option (claims / description / PDF); add concurrency for batches |
| `patentsview` API (official USPTO-derived) | Official | US data only | Use for US-side family completeness and assignee disambiguation |
| EPO OPS clients | Official | Authoritative INPADOC family links; requires an OPS key | Use when family determination must be authoritative |
| Commercial scraping APIs | Paid | Require a paid token | Not used |
| **Google Patents query endpoint** (page interface, not a project) | Live | Batching many numbers into one query returns up to 100 records per request — measured 0.034 s/patent | **Basis of this toolkit's bulk layer** |

## Facts that shaped the design

1. Batching numbers into one query is the fastest public path; the hard cap is 100 records per request (the remainder is silently dropped, so requests must be sharded and validated).
2. Large `num` values on *search* queries truncate (invalid JSON at roughly 20 KB), so search/facet queries stay at `num<=20`.
3. Some numbers (certain HK publications) are not reachable through the bulk query form and need a per-page fallback.
4. Exit IP count is the throughput bottleneck; one worker per exit.
5. Caching pays off immediately: re-running a corrected list becomes a cache hit.
