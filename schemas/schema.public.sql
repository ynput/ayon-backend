CREATE TABLE IF NOT EXISTS public.config(
  key VARCHAR NOT NULL PRIMARY KEY,
  value JSONB NOT NULL DEFAULT '{}'::JSONB
);

-- Projects

CREATE TABLE IF NOT EXISTS public.projects(
    name VARCHAR NOT NULL PRIMARY KEY,
    code VARCHAR NOT NULL,
    library BOOLEAN NOT NULL DEFAULT FALSE,
    config JSONB NOT NULL DEFAULT '{}'::JSONB,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS projectname_idx ON public.projects(LOWER(name));
CREATE UNIQUE INDEX IF NOT EXISTS projectcode_idx ON public.projects(LOWER(code));

-- Users

CREATE TABLE IF NOT EXISTS public.users(
    name VARCHAR NOT NULL PRIMARY KEY,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS username_idx ON public.users (LOWER(name));


-- Product types

CREATE TABLE IF NOT EXISTS public.product_types(
  name VARCHAR NOT NULL PRIMARY KEY,
  data JSONB NOT NULL DEFAULT '{}'::JSONB
);


------------
-- Events --
------------

CREATE TABLE IF NOT EXISTS public.events(
  id UUID NOT NULL PRIMARY KEY,
  hash VARCHAR NOT NULL,
  topic VARCHAR NOT NULL,
  sender VARCHAR,
  project_name VARCHAR, -- REFERENCES public.projects(name) ON DELETE CASCADE ON UPDATE CASCADE,
  user_name VARCHAR, -- REFERENCES public.users(name) ON DELETE CASCADE ON UPDATE CASCADE,
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
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  creation_order SERIAL NOT NULL
);

-- TODO: some indices here
CREATE UNIQUE INDEX IF NOT EXISTS unique_event_hash ON events(hash);
CREATE UNIQUE INDEX IF NOT EXISTS unique_creation_order ON events(creation_order);

--------------
-- Settings --
--------------

CREATE TABLE IF NOT EXISTS public.bundles(
  name VARCHAR NOT NULL PRIMARY KEY,
  is_production BOOLEAN NOT NULL DEFAULT FALSE,
  is_staging BOOLEAN NOT NULL DEFAULT FALSE,
  is_archived BOOLEAN NOT NULL DEFAULT FALSE,
  is_dev BOOLEAN NOT NULL DEFAULT FALSE,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- case insensitive name index
CREATE UNIQUE INDEX IF NOT EXISTS bundle_name_idx ON bundles(LOWER(name));
-- allow only one bundle to be production
CREATE UNIQUE INDEX IF NOT EXISTS bundle_production_idx ON bundles(is_production) WHERE is_production;
-- allow only one bundle to be staging
CREATE UNIQUE INDEX IF NOT EXISTS bundle_staging_idx ON bundles(is_staging) WHERE is_staging;



CREATE TABLE IF NOT EXISTS public.sites(
  id VARCHAR NOT NULL PRIMARY KEY,
  data JSONB NOT NULL DEFAULT '{}'::JSONB
);


CREATE TABLE IF NOT EXISTS public.access_groups(
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
  variant VARCHAR NOT NULL DEFAULT 'production',
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (addon_name, addon_version, variant)
);

CREATE TABLE IF NOT EXISTS public.site_settings(
  addon_name VARCHAR NOT NULL,
  addon_version VARCHAR NOT NULL,
  site_id VARCHAR NOT NULL REFERENCES public.sites(id) ON DELETE CASCADE,
  user_name VARCHAR NOT NULL REFERENCES public.users(name) ON DELETE CASCADE,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (addon_name, addon_version, site_id, user_name)
);



CREATE TABLE IF NOT EXISTS public.addon_data(
  addon_name VARCHAR NOT NULL,
  addon_version VARCHAR NOT NULL,
  key VARCHAR NOT NULL,
  data JSONB NOT NULL DEFAULT '{}'::JSONB,
  PRIMARY KEY (addon_name, addon_version, key)
);

CREATE TABLE IF NOT EXISTS public.secrets(
  name VARCHAR NOT NULL PRIMARY KEY,
  value VARCHAR NOT NULL
);


--------------
-- SERVICES --
--------------

CREATE TABLE IF NOT EXISTS public.hosts(
  name VARCHAR NOT NULL PRIMARY KEY,
  last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
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
  last_seen TIMESTAMP,
  data JSONB NOT NULL DEFAULT '{}'::JSONB
);

