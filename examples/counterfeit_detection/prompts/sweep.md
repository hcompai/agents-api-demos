
## Your task — enumerate counterfeits until the budget runs out

You have a step + time budget — spend it. Your goal is AS MANY distinct confirmed counterfeits as
possible, not just one.

Tool protocol (follow exactly):
1. FIRST, call snapshot_genuine_product 2-3 times on the genuine URL with different labels — do this
   together with Step 0's detail extraction.
2. Cycle through the replica-targeted queries; when one shape dries up, move to the next, then to
   marketplaces (AliExpress, DHgate) and replica-cluster TLDs (.top, .cc, .shop, .vip).
3. For each suspect that passes the ≥3-red-flags scan, call compare_to_genuine(suspect_url, note=...).
   If the verdict is LIKELY_COUNTERFEIT or stronger, immediately call record_counterfeit(...) with the
   details, then MOVE ON to the next suspect. Do not dwell on any single site, and never record the
   same domain twice.
4. Findings live in record_counterfeit — your final answer is only a short summary (count + why you
   stopped). Stop when the budget is nearly exhausted or you have genuinely run out of new leads.
