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

------------
-- Events --
------------

CREATE TABLE IF NOT EXISTS public.events(
  id UUID NOT NULL PRIMARY KEY,
  hash VARCHAR NOT NULL,
  topic VARCHAR NOT NULL,
  sender VARCHAR,
  project_name VARCHAR REFERENCES public.projects(name)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  user_name VARCHAR REFERENCES public.users(name) 
    ON DELETE CASCADE 
    ON UPDATE CASCADE,
  depends_on UUID REFERENCES public.events(id),
  status VARCHAR NOT NULL
    DEFAULT 'finished'
    CHECK (status IN (
      'pending', 
      'in_progress',
      'finished',
      'failed',
      'aborted',
      'restarted'
    )
  ),
  retries INTEGER NOT NULL DEFAULT 0,
  description TEXT NOT NULL DEFAULT '',
  summary JSONB NOT NULL DEFAULT '{}'::JSONB,
  payload JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at NUMERIC NOT NULL 
    DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
  updated_at NUMERIC NOT NULL 
    DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
  creation_order SERIAL NOT NULL
);

-- TODO: some indices here
CREATE UNIQUE INDEX IF NOT EXISTS unique_event_hash ON events(hash);
CREATE UNIQUE INDEX IF NOT EXISTS unique_creation_order ON events(creation_order);

--------------
-- Settings --
--------------

CREATE TABLE IF NOT EXISTS public.roles(
    name VARCHAR NOT NULL PRIMARY KEY, 
    data JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE IF NOT EXISTS public.attributes(
    name VARCHAR NOT NULL PRIMARY KEY,
    position INTEGER,
    scope VARCHAR[],
    builtin BOOLEAN NOT NULL DEFAULT FALSE,
    data JSONB NOT NULL DEFAULT '{}':: JSONB
);


CREATE TABLE IF NOT EXISTS public.anatomy_presets(
  name VARCHAR NOT NULL,
  version VARCHAR NOT NULL DEFAULT '4.0.0',
  is_primary BOOLEAN NOT NULL DEFAULT FALSE,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (name, version)
);


CREATE TABLE IF NOT EXISTS public.settings(
  addon_name VARCHAR NOT NULL,
  addon_version VARCHAR NOT NULL,
  staging BOOL NOT NULL DEFAULT FALSE,
  snapshot_time BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
  created_by VARCHAR,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (addon_name, addon_version, snapshot_time, staging)
);

CREATE TABLE IF NOT EXISTS public.addon_versions(
  name VARCHAR NOT NULL PRIMARY KEY,
  production_version VARCHAR,
  staging_version VARCHAR
);


CREATE TABLE IF NOT EXISTS public.addon_data(
  addon_name VARCHAR NOT NULL,
  addon_version VARCHAR NOT NULL,
  staging BOOL NOT NULL DEFAULT FALSE,
  key VARCHAR NOT NULL,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (addon_name, addon_version, staging, key)
);


--------------
-- SERVICES --
--------------

CREATE TABLE IF NOT EXISTS public.hosts(
  name VARCHAR NOT NULL PRIMARY KEY,
  last_seen NUMERIC,
  health JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE IF NOT EXISTS public.services(
  name VARCHAR PRIMARY KEY,
  hostname VARCHAR REFERENCES public.hosts(name) ON DELETE CASCADE ON UPDATE CASCADE,
  addon_name VARCHAR NOT NULL,
  addon_version VARCHAR NOT NULL,
  service VARCHAR NOT NULL,
  should_run BOOLEAN NOT NULL DEFAULT TRUE,
  is_running BOOLEAN NOT NULL DEFAULT FALSE,
  last_seen NUMERIC,
  data JSONB NOT NULL DEFAULT '{}'::JSONB
);


CREATE TABLE IF NOT EXISTS public.machines(
  ident VARCHAR NOT NULL PRIMARY KEY,
  data JSONB NOT NULL DEFAULT '{}'::JSONB
);


------------------
-- Dependencies --
------------------

CREATE TABLE IF NOT EXISTS public.dependency_packages(
  name VARCHAR NOT NULL,
  platform VARCHAR NOT NULL,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (name, platform)
);
