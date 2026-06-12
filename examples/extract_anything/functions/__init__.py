"""Deterministic typed functions over the browser agent — one file per tool.

Each ``functions/<name>.py`` co-locates three surfaces for one tool:

- The output Pydantic model(s) — the typed contract callers see.
- The Python function ``get_<name>(client, ...)`` (or ``describe_<name>(client) -> Output``,
  ``extract(client, ...) -> dict``).
- An ``@mcp.tool`` wrapper that injects the SDK client and exposes the same shape on the
  wire, and a ``_cli`` subcommand for shell use. ``CLI_NAME`` + ``CLI_FN`` make the
  subcommand discoverable here.

Importing this package triggers every tool module's ``@mcp.tool`` registration as a side
effect — ``server.py`` then just imports the package and calls ``mcp.run()``. ``cli.py``
reads ``CLI_SUBCOMMANDS`` to dispatch.
"""

from examples.extract_anything.functions import (
    apartment_listings,
    appointment_slots,
    catalog_table,
    extract as extract_module,
    flight_options,
    job_listings,
    marketplace_listings,
    picture,
    product_prices,
    products_infinite_scroll,
    recent_posts,
)
from examples.extract_anything.functions.apartment_listings import (
    ApartmentListing,
    ApartmentListings,
    get_apartment_listings,
)
from examples.extract_anything.functions.appointment_slots import (
    AppointmentSlot,
    AppointmentSlots,
    get_appointment_slots,
)
from examples.extract_anything.functions.catalog_table import CatalogRow, CatalogTable, get_catalog_table
from examples.extract_anything.functions.extract import extract
from examples.extract_anything.functions.flight_options import FlightOption, FlightOptions, get_flight_options
from examples.extract_anything.functions.job_listings import JobListing, JobListings, get_job_listings
from examples.extract_anything.functions.marketplace_listings import (
    MarketplaceListing,
    MarketplaceListings,
    get_marketplace_listings,
)
from examples.extract_anything.functions.picture import FeaturedPicture, describe_picture_of_the_day
from examples.extract_anything.functions.product_prices import Product, ProductPrices, get_product_prices
from examples.extract_anything.functions.products_infinite_scroll import (
    ScrolledProduct,
    ScrolledProducts,
    get_products_infinite_scroll,
)
from examples.extract_anything.functions.recent_posts import RecentPosts, SocialPost, get_recent_posts

# Order = order shown in ``extract-cli --help``. Picture first because it's the headline demo.
_TOOL_MODULES = [
    picture,
    extract_module,
    apartment_listings,
    appointment_slots,
    catalog_table,
    flight_options,
    job_listings,
    marketplace_listings,
    product_prices,
    products_infinite_scroll,
    recent_posts,
]

CLI_SUBCOMMANDS = {mod.CLI_NAME: mod.CLI_FN for mod in _TOOL_MODULES}

__all__ = [
    "CLI_SUBCOMMANDS",
    "ApartmentListing",
    "ApartmentListings",
    "AppointmentSlot",
    "AppointmentSlots",
    "CatalogRow",
    "CatalogTable",
    "FeaturedPicture",
    "FlightOption",
    "FlightOptions",
    "JobListing",
    "JobListings",
    "MarketplaceListing",
    "MarketplaceListings",
    "Product",
    "ProductPrices",
    "RecentPosts",
    "ScrolledProduct",
    "ScrolledProducts",
    "SocialPost",
    "describe_picture_of_the_day",
    "extract",
    "get_apartment_listings",
    "get_appointment_slots",
    "get_catalog_table",
    "get_flight_options",
    "get_job_listings",
    "get_marketplace_listings",
    "get_product_prices",
    "get_products_infinite_scroll",
    "get_recent_posts",
]
