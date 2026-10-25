"""
The docs page, in the design of the LinuxServer.io site ("Raft"). The endpoint reference is read from the
generated OpenAPI spec, so the docs can never disagree with the API; the templates only lay it out.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from . import responses
from .config import ORG, WEBSITE, SiteConfig
from .fleet import Fleet
from .templating import env

EXAMPLE_IMAGE = "sonarr"
EXAMPLE_PACKAGE = "curl"
MAX_DEPTH = 6
"""Deep enough for every schema; stops a recursive schema from recursing forever."""

DATA_SOURCES = [
    (
        "Image list, description, tags, architectures, changelog, config, snippets",
        "image.yml on every live branch of each docker-* repository",
        "https://github.com/linuxserver-playground",
    ),
    (
        "version, version_timestamp, release_url, builds, packages, layers, diffs",
        "The build bundle attached to every GitHub Release",
        "https://github.com/linuxserver-playground/builder/blob/main/CONVENTIONS.md",
    ),
    ("stars, archived", "GitHub repository (hourly poll)", "https://github.com/linuxserver-playground"),
    ("mods", "mod.yml on every branch of docker-mods", "https://github.com/linuxserver-playground/docker-mods"),
]
"""The source of each field, for the table at the end of the docs page."""

Schema = dict[str, Any]


# ---------------------------------------------------------------------------------------------------
# Reading the spec


def _resolve(spec: Schema, schema: Schema) -> Schema:
    """Follows a local "#/components/…" reference."""
    while "$ref" in schema:
        target: Any = spec
        for key in schema["$ref"].removeprefix("#/").split("/"):
            target = target[key]
        schema = target
    return schema


def _variants(schema: Schema) -> list[Schema]:
    """The alternatives of an anyOf/oneOf, without the null that Pydantic adds for optional fields."""
    options = schema.get("anyOf") or schema.get("oneOf") or [schema]
    return [s for s in options if s.get("type") != "null"]


def type_label(spec: Schema, schema: Schema) -> str:
    variants = _variants(schema)
    if len(variants) > 1:
        return " | ".join(type_label(spec, s) for s in variants)
    schema = variants[0] if variants else {}
    if "$ref" in schema:
        target = _resolve(spec, schema)
        return schema["$ref"].rsplit("/", 1)[-1] if "properties" in target else type_label(spec, target)
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    if schema.get("type") == "array":
        return type_label(spec, schema.get("items", {})) + "[]"
    if isinstance(schema.get("additionalProperties"), dict):
        return f"map<string, {type_label(spec, schema['additionalProperties'])}>"
    return f"{schema.get('type', 'any')} ({schema['format']})" if "format" in schema else schema.get("type", "any")


def _expandable(spec: Schema, schema: Schema) -> Schema | None:
    """The object a field expands into, if any: itself, its array items, or its map values."""
    variants = _variants(schema)
    if len(variants) != 1:
        return None
    s = _resolve(spec, variants[0])
    for candidate in (s, s.get("items"), s.get("additionalProperties")):
        if isinstance(candidate, dict) and "properties" in _resolve(spec, candidate):
            return _resolve(spec, candidate)
    return None


@dataclass
class FieldView:
    name: str
    type: str
    required: bool
    description: str
    children: list["FieldView"] = field(default_factory=list)


def _fields(spec: Schema, schema: Schema, depth: int = 0) -> list[FieldView]:
    required = set(schema.get("required", []))
    views = []
    for name, prop in schema.get("properties", {}).items():
        child = _expandable(spec, prop)
        description = prop.get("description") or (child.get("description", "") if child else "")
        views.append(
            FieldView(
                name=name,
                type=type_label(spec, prop),
                required=name in required,
                description=description,
                children=_fields(spec, child, depth + 1) if child and depth < MAX_DEPTH else [],
            )
        )
    return views


@dataclass
class OperationView:
    path: str
    anchor: str
    summary: str
    description: str
    params: list[FieldView]
    media_type: str
    response: str
    """The response's type: a schema name, or e.g. "string document" for YAML and XML."""
    fields: list[FieldView]
    path_params: list[tuple[str, str]]
    """Each path parameter with the example value its input starts with."""
    open_href: str

    @property
    def path_parts(self) -> list[tuple[str, bool]]:
        """The path split into (text, is_parameter) for highlighting."""
        return [(part, part.startswith("{")) for part in re.split(r"(\{[^}]+\})", self.path) if part]


def _operation(spec: Schema, path: str, op: Schema, config: SiteConfig, examples: dict[str, str]) -> OperationView:
    content: dict[str, Schema] = op["responses"]["200"]["content"]
    media_type, body = next(iter(content.items()))
    schema: Schema = body["schema"]
    resolved = _expandable(spec, schema)
    params = [
        FieldView(
            name=p["name"],
            type=f"{p['in']} · {type_label(spec, p.get('schema', {}))}",
            required=p.get("required", False),
            description=p.get("description", ""),
        )
        for p in op.get("parameters", [])
    ]
    path_params = [(p["name"], examples.get(p["name"], "")) for p in op.get("parameters", []) if p["in"] == "path"]
    # The real URL, so Open works before (or without) the script, which keeps it in sync with the inputs.
    open_path = path
    for name, value in path_params:
        open_path = open_path.replace(f"{{{name}}}", quote(value))
    return OperationView(
        path=path,
        anchor=f"op-{op['operationId']}",
        summary=op["summary"],
        description=op.get("description", ""),
        params=params,
        media_type=media_type,
        response=type_label(spec, schema) + ("" if media_type == "application/json" else " document"),
        fields=_fields(spec, resolved) if resolved else [],
        path_params=path_params,
        open_href=config.base_path + open_path.lstrip("/"),
    )


def operation_groups(
    spec: Schema, config: SiteConfig, examples: dict[str, str]
) -> list[tuple[Schema, list[OperationView]]]:
    """Operations grouped by tag, in the order the spec lists its tags."""
    ops = [(path, item["get"]) for path, item in spec["paths"].items() if "get" in item]
    return [
        (
            tag,
            [_operation(spec, path, op, config, examples) for path, op in ops if tag["name"] in op.get("tags", [])],
        )
        for tag in spec.get("tags", [])
    ]


# ---------------------------------------------------------------------------------------------------
# Pages


def _context(fleet: Fleet, config: SiteConfig) -> dict[str, Any]:
    """What the layout shows on every page."""
    stats = responses.stats(fleet)
    return {
        "fleet": fleet,
        "config": config,
        "base": config.base_path,
        "website": WEBSITE,
        "org": ORG,
        "stats": stats,
        "healthy": fleet.health == "Success",
        "builds": ("Builds", stats.builds, "build records"),
    }


def example_values(fleet: Fleet, name: str, version: str) -> dict[str, str]:
    """A value for every path parameter that resolves to a published file, for the Open links and inputs."""
    builds = [(tag, arch) for n, tag, arch in responses.package_routes(fleet) if n == name]
    tag, arch = next(
        (b for b in builds if b == (version, "amd64")),
        next((b for b in builds if b[0] == version), builds[0] if builds else (version, "amd64")),
    )
    slugs = responses.package_slugs(fleet)
    package = EXAMPLE_PACKAGE if EXAMPLE_PACKAGE in slugs or not slugs else slugs[0]
    return {"name": name, "tag": tag, "arch": arch, "package": package}


def render_index(fleet: Fleet, spec: Schema, config: SiteConfig) -> str:
    example = next((i for i in fleet.images if i.name == EXAMPLE_IMAGE), fleet.images[0] if fleet.images else None)
    example_name = example.name if example else EXAMPLE_IMAGE
    example_version = example.version if example else "latest"
    return env.get_template("index.html").render(
        **_context(fleet, config),
        spec=spec,
        groups=operation_groups(spec, config, example_values(fleet, example_name, example_version)),
        example_name=example_name,
        example_version=example_version,
        image_names=[i.name for i in fleet.images],
        data_sources=DATA_SOURCES,
    )


def render_not_found(fleet: Fleet, config: SiteConfig) -> str:
    return env.get_template("404.html").render(**_context(fleet, config))
