"""Read a product catalog HTML table into structured rows."""

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


class CatalogRow(BaseModel):
    product_id: str = Field(description="the Product ID cell exactly as shown")
    name: str = Field(description="product name")
    category: str = Field(description="category")
    price: Price = Field(description="price shown, number only")
    in_stock: bool = Field(description="true if the In Stock cell says Yes")


class CatalogTable(BaseModel):
    rows: list[CatalogRow]


def get_catalog_table(client: Client, *, site: HttpUrl) -> CatalogTable:
    """Read a product catalog HTML table into structured rows."""
    task = (
        "Read EVERY row of the product catalog table on the page, not just the first one. "
        "The table has many rows — include all of them."
    )
    return run_extraction(
        client,
        name="catalog-table-reader",
        description="Reads every row of an HTML catalog table.",
        persona="You extract HTML tables row by row.",
        start_url=str(site),
        task=task,
        answer_model=CatalogTable,
    )


@mcp.tool(name="get_catalog_table")
def _mcp(site: HttpUrl) -> CatalogTable:
    """Read a product catalog HTML table into structured rows."""
    return get_catalog_table(get_client(), site=site)


def _cli(site: str) -> None:
    """Read every row of a product catalog HTML table on the page."""
    run_cli(
        "get_catalog_table",
        budget_s=180.0,
        fn=lambda: get_catalog_table(get_client(), site=url(site)),
    )


CLI_NAME = "catalog-table"
CLI_FN = _cli
