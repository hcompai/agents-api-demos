"""Search a jobs site and return matching postings as structured data."""

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


class JobListing(BaseModel):
    title: str = Field(description="job title as shown")
    company: str = Field(description="hiring company as shown")
    location: str = Field(description="job location as shown")
    url: HttpUrl = Field(description="absolute link to the posting")


class JobListings(BaseModel):
    listings: list[JobListing]


def get_job_listings(
    client: Client,
    *,
    site: HttpUrl,
    query: str,
    location: str,
    max_results: int,
) -> JobListings:
    """Search a jobs site and return matching postings as structured data."""
    # Treat the query as a role family, not a title-substring filter: many sites split
    # "developer" / "engineer" / "programmer" across postings that all match the user's
    # intent. Listing the synonyms here keeps the agent from collapsing to title-match.
    task = (
        f"On {site}, look for {query}-style roles in {location} "
        f'(treat "developer", "engineer", "programmer", and "software engineer" as '
        f"equivalent — match the role family, not the exact title). Use the site's "
        f"own filters or location pages where available. Read up to {max_results} "
        f"postings, including ALL postings whose role matches, even if the exact word "
        f'"{query}" is not in the title.'
    )
    # Hard sites (Python.org/jobs has no in-board search and splits Remote across
    # multiple sub-buckets) need more headroom than the 20-step / 180s default to walk
    # every bucket before answering.
    return run_extraction(
        client,
        name="job-listings-reader",
        description="Reads postings off a jobs search UI.",
        persona="You operate job-search UIs.",
        start_url=str(site),
        task=task,
        answer_model=JobListings,
        max_steps=35,
        max_time_s=240.0,
    )


@mcp.tool(name="get_job_listings")
def _mcp(
    site: HttpUrl,
    query: Annotated[str, Field(min_length=1, description="role family — e.g. 'developer'")],
    location: Annotated[str, Field(min_length=1, description="city or 'remote'")],
    max_results: Annotated[int, Field(ge=1, le=50, description="how many postings to read")],
) -> JobListings:
    """Search a jobs site and return matching postings as structured data."""
    return get_job_listings(get_client(), site=site, query=query, location=location, max_results=max_results)


def _cli(site: str, query: str, location: str, max_results: int) -> None:
    """Search a jobs site for postings matching a role family in a location."""
    run_cli(
        "get_job_listings",
        budget_s=240.0,
        fn=lambda: get_job_listings(
            get_client(), site=url(site), query=query, location=location, max_results=max_results
        ),
    )


CLI_NAME = "job-listings"
CLI_FN = _cli
