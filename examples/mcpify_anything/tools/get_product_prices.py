"""Typed-read tool: search a shop, return the top results with structured prices."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field, HttpUrl

from examples.mcpify_anything.tool import browser_tool
from examples.mcpify_anything.types import Price


class ProductPricesInput(BaseModel):
    site: HttpUrl
    query: str = Field(min_length=1)
    max_results: int = Field(ge=1, le=50)


# Agent-facing schema: only fields the CUA can read off the page.
class Product(BaseModel):
    name: str = Field(description="the product title exactly as shown")
    price: Price = Field(description="the numeric price shown, no currency symbol")
    currency: str = Field(description="ISO currency code or symbol shown next to the price")
    url: HttpUrl = Field(description="absolute link to the product page")


class ProductPrices(BaseModel):
    """Tool output: the read products plus client-set capture metadata."""

    captured_at: datetime
    products: list[Product]


# Typed ``def`` helpers (rather than lambdas) so mypy can bind ``InputT`` for the decorator
# call — Python lambdas can't carry parameter annotations.
def _site(args: ProductPricesInput) -> HttpUrl:
    return args.site


def _prompt(args: ProductPricesInput) -> str:
    return f'On {args.site}, search for "{args.query}" and read up to {args.max_results} product results.'


@browser_tool(
    instructions="You read shopping result pages.",
    site=_site,
    prompt=_prompt,
)
async def get_product_prices(
    args: ProductPricesInput,
    answer: list[Product],
) -> ProductPrices:
    """Search a shopping site and return the top product prices as structured data."""
    return ProductPrices(captured_at=datetime.now(timezone.utc), products=answer)
