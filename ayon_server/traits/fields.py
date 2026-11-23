"""Trait fields of representations, for filter options and analysis.

Representations store their traits in the `traits` column. A database
trigger derives two columns from it (see schemas/migrations/00000017.sql):

- `trait_ids`: versioned and versionless ids of the traits present
- `trait_fields`: the short scalar fields of each trait, keyed by the
  versioned trait id. Numbers, booleans, strings of up to 64 characters
  and lists of up to 32 such values are kept, everything else (file
  lists, nested objects, long strings) is left out.

Filters use `traits/<trait id>/<field>` keys (see ayon_server.sqlfilter).
Field types come from the JSON Schemas in the trait definitions.

Project usage is cached in Redis for `USAGE_CACHE_TTL` seconds, because
counting reads the trait fields of every representation.

Studio settings (`traits_filtering` in the project settings of the core
addon) list the traits and fields offered for filtering (an allow list)
and add synonyms. They only change what the filter bar offers, other
fields still work in filters. Without the settings no field is offered.
"""

import re
import time
from typing import Annotated, Any

from ayon_server.addons.models import TraitDefinition
from ayon_server.addons.traits import TRAIT_VERSION_REGEX, get_trait_definitions
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import log_traceback
from ayon_server.sqlfilter import TraitFieldTypes
from ayon_server.types import Field, OPModel

USAGE_CACHE_NS = "project-trait-fields"
USAGE_CACHE_TTL = 60
FIELD_TYPES_TTL = 60
MAX_VALUES_LIMIT = 500

CORE_ADDON_NAME = "core"

FIELD_NAME_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# String formats whose values are not useful in filters
SKIPPED_STRING_FORMATS = {"regex", "path", "uri", "file-path", "directory-path"}

ACRONYMS = {"fps", "id", "ocio", "uri", "url", "udim", "uv"}


#
# Field types from trait definitions
#


def field_title(name: str) -> str:
    """Human title of a field name: `display_window_width` -> `Display Window Width`."""

    words = [word for word in name.split("_") if word]
    return " ".join(
        word.upper() if word.lower() in ACRONYMS else word[:1].upper() + word[1:]
        for word in words
    )


def _non_null(schema: dict[str, Any]) -> dict[str, Any]:
    """Unwrap `anyOf: [X, {type: null}]` and `type: [X, null]`."""

    for key in ("anyOf", "oneOf"):
        options = schema.get(key)
        if isinstance(options, list):
            rest = [o for o in options if o.get("type") != "null"]
            if len(rest) == 1:
                return {**schema, **rest[0]}
    return schema


def _single_type(schema: dict[str, Any]) -> str | None:
    value = schema.get("type")
    if isinstance(value, list):
        rest = [t for t in value if t != "null"]
        return rest[0] if len(rest) == 1 else None
    return value if isinstance(value, str) else None


def schema_field_type(schema: dict[str, Any]) -> str | None:
    """Filter type of a trait field from its JSON Schema.

    Returns None for fields that cannot be filtered (objects, lists of
    objects, regular expressions and paths).
    """

    schema = _non_null(schema)
    json_type = _single_type(schema)
    if json_type is None and isinstance(schema.get("enum"), list):
        values = [v for v in schema["enum"] if v is not None]
        if values and all(isinstance(v, str) for v in values):
            json_type = "string"
    if json_type == "integer":
        return "integer"
    if json_type == "number":
        return "float"
    if json_type == "boolean":
        return "boolean"
    if json_type == "string":
        if schema.get("format") in SKIPPED_STRING_FORMATS:
            return None
        return "string"
    if json_type == "array":
        items = schema.get("items")
        if not isinstance(items, dict):
            return None
        item_type = _single_type(_non_null(items))
        if item_type == "string":
            return "list_of_strings"
        if item_type == "integer":
            return "list_of_integers"
    return None


class FieldSpec(OPModel):
    type: str
    title: str
    description: str = ""
    enum: list[Any] | None = None


def get_definition_fields(definition: TraitDefinition) -> dict[str, FieldSpec]:
    """Filterable top-level fields of a trait version."""

    properties = definition.trait_schema.get("properties") or {}
    result: dict[str, FieldSpec] = {}
    for name, schema in properties.items():
        if not isinstance(schema, dict) or not FIELD_NAME_REGEX.match(name):
            continue
        field_type = schema_field_type(schema)
        if field_type is None:
            continue
        schema = _non_null(schema)
        enum = schema.get("enum")
        result[name] = FieldSpec(
            type=field_type,
            title=schema.get("title") or field_title(name),
            description=schema.get("description") or "",
            enum=[v for v in enum if v is not None] if isinstance(enum, list) else None,
        )
    return result


_field_types_cache: tuple[float, TraitFieldTypes] | None = None


async def get_trait_field_types() -> TraitFieldTypes:
    """Field types of all known trait versions, for filters.

    Uses the definitions of all installed addon versions, so filters
    work on old trait versions too. Cached in the process for
    `FIELD_TYPES_TTL` seconds.
    """

    global _field_types_cache
    now = time.monotonic()
    if _field_types_cache and now - _field_types_cache[0] < FIELD_TYPES_TTL:
        return _field_types_cache[1]

    result: TraitFieldTypes = {}
    for definition in await get_trait_definitions():
        if definition.version is None:
            continue
        fields = get_definition_fields(definition)
        result.setdefault(definition.versionless_id, {})[definition.version] = {
            name: spec.type for name, spec in fields.items()
        }
    _field_types_cache = (now, result)
    return result


def clear_trait_field_types_cache() -> None:
    global _field_types_cache
    _field_types_cache = None


#
# Project usage
#


class TraitFieldInfo(OPModel):
    name: Annotated[str, Field(description="Field name", example="frame_start")]
    title: Annotated[str, Field(example="Frame Start")]
    type: Annotated[str, Field(example="integer")]
    description: str = ""
    enum: Annotated[list[Any] | None, Field(description="Allowed values")] = None
    versions: Annotated[
        list[int], Field(description="Trait versions having the field")
    ] = Field(default_factory=list)
    count: Annotated[int, Field(description="Representations with a value")] = 0
    synonyms: list[str] = Field(default_factory=list)


class TraitUsage(OPModel):
    id: Annotated[str, Field(description="Versionless trait ID")]
    name: Annotated[str, Field(description="Trait name")]
    description: str = ""
    versions: list[int] = Field(default_factory=list)
    count: Annotated[int, Field(description="Representations with the trait")] = 0
    fields: list[TraitFieldInfo] = Field(default_factory=list)


class ProjectTraitFields(OPModel):
    traits: list[TraitUsage] = Field(default_factory=list)


class TraitFieldValue(OPModel):
    value: Any
    count: int


async def get_project_trait_fields(
    project_name: str, *, use_cache: bool = True
) -> ProjectTraitFields:
    """Traits and trait fields used by representations of a project.

    Only fields with a stored value are listed. Studio settings are not
    applied, see `apply_filtering_settings()`.
    """

    if use_cache:
        cached = await Redis.get_json(USAGE_CACHE_NS, project_name)
        if cached is not None:
            return ProjectTraitFields(**cached)

    trait_counts = await Postgres.fetch(
        f"""
        SELECT trait_id, count(*) AS count
        FROM project_{project_name}.representations r,
        LATERAL unnest(r.trait_ids) trait_id
        GROUP BY 1
        """
    )
    field_counts = await Postgres.fetch(
        f"""
        SELECT t.key AS trait_id, f.key AS field, count(*) AS count
        FROM project_{project_name}.representations r,
        LATERAL jsonb_each(r.trait_fields) t,
        LATERAL jsonb_object_keys(t.value) f(key)
        GROUP BY 1, 2
        """
    )

    definitions: dict[str, TraitDefinition] = {
        d.id: d for d in await get_trait_definitions()
    }

    traits: dict[str, TraitUsage] = {}
    for row in trait_counts:
        trait_id = row["trait_id"]
        match = TRAIT_VERSION_REGEX.search(trait_id)
        if match:
            continue
        traits[trait_id] = TraitUsage(
            id=trait_id,
            name=trait_id.rsplit(".", 1)[-1],
            count=row["count"],
        )
    for row in trait_counts:
        trait_id = row["trait_id"]
        match = TRAIT_VERSION_REGEX.search(trait_id)
        if not match:
            continue
        usage = traits.get(TRAIT_VERSION_REGEX.sub("", trait_id))
        if usage is None:
            continue
        usage.versions.append(int(match[1]))
        definition = definitions.get(trait_id)
        if definition is not None:
            # The newest version names the trait
            usage.name = definition.name
            usage.description = definition.description

    fields: dict[tuple[str, str], TraitFieldInfo] = {}
    for row in sorted(field_counts, key=lambda r: (r["trait_id"], r["field"])):
        trait_id, name = row["trait_id"], row["field"]
        match = TRAIT_VERSION_REGEX.search(trait_id)
        definition = definitions.get(trait_id)
        if not match or definition is None:
            # Without a definition the type is unknown
            continue
        spec = get_definition_fields(definition).get(name)
        if spec is None:
            continue
        versionless_id = definition.versionless_id
        info = fields.get((versionless_id, name))
        if info is None:
            info = TraitFieldInfo(
                name=name,
                title=spec.title,
                type=spec.type,
                description=spec.description,
                enum=spec.enum,
            )
            fields[(versionless_id, name)] = info
        else:
            # Newer versions win
            info.title = spec.title
            info.description = spec.description or info.description
            if spec.enum and info.enum is not None:
                info.enum = [*info.enum, *(v for v in spec.enum if v not in info.enum)]
            else:
                info.enum = None
        info.versions.append(int(match[1]))
        info.count += row["count"]

    for (versionless_id, _), info in fields.items():
        usage = traits.get(versionless_id)
        if usage is not None:
            usage.fields.append(info)

    for usage in traits.values():
        usage.versions.sort()
        usage.fields.sort(key=lambda info: info.title.lower())

    result = ProjectTraitFields(
        traits=sorted(traits.values(), key=lambda usage: usage.name.lower()),
    )
    await Redis.set_json(
        USAGE_CACHE_NS,
        project_name,
        result.model_dump(),
        ttl=USAGE_CACHE_TTL,
    )
    return result


async def get_trait_field_values(
    project_name: str,
    trait_id: str,
    field: str,
    *,
    search: str | None = None,
    limit: int = 50,
) -> list[TraitFieldValue]:
    """The most frequent values of a trait field in a project, with counts.

    A versionless trait id covers all its versions.
    """

    field_types = await get_trait_field_types()
    versionless_id = TRAIT_VERSION_REGEX.sub("", trait_id)
    versions = field_types.get(versionless_id) or {}
    match = TRAIT_VERSION_REGEX.search(trait_id)
    keys = [
        f"{versionless_id}.v{version}"
        for version, fields in versions.items()
        if field in fields and (not match or version == int(match[1]))
    ]
    if not keys:
        raise BadRequestException(f"Unknown trait field: {trait_id}/{field}")
    limit = max(1, min(limit, MAX_VALUES_LIMIT))

    # Lists count each item
    source = """
        LATERAL (SELECT r.trait_fields->k.key->$2::text AS raw) f,
        LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(f.raw) = 'array' THEN f.raw
            ELSE jsonb_build_array(f.raw) END
        ) v(value)
    """
    conditions = ["f.raw IS NOT NULL"]
    args: list[Any] = [keys, field, limit]
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        args.append(f"%{escaped}%")
        conditions.append(f"(v.value #>> '{{}}') ILIKE ${len(args)}")

    rows = await Postgres.fetch(
        f"""
        SELECT v.value AS value, count(*) AS count
        FROM project_{project_name}.representations r,
        LATERAL unnest($1::varchar[]) k(key),
        {source}
        WHERE {" AND ".join(conditions)}
        GROUP BY 1
        ORDER BY 2 DESC, 1
        LIMIT $3
        """,
        *args,
    )
    return [TraitFieldValue(value=row["value"], count=row["count"]) for row in rows]


#
# Studio settings
#


class TraitsFilteringSettings(OPModel):
    exposed_traits: list[str] = Field(default_factory=list)
    exposed_fields: list[str] = Field(default_factory=list)
    synonyms: list[dict[str, str]] = Field(default_factory=list)


async def get_filtering_settings(
    project_name: str, variant: str = "production"
) -> TraitsFilteringSettings | None:
    """`traits_filtering` from the core addon project settings."""

    from ayon_server.addons.library import AddonLibrary

    try:
        addon = await AddonLibrary.getinstance().get_addon_by_variant(
            CORE_ADDON_NAME, variant
        )
        if addon is None:
            return None
        settings = await addon.get_project_settings(project_name, variant=variant)
        section = getattr(settings, "traits_filtering", None)
        if section is None:
            return None
        return TraitsFilteringSettings(**section.dict())
    except Exception:
        log_traceback("Unable to read traits_filtering settings")
        return None


def apply_filtering_settings(
    data: ProjectTraitFields, settings: TraitsFilteringSettings | None
) -> ProjectTraitFields:
    """Keep only the exposed fields and add synonyms.

    Every used trait stays in the list (for "Has Trait"), with only its
    exposed fields. Without settings no field is exposed.
    """

    if settings is None:
        settings = TraitsFilteringSettings()
    exposed_traits = set(settings.exposed_traits)
    exposed_fields = set(settings.exposed_fields)
    synonyms: dict[str, list[str]] = {}
    for item in settings.synonyms:
        synonym, field_key = item.get("name"), item.get("field")
        if synonym and field_key:
            synonyms.setdefault(field_key, []).append(synonym)

    traits: list[TraitUsage] = []
    for usage in data.traits:
        fields: list[TraitFieldInfo] = []
        for info in usage.fields:
            key = f"{usage.id}/{info.name}"
            if usage.id not in exposed_traits and key not in exposed_fields:
                continue
            if key in synonyms:
                info = info.model_copy(
                    update={"synonyms": [*info.synonyms, *synonyms[key]]}
                )
            fields.append(info)
        traits.append(usage.model_copy(update={"fields": fields}))
    return data.model_copy(update={"traits": traits})
