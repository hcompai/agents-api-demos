"""Action tool: add items to a cart, then read the cart back as proof and derive client-side totals."""

from __future__ import annotations  # ``from_run`` returns the enclosing class — needs deferred eval.

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from examples.mcpify_anything.tool import browser_tool
from examples.mcpify_anything.types import Price

CartStatus = Literal["added", "partial", "noop"]


class CartItem(BaseModel):
    product_url: HttpUrl
    quantity: int = Field(ge=1, le=99)


class CartItemsInput(BaseModel):
    items: list[CartItem] = Field(min_length=1)


# Agent-facing per-line schema. The answer is ``list[CartLine]``; the receipt status,
# total, currency, and evidence are derived client-side below — the agent only reports
# what it can read off the cart page.
class CartLine(BaseModel):
    name: str = Field(description="product name exactly as shown in the cart")
    quantity: int = Field(description="quantity for this line as shown in the cart")
    line_total: Price | None = Field(description="line subtotal shown, or null if none is shown")
    currency: str | None = Field(description="currency of the line subtotal, or null")


class CartReceipt(BaseModel):
    """Tool output: the agent's verified cart lines plus client-derived summary fields."""

    status: CartStatus
    requested_items: list[CartItem]
    lines: list[CartLine]
    cart_total: Price | None
    currency: str | None
    evidence: str

    @classmethod
    def from_run(cls, requested: list[CartItem], lines: list[CartLine]) -> CartReceipt:
        return cls(
            status=cls._status(requested, lines),
            requested_items=requested,
            lines=lines,
            cart_total=cls._cart_total(lines),
            currency=cls._currency(lines),
            evidence=cls._evidence(lines),
        )

    @staticmethod
    def _status(requested: list[CartItem], lines: list[CartLine]) -> CartStatus:
        if not lines:
            return "noop"
        if len(lines) < len(requested):
            return "partial"
        return "added"

    @staticmethod
    def _currency(lines: list[CartLine]) -> str | None:
        # Mixed-currency carts are real (international shops, multi-vendor marketplaces). Summing
        # across currencies would be silently wrong, so we return None and surface "we can't
        # compute one" — matching how _cart_total already handles missing line totals.
        seen = {line.currency for line in lines if line.currency}
        if len(seen) != 1:
            return None
        return next(iter(seen))

    @staticmethod
    def _cart_total(lines: list[CartLine]) -> Price | None:
        if CartReceipt._currency(lines) is None:
            return None
        # Seeding with the first total keeps the running type Decimal (vs sum()'s int zero).
        totals: list[Decimal] = [line.line_total for line in lines if line.line_total is not None]
        if not totals or len(totals) != len(lines):
            return None
        return sum(totals[1:], totals[0])

    @staticmethod
    def _evidence(lines: list[CartLine]) -> str:
        if not lines:
            return "cart is empty"
        return "; ".join(f"{line.name} x{line.quantity}" for line in lines)


def _render_items(items: list[CartItem]) -> str:
    return "; ".join(f"{item.product_url} (quantity {item.quantity})" for item in items)


@browser_tool(
    instructions=("You add items to e-commerce carts and verify the result by reading the cart back."),
    site=lambda a: a.items[0].product_url,
    prompt=lambda a: (
        "Add each of these products to the shopping cart at the given quantity, then open the "
        f"cart page and read back every line item it now shows. Products: {_render_items(a.items)}."
    ),
)
async def add_cart_items(
    args: CartItemsInput,
    answer: list[CartLine],
) -> CartReceipt:
    """Add one or more products to the site's shopping cart, then read the cart back as proof."""
    return CartReceipt.from_run(args.items, answer)
