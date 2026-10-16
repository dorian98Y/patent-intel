# Pitfalls: how list-level patent verification goes wrong

Every item below was observed while verifying real patent lists. Format: **symptom → root cause → how to test → how this toolkit avoids it.** No example below contains data from any particular customer list.

## A. Recall (missing patents)

1. **Patents indexed only under one language's applicant string are never found by a query in the other language.**
   *Root cause*: the index stores whichever applicant string the record carries; facet queries match that string. A record indexed in English does not match a Chinese applicant name, and vice versa.
   *Test*: run the same recall set with the local spelling, the English spelling, and their union; compare totals and the first page of results.
   *Avoid*: recall queries must be the **union of all known spellings**, cross-checked with a first-inventor name query.

2. **Utility models (U) and designs (S) get missed when "granted" means "has a B publication".**
   *Root cause*: U/S publications *are* the grant publications and frequently have no A sibling. A checker that only tests `…B`/`…I`, and exits early when unsure, classifies those families as "not granted".
   *Test*: test every kind code in `B/I/U/S` per family; any hit means granted. Never exit early on "uncertain".
   *Avoid*: the toolkit treats `B/I/U/S` as granted when choosing a family representative.

3. **Topic filters and ownership filters are orthogonal axes.**
   *Root cause*: treating "is this patent about topic X" as a proxy for "does this entity own it" (or the reverse) silently drops valid records.
   *Test*: compute both sets and compare the difference rather than only the intersection.
   *Avoid*: decide which axis the deliverable needs, state it, and never merge the two in one filter.

## B. Comparison (false conclusions)

4. **Comparing publication numbers literally turns "same patent, another publication" into "missing patent".**
   *Root cause*: one invention has several publication numbers (A/B within a jurisdiction, plus CN/US/WO members across jurisdictions).
   *Test*: strip the kind code before comparing; follow the family link for cross-jurisdiction matches.
   *Avoid*: all comparisons go through `stem()`; cross-jurisdiction duplication is caught by the optional family pass.

5. **Family links are asymmetric — two publications of one invention can look unrelated.**
   *Root cause*: the published family section is incomplete in both directions.
   *Test*: for pairs that share a title but carry no family link, compare priority/filing order before concluding they are different inventions.
   *Avoid*: only hard evidence (a family link) triggers an automatic merge; title-only matches are reported as "suspected same invention — needs review".

6. **Differing titles between an application publication and its grant publication are not transcription errors.**
   *Root cause*: offices may amend the title at grant.
   *Test*: pull both publications' titles for the same family and measure how often they differ (in a sample of a few hundred grant publications, only a couple differed — but any single case is enough to break a list that mixes sources).
   *Avoid*: take titles from the **grant publication**; the verifier reports title mismatches as their own class, showing both values.

7. **The source list itself can carry wrong numbers.**
   *Root cause*: hand-typed numbers get digits transposed, or a kind code is dropped.
   *Test*: look up the row's application number (or title) and compare the resolved publication number.
   *Avoid*: extract both application and publication numbers when parsing a list; only mark a number "verified" after a page fetch confirms it.

8. **Counts get mixed across definitions.**
   *Symptom*: the same dataset yields several different "totals".
   *Root cause*: publication-level vs family-level; with/without U and S; with/without international applications; different cut-off dates.
   *Avoid*: every reported number carries its definition (level, kinds, cut-off). The workflow summary always prints the de-duplicated count, the source distribution, and the mismatch count.

## C. Retrieval (the fetching itself)

9. **Oversized responses to a search query are truncated.**
   *Root cause*: large facet responses are cut mid-JSON.
   *Test*: a failed `json.loads` on a response that looks complete is the tell; compare response size against expectation.
   *Avoid*: bulk number queries are safe (small payloads); keep facet queries at `num<=20` and paginate.

10. **A rate-limited exit returns zero results with no error.**
    *Root cause*: the upstream serves a block page instead of data, and naive code records "no results".
    *Test*: inspect response length and block-page keywords; re-run any zero-result query once before believing it.
    *Avoid*: `xhr()` returns `None` (not an empty list) on failure; exits rotate and re-authenticate when a block is detected.

11. **Parallelism is not the lever — exit IP count is.**
    *Symptom*: three shards run slower than one, with much higher average latency per page.
    *Root cause*: all shards share the same small pool of exit IPs, worsening rate limiting.
    *Test*: time one exit serially, several exits serially, and several exits in parallel.
    *Avoid*: one worker per exit; scale throughput by adding exits.

12. **"Verified" needs a stated boundary.**
    *Root cause*: fetched / fetched-via-fallback / not-fetched get reported as a single number.
    *Avoid*: report hits, fallbacks and misses separately; publications that are not public yet (e.g. provisional applications) are labelled as such rather than retried indefinitely.

## D. Delivery

13. **The same number can appear twice in a source list** → de-duplicate exact repeats *before* the family pass.
14. **Upgrading rows from an application publication to the grant publication can collide with rows already in the list** → run de-duplication again *after* any A→B upgrade.
15. **Localized documents can silently fall back to the source language** (e.g. an English edition retaining foreign-language assignee names). Verify with a whole-document check (e.g. a CJK character count) instead of spot-checking one column.
