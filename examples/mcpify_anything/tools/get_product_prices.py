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


@browser_tool(
    instructions="You read shopping result pages.",
    site=lambda a: a.site,
    prompt=lambda a: f'On {a.site}, search for "{a.query}" and read up to {a.max_results} product results.',
)
async def get_product_prices(
    args: ProductPricesInput,
    answer: list[Product],
) -> ProductPrices:
    """Search a shopping site and return the top product prices as structured data."""
    return ProductPrices(captured_at=datetime.now(timezone.utc), products=answer)
