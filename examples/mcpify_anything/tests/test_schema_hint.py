"""Tests for ``schema_hint`` — the JSON-schema-to-prompt renderer.

Fixtures are local to this file so the renderer's tests stay decoupled from any tool's
shipping model (which can evolve). Each fixture exercises one schema-shape branch.
"""

from decimal import Decimal
from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, Field, HttpUrl, WithJsonSchema

from examples.mcpify_anything.schema_hint import schema_hint
from examples.mcpify_anything.types import Price


class _StatusFixture(BaseModel):
    """Exercises enum + description-as-comment + nullable + Price collapse in one model."""

    status: Literal["alpha", "beta", "gamma"] = Field(description="lifecycle stage")
    price: Price | None = Field(description="total price shown")
    currency: str | None = Field(description="currency of the price, or null")
    evidence: str


class _ProductFixture(BaseModel):
    name: str = Field(description="the product title exactly as shown")
    price: Price = Field(description="the numeric price shown")
    url: HttpUrl = Field(description="absolute link to the product page")


class _ProductList(BaseModel):
    products: list[_ProductFixture]


def test_header_demands_json_only() -> None:
    assert "ONLY" in schema_hint(_ProductList)


def test_enum_rendered_as_pipe_separated_literals() -> None:
    assert '"status": "alpha"|"beta"|"gamma"' in schema_hint(_StatusFixture)


def test_field_description_rendered_as_comment() -> None:
    # The semantics that used to live in hand-written prompts now live on the model.
    hint = schema_hint(_StatusFixture)
    assert "lifecycle stage" in hint


def test_nullable_renders_pipe_null() -> None:
    assert '"currency": string|null' in schema_hint(_StatusFixture)


def test_price_anyof_collapses_to_number() -> None:
    # Price is Annotated[Decimal, anyOf(number, string)]; we collapse to a clean ``number``.
    assert '"price": number|null' in schema_hint(_StatusFixture)


def test_number_or_string_anyof_collapses_for_any_type_not_just_price() -> None:
    # The collapse rule must be domain-neutral: any pydantic type that advertises a
    # number-or-string anyOf via WithJsonSchema renders as ``number`` in prompts. Guards
    # against re-introducing a ``Price``-specific code path that would skip other types.
    NumberOrString = Annotated[Decimal, WithJsonSchema({"anyOf": [{"type": "number"}, {"type": "string"}]})]

    class _Bag(BaseModel):
        amount: NumberOrString

    hint = schema_hint(_Bag)
    assert '"amount": number' in hint
    assert "string" not in hint  # the union side was collapsed, not just hidden behind ``number|string``


def test_nested_list_of_objects_rendered() -> None:
    hint = schema_hint(_ProductList)
    assert '"products": [' in hint
    assert '"name": string' in hint
    assert '"price": number' in hint
    assert '"url": string' in hint


def test_unknown_type_raises() -> None:
    # A model whose schema carries a type ``schema_hint`` cannot map should fail loudly,
    # not silently emit a wrong token.
    class _Weird(BaseModel):
        blob: object

    with pytest.raises(ValueError):
        schema_hint(_Weird)
