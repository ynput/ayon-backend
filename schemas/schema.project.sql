--------------
-- SETTINGS --
--------------

-- project settings overrides

CREATE TABLE IF NOT EXISTS project_settings(
  version VARCHAR NOT NULL PRIMARY KEY,
  data JSONB NOT NULL DEFAULT '{}'::JSONB
);


----------------
-- AUX TABLES --
----------------

CREATE TABLE thumbnails(
    id UUID NOT NULL PRIMARY KEY,
    mime VARCHAR NOT NULL,
    data bytea NOT NULL
);
 
ALTER TABLE thumbnails ALTER COLUMN data SET STORAGE EXTERNAL;


CREATE TABLE task_types(
    name VARCHAR NOT NULL PRIMARY KEY,
    data JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE folder_types(
    name VARCHAR NOT NULL PRIMARY KEY,
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
    folder_type VARCHAR REFERENCES folder_types(name) ON UPDATE CASCADE ON DELETE SET NULL,
    parent_id UUID REFERENCES folders(id),
    thumbnail_id UUID REFERENCES thumbnails(id) ON DELETE SET NULL,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);

CREATE INDEX folder_parent_idx ON folders(parent_id);

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
    folder_id UUID NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    task_type VARCHAR REFERENCES task_types(name) ON UPDATE CASCADE,
    assignees VARCHAR[] NOT NULL DEFAULT '{}',

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);

CREATE INDEX task_parent_idx ON tasks(folder_id);
CREATE INDEX task_type_idx ON tasks(task_type);
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
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);

CREATE INDEX subset_parent_idx ON subsets(folder_id);
CREATE INDEX subset_family_idx ON subsets(family);
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
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);

CREATE INDEX version_parent_idx ON versions(subset_id);
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

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);

CREATE INDEX representation_parent_idx ON representations(version_id);

-----------
-- FILES --
-----------

-- This table doesn't represent entities, but state of file synchronisation 
-- across sites. Each row represnts a representation on a location
-- so there should be max representations*locations rows and
-- they don't have a python counterpart derived from BaseEntity class.


CREATE TABLE files (
    representation_id UUID NOT NULL REFERENCES representations(id) ON DELETE CASCADE,
    site_name VARCHAR NOT NULL,
    status INTEGER NOT NULL DEFAULT -1,
    priority INTEGER NOT NULL DEFAULT 50,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (representation_id, site_name)
);

CREATE INDEX file_status_idx ON files(status);
CREATE INDEX file_priority_idx ON files(priority desc);

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
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);

CREATE INDEX link_input_idx ON links(input_id);
CREATE INDEX link_output_idx ON links(output_id);
CREATE UNIQUE INDEX link_unique_idx ON links(input_id, output_id, link_name);

--------------
-- SETTINGS --
--------------

CREATE TABLE settings(
  addon_name VARCHAR NOT NULL,
  addon_version VARCHAR NOT NULL,
  staging BOOL NOT NULL DEFAULT FALSE,
  snapshot_time BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (addon_name, addon_version, snapshot_time, staging)
);

CREATE TABLE addon_versions(
  name VARCHAR NOT NULL PRIMARY KEY,
  production_version VARCHAR,
  staging_version VARCHAR
);
