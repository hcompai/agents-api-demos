"""Scroll an infinite-scroll page to load products, then read them as structured data."""

from typing import Annotated

from hai_agents import Client
from pydantic import BaseModel, Field, HttpUrl

from examples.extract_anything.functions._common import (
    Price,
    get_client,
    mcp,
    run_cli,
    run_extraction,
    url,
)


class ScrolledProduct(BaseModel):
    name: str = Field(description="product name exactly as shown")
    price: Price = Field(description="the price shown, number only")


class ScrolledProducts(BaseModel):
    products: list[ScrolledProduct]


def get_products_infinite_scroll(
    client: Client,
    *,
    site: HttpUrl,
    max_results: int,
) -> ScrolledProducts:
    """Scroll an infinite-scroll page to load products, then read them as structured data."""
    task = (
        f"On {site}, products load lazily as you scroll. Scroll down to load more products "
        f"until at least {max_results} are visible, then STOP scrolling immediately. Do NOT try "
        "to reach the bottom of the page — this list may be effectively endless, so chasing the "
        f"bottom will never terminate. As soon as you can see {max_results} products (or a "
        f"scroll reveals no new ones), read the first {max_results} products."
    )
    return run_extraction(
        client,
        name="infinite-scroll-reader",
        description="Loads an infinite-scroll list far enough to read N items.",
        persona=(
            "You load lazy/infinite-scroll lists by scrolling. "
            "Stop scrolling as soon as you have enough products and answer right away; never "
            "keep scrolling indefinitely trying to reach the end of an endless list."
        ),
        start_url=str(site),
        task=task,
        answer_model=ScrolledProducts,
        max_steps=30,
        max_time_s=240.0,
    )


@mcp.tool(name="get_products_infinite_scroll")
def _mcp(
    site: HttpUrl,
    max_results: Annotated[int, Field(ge=1, le=100, description="how many products to load before stopping")],
) -> ScrolledProducts:
    """Scroll an infinite-scroll page to load products, then read them as structured data."""
    return get_products_infinite_scroll(get_client(), site=site, max_results=max_results)


def _cli(site: str, max_results: int) -> None:
    """Scroll a lazy-loaded products page until N items load, then read them."""
    run_cli(
        "get_products_infinite_scroll",
        budget_s=240.0,
        fn=lambda: get_products_infinite_scroll(get_client(), site=url(site), max_results=max_results),
    )


CLI_NAME = "products-infinite-scroll"
CLI_FN = _cli
