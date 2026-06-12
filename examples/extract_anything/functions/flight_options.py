"""Search a flights site for a one-way route on a date and return fare options."""

from datetime import date
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


class FlightOption(BaseModel):
    airline: str = Field(description="operating airline as shown")
    depart_time: str = Field(description="departure time as shown")
    arrive_time: str = Field(description="arrival time as shown")
    stops: int = Field(description="number of stops (0 for nonstop)")
    price: Price = Field(description="fare shown, number only")
    currency: str = Field(description="currency code or symbol shown")
    url: HttpUrl = Field(description="absolute link to the fare/booking")


class FlightOptions(BaseModel):
    options: list[FlightOption]


def get_flight_options(
    client: Client,
    *,
    site: HttpUrl,
    origin: str,
    destination: str,
    depart_date: date,
    max_results: int,
) -> FlightOptions:
    """Search a flights site for a one-way route on a date and return fare options as structured data."""
    task = (
        f"On {site}, search one-way flights from {origin} to {destination} "
        f"on {depart_date.isoformat()}. Read up to {max_results} fare options."
    )
    return run_extraction(
        client,
        name="flight-options-reader",
        description="Reads fare options off a flights search UI.",
        persona="You operate flight-search UIs.",
        start_url=str(site),
        task=task,
        answer_model=FlightOptions,
    )


@mcp.tool(name="get_flight_options")
def _mcp(
    site: HttpUrl,
    origin: Annotated[str, Field(min_length=1, description="origin airport/city")],
    destination: Annotated[str, Field(min_length=1, description="destination airport/city")],
    depart_date: Annotated[date, Field(description="departure date")],
    max_results: Annotated[int, Field(ge=1, le=50, description="how many fares to read")],
) -> FlightOptions:
    """Search a flights site for a one-way route on a date and return fare options as structured data."""
    return get_flight_options(
        get_client(),
        site=site,
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        max_results=max_results,
    )


def _cli(site: str, origin: str, destination: str, depart_date: date, max_results: int) -> None:
    """Search a flights site for one-way fares on a route + date."""
    run_cli(
        "get_flight_options",
        budget_s=180.0,
        fn=lambda: get_flight_options(
            get_client(),
            site=url(site),
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            max_results=max_results,
        ),
    )


CLI_NAME = "flight-options"
CLI_FN = _cli
