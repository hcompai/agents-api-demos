"""Search a booking site for available appointment slots."""

from typing import Annotated

from hai_agents import Client
from pydantic import BaseModel, Field, HttpUrl

from examples.extract_anything.functions._common import (
    get_client,
    mcp,
    run_cli,
    run_extraction,
    url,
)


class AppointmentSlot(BaseModel):
    service: str = Field(description="service the slot is for, as shown")
    location: str = Field(description="office/location as shown")
    slot: str = Field(description="the date/time of the slot exactly as shown")
    available: bool = Field(description="true if the slot is bookable")
    url: HttpUrl = Field(description="absolute link to the slot/booking page")


class AppointmentSlots(BaseModel):
    slots: list[AppointmentSlot]


def get_appointment_slots(
    client: Client,
    *,
    site: HttpUrl,
    service: str,
    location: str,
    max_results: int,
) -> AppointmentSlots:
    """Search a booking site for available appointment slots and return them as structured data."""
    task = f'On {site}, find available "{service}" appointment slots at {location}. Read up to {max_results} slots.'
    return run_extraction(
        client,
        name="appointment-slots-reader",
        description="Reads available appointment slots off a booking UI.",
        persona="You operate appointment-booking UIs.",
        start_url=str(site),
        task=task,
        answer_model=AppointmentSlots,
    )


@mcp.tool(name="get_appointment_slots")
def _mcp(
    site: HttpUrl,
    service: Annotated[str, Field(min_length=1, description="service to book")],
    location: Annotated[str, Field(min_length=1, description="city or office")],
    max_results: Annotated[int, Field(ge=1, le=50, description="how many slots to read")],
) -> AppointmentSlots:
    """Search a booking site for available appointment slots and return them as structured data."""
    return get_appointment_slots(get_client(), site=site, service=service, location=location, max_results=max_results)


def _cli(site: str, service: str, location: str, max_results: int) -> None:
    """Search a booking site for available appointment slots."""
    run_cli(
        "get_appointment_slots",
        budget_s=180.0,
        fn=lambda: get_appointment_slots(
            get_client(), site=url(site), service=service, location=location, max_results=max_results
        ),
    )


CLI_NAME = "appointment-slots"
CLI_FN = _cli
