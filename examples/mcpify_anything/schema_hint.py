"""Render a Pydantic model's JSON schema into a compact 'return ONLY this JSON' prompt instruction."""

from typing import Any

from pydantic import BaseModel

# ``model_json_schema()`` returns nested ``dict[str, Any]`` (arbitrary JSON Schema). ``Any`` is
# the honest type for a schema node since its keys/values vary by shape; we narrow each node
# by inspecting the keys we render and fail loud on anything we do not understand.
SchemaNode = dict[str, Any]

_INDENT = "  "
_HEADER = "Return ONLY a JSON object matching this shape, with no other prose:\n"
_SCALAR_TOKENS = {
    "string": "string",
    "number": "number",
    "integer": "integer",
    "boolean": "boolean",
    "null": "null",
}


def schema_hint(model: type[BaseModel]) -> str:
    """Render a model's JSON schema into a 'return ONLY this JSON' prompt instruction.

    Single source of truth for the answer shape: the model defines the structure and (via
    ``Field(description=...)``) the per-field semantics, so a tool's prompt never restates
    either by hand. Nested models (``$defs``/``$ref``), arrays, enums, nullables and the
    ``Price`` number-or-string union are rendered as compact, model-friendly tokens.

    Args:
        model: The Pydantic model whose schema should be rendered.

    Returns:
        A multi-line string suitable to be appended to the user message of a CUA prompt.
    """
    schema = model.model_json_schema()
    defs: dict[str, SchemaNode] = schema.get("$defs", {})
    return _HEADER + _render(schema, defs, indent=0)


def _render(node: SchemaNode, defs: dict[str, SchemaNode], indent: int) -> str:
    node = _resolve(node, defs)
    if "enum" in node:
        return _enum_token(node["enum"])
    if "anyOf" in node:
        return _anyof_token(node["anyOf"], defs)
    node_type = node.get("type")
    if node_type == "array":
        return _render_array(node, defs, indent)
    if node_type == "object" or "properties" in node:
        return _render_object(node, defs, indent)
    return _scalar_token(node_type)


def _render_object(node: SchemaNode, defs: dict[str, SchemaNode], indent: int) -> str:
    properties: dict[str, SchemaNode] = node.get("properties", {})
    inner_pad = _INDENT * (indent + 1)
    close_pad = _INDENT * indent
    fields = list(properties.items())
    lines: list[str] = []
    for position, (key, prop) in enumerate(fields):
        value = _render(prop, defs, indent + 1)
        comma = "," if position < len(fields) - 1 else ""
        description = prop.get("description")  # read before _resolve drops $ref siblings
        comment = f"  // {description}" if description else ""
        lines.append(f'{inner_pad}"{key}": {value}{comma}{comment}')
    return "{\n" + "\n".join(lines) + f"\n{close_pad}}}"


def _render_array(node: SchemaNode, defs: dict[str, SchemaNode], indent: int) -> str:
    inner_pad = _INDENT * (indent + 1)
    close_pad = _INDENT * indent
    item = _render(node["items"], defs, indent + 1)
    return f"[\n{inner_pad}{item}\n{close_pad}]"


def _resolve(node: SchemaNode, defs: dict[str, SchemaNode]) -> SchemaNode:
    ref = node.get("$ref")
    if ref is not None:
        return defs[ref.split("/")[-1]]
    return node


def _enum_token(values: list[object]) -> str:
    return "|".join(f'"{value}"' if isinstance(value, str) else str(value) for value in values)


def _anyof_token(subschemas: list[SchemaNode], defs: dict[str, SchemaNode]) -> str:
    tokens: list[str] = []
    for sub in subschemas:
        resolved = _resolve(sub, defs)
        tokens.append(_enum_token(resolved["enum"]) if "enum" in resolved else _scalar_token(resolved.get("type")))
    # Some pydantic types (notably Decimals whose default regex pattern we strip via
    # WithJsonSchema) advertise a number-or-string anyOf in their JSON schema. Render the
    # cleaner ``number`` token in prompts so the agent isn't told it may answer with a string.
    if "number" in tokens and "string" in tokens:
        tokens = [token for token in tokens if token != "string"]
    deduped: list[str] = []
    for token in tokens:
        if token not in deduped:
            deduped.append(token)
    return "|".join(deduped)


def _scalar_token(node_type: object) -> str:
    token = _SCALAR_TOKENS.get(node_type) if isinstance(node_type, str) else None
    if token is None:
        raise ValueError(f"schema_hint cannot render schema node of type {node_type!r}")
    return token
