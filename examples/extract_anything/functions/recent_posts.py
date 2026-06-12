"""Read the most recent posts from an account/profile as structured data."""

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


class SocialPost(BaseModel):
    author: str = Field(description="post author/handle as shown")
    text: str = Field(description="post text/content as shown")
    posted_at: str = Field(description="when the post was made, as shown (e.g. a date or relative time)")
    url: HttpUrl = Field(description="absolute link to the post")


class RecentPosts(BaseModel):
    posts: list[SocialPost]


def get_recent_posts(
    client: Client,
    *,
    site: HttpUrl,
    account: str,
    max_results: int,
) -> RecentPosts:
    """Read the most recent posts from an account/profile as structured data."""
    task = f"On {site}, open the {account} account/profile and read its most recent up to {max_results} posts."
    return run_extraction(
        client,
        name="recent-posts-reader",
        description="Reads recent posts off a social profile.",
        persona="You read social profiles.",
        start_url=str(site),
        task=task,
        answer_model=RecentPosts,
    )


@mcp.tool(name="get_recent_posts")
def _mcp(
    site: HttpUrl,
    account: Annotated[str, Field(min_length=1, description="account/handle to open")],
    max_results: Annotated[int, Field(ge=1, le=50, description="how many posts to read")],
) -> RecentPosts:
    """Read the most recent posts from an account/profile as structured data."""
    return get_recent_posts(get_client(), site=site, account=account, max_results=max_results)


def _cli(site: str, account: str, max_results: int) -> None:
    """Read the most recent posts from a social account/profile."""
    run_cli(
        "get_recent_posts",
        budget_s=180.0,
        fn=lambda: get_recent_posts(get_client(), site=url(site), account=account, max_results=max_results),
    )


CLI_NAME = "recent-posts"
CLI_FN = _cli
