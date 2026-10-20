"""Drive an H Computer-Use agent to add Daft Punk's "Random Access Memories" to an Amazon cart.

The agent *sees* Amazon and decides what to click/type/scroll; there's no Amazon API here.
Run with:  source .env && .hai-venv/bin/python add_to_cart.py
(Reads HAI_API_KEY from the environment; `source .env` first, or export it.)
"""

import os
import sys
from hai_agents import Client, wait_for_session

# EU is the SDK default; the agent-view host below must match the region.
AGENT_VIEW_HOST = "https://platform.eu.hcompany.ai"

# A visual browser agent: it perceives the page and clicks through the UI (needed for "add to cart").
AGENT = "h/web-surfer-pro"

# The task is *what to do now* → goes in `messages`, never in `instructions`.
TASK = """\
Go to https://www.amazon.com. In the search bar, search for "Random Access Memories Daft Punk".

From the results, open the main album listing for the Daft Punk album (prefer the CD or Vinyl
music product, not a t-shirt or unrelated item). On the product page, click "Add to Cart".
Then confirm the item is in the cart.
Report the exact product title, format, price, and whether it was successfully added to the cart.
Do NOT proceed to checkout or enter any payment information.
"""


def main() -> int:
    api_key = os.environ.get("HAI_API_KEY")
    if not api_key:
        print("Missing HAI_API_KEY. `source .env` first, or export it in the environment.", file=sys.stderr)
        return 1

    client = Client(api_key=api_key)

    # Create the session first so we can print the live link *before* the run blocks.
    session = client.sessions.create_session(agent=AGENT, messages=TASK)

    live_url = f"{AGENT_VIEW_HOST}/agent-view/{session.id}"
    print(f"Session : {session.id}", flush=True)
    print(f"Watch   : {live_url}", flush=True)

    result = wait_for_session(client, session.id, timeout_seconds=600)
    status = result.status if hasattr(result, "status") else "settled"
    print(f"\nStatus  : {status}")
    print(f"Answer  :\n{result.answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
