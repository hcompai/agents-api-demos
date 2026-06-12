"""Search a real-estate site and return matching rental listings as structured data."""

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


class ApartmentListing(BaseModel):
    title: str = Field(description="listing title or street/address as shown")
    rent: Price = Field(description="monthly rent shown, number only")
    currency: str = Field(description="currency code or symbol shown")
    beds: int = Field(description="number of bedrooms shown")
    url: HttpUrl = Field(description="absolute link to the listing")


class ApartmentListings(BaseModel):
    listings: list[ApartmentListing]


def get_apartment_listings(
    client: Client,
    *,
    site: HttpUrl,
    city: str,
    max_rent: int,
    min_beds: int,
    max_results: int,
) -> ApartmentListings:
    """Search a real-estate site and return matching rental listings as structured data."""
    task = (
        f"On {site}, search rental apartments in {city} with at least {min_beds} "
        f"bedrooms and rent up to {max_rent}. Read up to {max_results} listings."
    )
    return run_extraction(
        client,
        name="apartment-listings-reader",
        description="Reads rental listings off a real-estate search UI.",
        persona="You operate real-estate search UIs.",
        start_url=str(site),
        task=task,
        answer_model=ApartmentListings,
    )


@mcp.tool(name="get_apartment_listings")
def _mcp(
    site: HttpUrl,
    city: Annotated[str, Field(min_length=1, description="city to search")],
    max_rent: Annotated[int, Field(ge=0, description="upper bound on monthly rent")],
    min_beds: Annotated[int, Field(ge=0, description="minimum number of bedrooms")],
    max_results: Annotated[int, Field(ge=1, le=50, description="how many listings to read")],
) -> ApartmentListings:
    """Search a real-estate site and return matching rental listings as structured data."""
    return get_apartment_listings(
        get_client(),
        site=site,
        city=city,
        max_rent=max_rent,
        min_beds=min_beds,
        max_results=max_results,
    )


def _cli(site: str, city: str, max_rent: int, min_beds: int, max_results: int) -> None:
    """Search a real-estate site and return matching rental listings."""
    run_cli(
        "get_apartment_listings",
        budget_s=180.0,
        fn=lambda: get_apartment_listings(
            get_client(),
            site=url(site),
            city=city,
            max_rent=max_rent,
            min_beds=min_beds,
            max_results=max_results,
        ),
    )


CLI_NAME = "apartment-listings"
CLI_FN = _cli
