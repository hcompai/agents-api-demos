"""Search a classifieds/marketplace site and return matching listings."""

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


class MarketplaceListing(BaseModel):
    title: str = Field(description="listing title as shown")
    price: Price = Field(description="asking price shown, number only")
    currency: str = Field(description="currency code or symbol shown")
    location: str = Field(description="listing location as shown")
    url: HttpUrl = Field(description="absolute link to the listing")


class MarketplaceListings(BaseModel):
    listings: list[MarketplaceListing]


def get_marketplace_listings(
    client: Client,
    *,
    site: HttpUrl,
    query: str,
    location: str,
    max_price: int,
    max_results: int,
) -> MarketplaceListings:
    """Search a classifieds/marketplace site and return matching listings as structured data."""
    task = f'On {site}, search for "{query}" in {location} priced up to {max_price}. Read up to {max_results} listings.'
    return run_extraction(
        client,
        name="marketplace-listings-reader",
        description="Reads classifieds/marketplace listings off a search UI.",
        persona="You operate marketplace search UIs.",
        start_url=str(site),
        task=task,
        answer_model=MarketplaceListings,
    )


@mcp.tool(name="get_marketplace_listings")
def _mcp(
    site: HttpUrl,
    query: Annotated[str, Field(min_length=1, description="what to search for")],
    location: Annotated[str, Field(min_length=1, description="city or region")],
    max_price: Annotated[int, Field(ge=0, description="upper bound on asking price")],
    max_results: Annotated[int, Field(ge=1, le=50, description="how many listings to read")],
) -> MarketplaceListings:
    """Search a classifieds/marketplace site and return matching listings as structured data."""
    return get_marketplace_listings(
        get_client(),
        site=site,
        query=query,
        location=location,
        max_price=max_price,
        max_results=max_results,
    )


def _cli(site: str, query: str, location: str, max_price: int, max_results: int) -> None:
    """Search a classifieds/marketplace site for matching listings."""
    run_cli(
        "get_marketplace_listings",
        budget_s=180.0,
        fn=lambda: get_marketplace_listings(
            get_client(),
            site=url(site),
            query=query,
            location=location,
            max_price=max_price,
            max_results=max_results,
        ),
    )


CLI_NAME = "marketplace-listings"
CLI_FN = _cli
