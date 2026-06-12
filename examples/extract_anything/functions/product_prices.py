"""Search a shopping site and return top product prices as structured data."""

from datetime import datetime, timezone
from typing import Annotated

from hai_agents import Agent, Client, run_session
from pydantic import BaseModel, Field, HttpUrl

from examples._shared import browser_env
from examples.extract_anything.functions._common import (
    OPERATOR_PREAMBLE,
    Price,
    get_client,
    mcp,
    parse_answer,
    run_cli,
    url,
)


# Agent-facing schema: only fields the CUA can read off the page.
class Product(BaseModel):
    name: str = Field(description="the product title exactly as shown")
    price: Price = Field(description="the numeric price shown, no currency symbol")
    currency: str = Field(description="ISO currency code or symbol shown next to the price")
    url: HttpUrl = Field(description="absolute link to the product page")


class _ProductsAgentAnswer(BaseModel):
    products: list[Product]


class ProductPrices(BaseModel):
    """Tool output: the read products plus client-set capture metadata."""

    captured_at: datetime
    products: list[Product]


def get_product_prices(
    client: Client,
    *,
    site: HttpUrl,
    query: str,
    max_results: int,
) -> ProductPrices:
    """Search a shopping site and return the top product prices as structured data.

    Unlike the other ``get_*`` tools, this one mixes the agent's answer with client-side
    metadata: ``captured_at`` is stamped after the session returns (the agent can't read
    a trustworthy timestamp off the page). The agent-facing schema only includes fields
    the CUA can actually read.
    """
    task = f'On {site}, search for "{query}" and read up to {max_results} product results.'
    result = run_session(
        client,
        agent=Agent(
            name="product-prices-reader",
            description="Reads product prices off a shopping search UI.",
            instructions=f"You read shopping result pages.\n\n{OPERATOR_PREAMBLE}",
            environments=[browser_env(str(site))],
            answer_format=_ProductsAgentAnswer.model_json_schema(),
        ),
        messages=task,
        max_steps=20,
        max_time_s=180.0,
    )
    answer = parse_answer(result, _ProductsAgentAnswer)
    return ProductPrices(captured_at=datetime.now(timezone.utc), products=answer.products)


@mcp.tool(name="get_product_prices")
def _mcp(
    site: HttpUrl,
    query: Annotated[str, Field(min_length=1, description="search term")],
    max_results: Annotated[int, Field(ge=1, le=50, description="how many products to read")],
) -> ProductPrices:
    """Search a shopping site and return the top product prices as structured data."""
    return get_product_prices(get_client(), site=site, query=query, max_results=max_results)


def _cli(site: str, query: str, max_results: int) -> None:
    """Search a shopping site for product prices; stamps ``captured_at`` client-side."""
    run_cli(
        "get_product_prices",
        budget_s=180.0,
        fn=lambda: get_product_prices(get_client(), site=url(site), query=query, max_results=max_results),
    )


CLI_NAME = "product-prices"
CLI_FN = _cli
