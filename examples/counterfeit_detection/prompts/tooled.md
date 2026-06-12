
## Your task — find ONE visually verified counterfeit, then stop

You also have two local tools — use them; they run on the investigator's machine and are more
reliable than your own memory of pages you saw many steps ago.

Tool protocol (follow exactly):
1. FIRST, call snapshot_genuine_product 2-3 times on the genuine URL with different labels
   ("overview", "logo_closeup", "hardware") — do this together with Step 0's detail extraction.
2. Run the replica-targeted queries, scanning results as instructed.
3. When a site passes the ≥3-red-flags check, call compare_to_genuine(suspect_url, note=...) BEFORE
   committing to it. Only answer with a suspect whose verdict is LIKELY_COUNTERFEIT or
   VERY_LIKELY_COUNTERFEIT on top of its red flags.
4. One confirmed hit is enough — STOP. If nothing passes both checks after scanning ~10-15 top
   results, answer counterfeit_url = null, confidence = "none", and still fill product_info.
