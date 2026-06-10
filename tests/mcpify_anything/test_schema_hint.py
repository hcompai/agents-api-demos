"""Tests for ``schema_hint`` — the JSON-schema-to-prompt renderer."""

from decimal import Decimal
from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, Field, HttpUrl, WithJsonSchema

from examples.mcpify_anything.schema_hint import schema_hint
from examples.mcpify_anything.types import Price


class _StatusFixture(BaseModel):
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
    hint = schema_hint(_StatusFixture)
    assert "lifecycle stage" in hint


def test_nullable_renders_pipe_null() -> None:
    assert '"currency": string|null' in schema_hint(_StatusFixture)


def test_price_anyof_collapses_to_number() -> None:
    assert '"price": number|null' in schema_hint(_StatusFixture)


def test_number_or_string_anyof_collapses_for_any_type_not_just_price() -> None:
    # Collapse rule must be domain-neutral, not Price-specific.
    NumberOrString = Annotated[Decimal, WithJsonSchema({"anyOf": [{"type": "number"}, {"type": "string"}]})]

    class _Bag(BaseModel):
        amount: NumberOrString

    hint = schema_hint(_Bag)
    assert '"amount": number' in hint
    assert "string" not in hint


def test_nested_list_of_objects_rendered() -> None:
    hint = schema_hint(_ProductList)
    assert '"products": [' in hint
    assert '"name": string' in hint
    assert '"price": number' in hint
    assert '"url": string' in hint


def test_unknown_type_raises() -> None:
    # Fail loud on schema shapes the renderer can't map — never emit a wrong token silently.
    class _Weird(BaseModel):
        blob: object

    with pytest.raises(ValueError):
        schema_hint(_Weird)
