-- Projects

CREATE TABLE IF NOT EXISTS public.projects(
    name VARCHAR NOT NULL PRIMARY KEY,
    code VARCHAR NOT NULL,
    library BOOLEAN NOT NULL DEFAULT FALSE,
    config JSONB NOT NULL DEFAULT '{}'::JSONB,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);

CREATE UNIQUE INDEX IF NOT EXISTS projectname_idx ON public.projects (LOWER(name));
CREATE UNIQUE INDEX IF NOT EXISTS projectcode_idx ON public.projects(LOWER(code));

-- Users

CREATE TABLE IF NOT EXISTS public.users(
    name VARCHAR NOT NULL PRIMARY KEY,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);

CREATE UNIQUE INDEX IF NOT EXISTS username_idx ON public.projects (LOWER(name));

-- Roles

CREATE TABLE IF NOT EXISTS public.roles(
    name VARCHAR NOT NULL, 
    project_name VARCHAR NOT NULL DEFAULT '_', 
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (name, project_name)
);

-- Attributes

CREATE TABLE IF NOT EXISTS public.attributes(
    name VARCHAR NOT NULL PRIMARY KEY,
    position INTEGER,
    scope VARCHAR[],
    builtin BOOLEAN NOT NULL DEFAULT FALSE,
    data JSONB NOT NULL DEFAULT '{}':: JSONB
);

--------------
-- Settings --
--------------

CREATE TABLE IF NOT EXISTS public.anatomy_presets(
  name VARCHAR NOT NULL,
  version VARCHAR NOT NULL DEFAULT '4.0.0',
  is_primary BOOLEAN NOT NULL DEFAULT FALSE,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (name, version)
);



CREATE TABLE IF NOT EXISTS public.system_settings(
  setting_group VARCHAR NOT NULL,
  version VARCHAR NOT NULL DEFAULT '4.0.0',
  snapshot_time BIGINT NOT NULL DEFAULT 0,
  staging BOOL NOT NULL DEFAULT FALSE,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (setting_group, version, snapshot_time, staging)
);

CREATE TABLE IF NOT EXISTS public.addon_versions(
  name VARCHAR NOT NULL PRIMARY KEY,
  production_version VARCHAR,
  staging_version VARCHAR
);
