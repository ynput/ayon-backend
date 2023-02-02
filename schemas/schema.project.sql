----------------
-- AUX TABLES --
----------------

CREATE TABLE thumbnails(
    id UUID NOT NULL PRIMARY KEY,
    mime VARCHAR NOT NULL,
    data BYTEA NOT NULL,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);
 
ALTER TABLE thumbnails ALTER COLUMN data SET STORAGE EXTERNAL;


CREATE TABLE task_types(
    name VARCHAR NOT NULL PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    data JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE folder_types(
    name VARCHAR NOT NULL PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    data JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE statuses(
    name VARCHAR NOT NULL PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    data JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE tags(
    name VARCHAR NOT NULL PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    data JSONB NOT NULL DEFAULT '{}'::JSONB
);

-------------------
-- BASE ENTITIES --
-------------------


-------------
-- FOLDERS --
-------------

CREATE TABLE folders(
    id UUID NOT NULL PRIMARY KEY,

    name VARCHAR NOT NULL,
    label VARCHAR,
    folder_type VARCHAR NOT NULL REFERENCES folder_types(name) ON UPDATE CASCADE,
    parent_id UUID REFERENCES folders(id),
    thumbnail_id UUID REFERENCES thumbnails(id) ON DELETE SET NULL,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    status VARCHAR NOT NULL REFERENCES statuses(name) ON UPDATE CASCADE,
    tags VARCHAR[] NOT NULL DEFAULT '{}',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    creation_order SERIAL NOT NULL
);

CREATE INDEX folder_parent_idx ON folders(parent_id);
CREATE UNIQUE INDEX folder_creation_order_idx ON folders(creation_order);

-- Two partial indices are used as a workaround for root folders (which have parent_id NULL)

CREATE UNIQUE INDEX folder_unique_name_parent ON folders (parent_id, name) 
    WHERE (active IS TRUE AND parent_id IS NOT NULL);

CREATE UNIQUE INDEX folder_root_unique_name ON folders (name) 
    WHERE (active IS TRUE AND parent_id IS NULL);


-- Hierarchy view
-- Materialized view used as a shorthand to get folder parents/full path

CREATE MATERIALIZED VIEW hierarchy 
AS 
    WITH htable AS (
        WITH RECURSIVE hierarchy AS (
            SELECT id, name, parent_id, 1 as pos, id as base_id
            FROM
                folders
            UNION
                SELECT e.id, e.name, e.parent_id, pos + 1, base_id
                FROM folders e
                INNER JOIN hierarchy s ON s.parent_id = e.id
        ) SELECT
            base_id,
            string_agg(name, '/' ORDER BY pos DESC) as path
        FROM
            hierarchy
        GROUP BY base_id
   )
   SELECT base_id AS id, path FROM htable;

CREATE UNIQUE INDEX hierarchy_id ON hierarchy (id);


CREATE TABLE exported_attributes(
  folder_id UUID NOT NULL PRIMARY KEY REFERENCES folders(id) ON DELETE CASCADE,
  path VARCHAR NOT NULL,
  attrib JSONB NOT NULL DEFAULT '{}'::JSONB
);

-----------
-- TASKS --
-----------

CREATE TABLE tasks(
    id UUID NOT NULL PRIMARY KEY,

    name VARCHAR NOT NULL,
    label VARCHAR,
    folder_id UUID NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    task_type VARCHAR REFERENCES task_types(name) ON UPDATE CASCADE,
    assignees VARCHAR[] NOT NULL DEFAULT '{}',

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR NOT NULL REFERENCES statuses(name) ON UPDATE CASCADE,
    tags VARCHAR[] NOT NULL DEFAULT '{}',
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    creation_order SERIAL NOT NULL
);

CREATE INDEX task_parent_idx ON tasks(folder_id);
CREATE INDEX task_type_idx ON tasks(task_type);
CREATE UNIQUE INDEX task_creation_order_idx ON tasks(creation_order);
CREATE UNIQUE INDEX task_unique_name ON tasks(folder_id, name);

-------------
-- SUBSETS --
-------------

CREATE TABLE subsets(
    id UUID NOT NULL PRIMARY KEY,
    name VARCHAR NOT NULL,

    folder_id UUID NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    family VARCHAR NOT NULL,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR NOT NULL REFERENCES statuses(name) ON UPDATE CASCADE,
    tags VARCHAR[] NOT NULL DEFAULT '{}',
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    creation_order SERIAL NOT NULL
);

CREATE INDEX subset_parent_idx ON subsets(folder_id);
CREATE INDEX subset_family_idx ON subsets(family);
CREATE UNIQUE INDEX subset_creation_order_idx ON subsets(creation_order);
CREATE UNIQUE INDEX subset_unique_name_parent ON subsets (folder_id, name) WHERE (active IS TRUE);

--------------
-- VERSIONS --
--------------

CREATE TABLE versions(
    id UUID NOT NULL PRIMARY KEY,

    version INTEGER NOT NULL,
    subset_id UUID NOT NULL REFERENCES subsets(id) ON DELETE CASCADE,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    thumbnail_id UUID REFERENCES thumbnails(id) ON DELETE SET NULL,
    author VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR NOT NULL REFERENCES statuses(name) ON UPDATE CASCADE,
    tags VARCHAR[] NOT NULL DEFAULT '{}',
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    creation_order SERIAL NOT NULL
);

CREATE INDEX version_parent_idx ON versions(subset_id);
CREATE UNIQUE INDEX version_creation_order_idx ON versions(creation_order);
CREATE UNIQUE INDEX version_unique_version_parent ON versions (subset_id, version) WHERE (active IS TRUE);

-- Version list VIEW
-- Materialized view used as a shorthand to get subset versions

CREATE MATERIALIZED VIEW version_list
AS
    SELECT
        v.subset_id AS subset_id,
        array_agg(v.id ORDER BY v.version ) AS ids, 
        array_agg(v.version ORDER BY v.version ) AS versions
    FROM
        versions AS v
    GROUP BY v.subset_id;

CREATE UNIQUE INDEX version_list_id ON version_list (subset_id);

---------------------
-- REPRESENTATIONS --
---------------------

-- List of files is stored in `data` column ( {"files" : [ ... ]})

CREATE TABLE representations(
    id UUID NOT NULL PRIMARY KEY,
    name VARCHAR NOT NULL,

    version_id UUID NOT NULL REFERENCES versions(id) ON DELETE CASCADE,
    files JSONB NOT NULL DEFAULT '[]'::JSONB,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR NOT NULL REFERENCES statuses(name) ON UPDATE CASCADE,
    tags VARCHAR[] NOT NULL DEFAULT '{}',
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    creation_order SERIAL NOT NULL
);

CREATE INDEX representation_parent_idx ON representations(version_id);
CREATE UNIQUE INDEX representation_creation_order_idx ON representations(creation_order);

---------------
-- WORKFILES --
---------------

CREATE TABLE workfiles(
    id UUID NOT NULL PRIMARY KEY,
    path VARCHAR NOT NULL UNIQUE,
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,

    thumbnail_id UUID REFERENCES thumbnails(id) ON DELETE SET NULL,

    created_by VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,
    updated_by VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR NOT NULL REFERENCES statuses(name) ON UPDATE CASCADE,
    tags VARCHAR[] NOT NULL DEFAULT '{}',
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    creation_order SERIAL NOT NULL
);

-----------
-- LINKS --
-----------

CREATE TABLE link_types(
    name varchar NOT NULL PRIMARY KEY,
    input_type VARCHAR NOT NULL,
    output_type VARCHAR NOT NULL,
    link_type VARCHAR NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE UNIQUE INDEX link_type_unique_idx ON link_types(input_type, output_type, link_type);

CREATE TABLE links (
    id UUID NOT NULL PRIMARY KEY,
    input_id UUID NOT NULL,
    output_id UUID NOT NULL,
    link_name VARCHAR NOT NULL REFERENCES link_types(name) ON DELETE CASCADE,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    creation_order SERIAL NOT NULL
);

CREATE INDEX link_input_idx ON links(input_id);
CREATE INDEX link_output_idx ON links(output_id);
CREATE UNIQUE INDEX link_creation_order_idx ON links(creation_order);
CREATE UNIQUE INDEX link_unique_idx ON links(input_id, output_id, link_name);

--------------
-- SETTINGS --
--------------

-- Project specific overrides of roles and addon settings
-- The table structure is the same as in the public schema

CREATE TABLE IF NOT EXISTS roles(
    name VARCHAR NOT NULL PRIMARY KEY REFERENCES public.roles(name) ON DELETE CASCADE,
    data JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE settings(
  addon_name VARCHAR NOT NULL,
  addon_version VARCHAR NOT NULL,
  variant VARCHAR NOT NULL DEFAULT 'production',
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (addon_name, addon_version, variant)
);

CREATE TABLE project_site_settings(
  addon_name VARCHAR NOT NULL,
  addon_version VARCHAR NOT NULL,
  site_id VARCHAR REFERENCES public.sites(id) ON DELETE CASCADE,
  user_name VARCHAR REFERENCES public.users(name) ON DELETE CASCADE,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (addon_name, addon_version, site_id, user_name)
);

CREATE TABLE addon_versions(
  name VARCHAR NOT NULL PRIMARY KEY,
  production_version VARCHAR,
  staging_version VARCHAR
);

CREATE TABLE IF NOT EXISTS addon_data(
  addon_name VARCHAR NOT NULL,
  addon_version VARCHAR NOT NULL,
  key VARCHAR NOT NULL,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (addon_name, addon_version, key)
);


CREATE TABLE IF NOT EXISTS custom_roots(
  site_id VARCHAR NOT NULL REFERENCES public.sites(id) ON DELETE CASCADE,
  user_name VARCHAR NOT NULL REFERENCES public.users(name) ON DELETE CASCADE,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (site_id, user_name)
);
