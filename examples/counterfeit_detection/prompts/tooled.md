
Your browser starts on the genuine product page. You also have two local tools — use them; they run on the
investigator's machine and are more reliable than your own memory of pages you saw many steps ago.

Tool protocol (follow exactly):
1. FIRST, call snapshot_genuine_product 2-3 times on the genuine URL with different labels
   ("overview", "logo_closeup", "hardware"). This caches reference screenshots.
2. Search the web for suspect listings.
3. BEFORE committing to any suspect as your answer, call compare_to_genuine(suspect_url, note=...) and read
   the verdict. Only answer with a suspect that scored LIKELY_COUNTERFEIT or VERY_LIKELY_COUNTERFEIT.
4. One confident hit is enough — stop and answer. If nothing is confirmed, answer counterfeit_url = null.
