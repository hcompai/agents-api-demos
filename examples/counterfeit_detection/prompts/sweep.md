
Your browser starts on the genuine product page. You have a step + time budget — spend it. Your goal is to
find AS MANY distinct counterfeit listings as you can before the budget runs out, not just one.

Tool protocol (follow exactly):
1. FIRST, call snapshot_genuine_product 2-3 times on the genuine URL with different labels.
2. Search broad: replica-cluster TLDs (.top, .cc, .shop, .vip), large marketplaces (AliExpress, DHgate),
   "1:1 replica" / "AAA quality" sites, replica-community link lists.
3. For each suspect, call compare_to_genuine(suspect_url, note=...). If the verdict is LIKELY_COUNTERFEIT or
   stronger, immediately call record_counterfeit(...) with the details, then MOVE ON to the next suspect.
   Do not dwell on any single site.
4. Findings live in record_counterfeit — your final answer is only a short summary (count + why you stopped).
   Stop when the budget is nearly exhausted or you have genuinely run out of new leads.
