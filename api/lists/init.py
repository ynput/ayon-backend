# TODO: Remove before merging. This is a temporary endpoint used during the development
# of entity list feature.  When the final DB structure is ready,
# the queries will be moved to the migration scripts.


from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.lib.postgres import Postgres

from .router import router

queries = [
    "DROP TABLE IF EXISTS entity_list_items",
    "DROP TABLE IF EXISTS entity_lists",
    """
CREATE TABLE entity_lists(
  id UUID NOT NULL PRIMARY KEY,
  list_type VARCHAR NOT NULL,
  label VARCHAR NOT NULL,
  owner VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,
  access JSONB NOT NULL DEFAULT '{}'::JSONB,
  template JSONB NOT NULL DEFAULT '{}'::JSONB,

  attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  tags VARCHAR[] NOT NULL DEFAULT ARRAY[]::VARCHAR[],

  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,
  updated_by VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,
  creation_order SERIAL NOT NULL
);
""",
    """
CREATE TABLE entity_list_items(
  id UUID NOT NULL PRIMARY KEY,
  entity_list_id UUID NOT NULL REFERENCES entity_lists(id) ON DELETE CASCADE,
  entity_type VARCHAR NOT NULL,
  entity_id UUID NOT NULL,
  position INTEGER NOT NULL,

  attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  tags VARCHAR[] NOT NULL DEFAULT ARRAY[]::VARCHAR[],

  created_by VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,
  updated_by VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
""",
]


@router.post("/__initialize__", response_model_exclude_none=True)
async def initialize_entity_lists_for_project(
    user: CurrentUser,
    project_name: ProjectName,
) -> EmptyResponse:
    """
    This endpoint is used during the development of entity list feature.

    When the final DB structure is ready, the queries will be moved to
    the migration scripts.
    """
    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(f"SET LOCAL search_path TO project_{project_name}")
        for query in queries:
            # do not use .format() here because of '{}'::JSONB
            query = query.replace("{project_name}", project_name)
            await conn.execute(query)

    return EmptyResponse()
