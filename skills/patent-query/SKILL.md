---
name: patent-query
description: "Use when verifying, cleaning or de-duplicating a patent list (bulk metadata lookup, family links, mismatch reports) against Google Patents."
---

# Patent list verification (bulk lookup · family links · mismatch reports)

Use this when someone hands you a patent list (CSV/XLSX/DOCX table) and wants it **checked, cleaned or completed**: "verify every URL", "which of these are actually granted", "find duplicates", "what's missing from my list".

## 0. Decide the three things first

1. **Level of comparison — publication number or family?** One invention has several publication numbers (A application, B grant, plus CN/US/WO members). Comparing raw numbers manufactures phantom gaps. Always compare after stripping the kind code; use family links for cross-jurisdiction.
2. **Which kinds count as "granted"?** `B`/`I` = invention grant, `U` = utility model, `S` = design — U/S *are* the grant publications. `A` = application publication. International (WO) applications have no grant publication.
3. **Cut-off and definitions.** Any number you report must carry its definition: publication-level or family-level, which kinds included, which filing-date cut-off.

## 1. Bulk retrieval

```bash
python3 -m patent_intel.gp resolve list.csv --col 号码 --lang CHINESE -o meta.csv
```
- Batch many numbers into one query (up to 100 per request; the endpoint silently drops the rest, so the tool shards and validates).
- Measured: 0.03–0.15 s/patent in batch mode vs 2.2–3.5 s/patent fetching each page.
- Cache is persistent: correcting a list and re-running is nearly free.
- A number the bulk form does not index (some HK publications) falls back to a page fetch automatically.

## 2. Verification

```bash
python3 -m patent_intel.verify --ref list.csv --lang CHINESE --out mismatches.csv   # exit code 2 = differences found
```
Four mismatch classes, kept separate on purpose:
- **number not found** — the number does not resolve at all;
- **same-stem only** — the bulk query returned a sibling publication (e.g. you asked for the grant and got the application) and the exact number could not be confirmed: re-check before publishing;
- **title mismatch** — often legitimate (officials amend titles at grant); take the grant publication's title as authoritative;
- **date mismatch** — filing or publication date differs from the list.

Feed it the **original list**, not a de-duplicated file with only a number column — otherwise the title/date columns are silently skipped.

## 3. De-duplication

```bash
python3 -m patent_intel.dedupe --in list.csv --out dedup.csv --report merges.csv [--family]
```
- Pass 1: exact repeats, then same-stem merging (A/B) with grant publications preferred as the representative.
- Pass 2 (`--family`): merges across jurisdictions when family links overlap.
- Hard evidence (a shared family link) merges automatically; **title-only matches are flagged** as "suspected same invention — needs review". Never auto-merge on titles alone.
- After upgrading rows from application to grant publications, **run de-duplication again** — upgraded rows can collide with rows already present.

## 4. Reporting discipline

- State per-batch: checked / hit / fallback / not found, and the mismatch count by class.
- Only call a link "verified" after an actual fetch; if a fetch is blocked by rate limiting, rotate the exit and retry before calling it broken.
- Anything you cannot retrieve is reported as "not retrieved" — never as an inference.

## 5. Via MCP (agent-friendly)

`python3 -m patent_intel.mcp_server` exposes `patent_resolve`, `patent_verify`, `patent_dedupe`, `patent_family`, `patent_search` (recall/facet queries) and `patent_status` (exit + cache health). Configure it in any MCP client; see the repository README.

## 6. Recall searches (when the task is "find all patents of X")

- Facet queries match the applicant/inventor string as indexed: **run the union of all spellings** (local language + English/transliterations) and dedupe the result.
- Quote multi-word keyword phrases; unquoted multi-word queries degrade into term-AND and produce false hits.
- Facet queries must stay at `num<=20` (larger responses truncate); paginate instead.
- Facet-indexed recall is never complete on its own — union it with a keyword or inventor-name leg and state which definitions the final set uses.
