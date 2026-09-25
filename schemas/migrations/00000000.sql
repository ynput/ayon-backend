-- This migration will never be triggered autmatically 
-- As it handles migration from very early beta versions
-- of Ayon. It is here for reference only. If a migration
-- from a version older than 0.3.1 is needed, it should be
-- done manually.


----------------
-- AYON 0.3.1 --
----------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'bundles'
        AND column_name = 'is_archived'
    ) THEN
        ALTER TABLE IF EXISTS bundles
        ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;


----------------
-- AYON 0.4.0 --
----------------

-- Add is_dev column to bundles
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'bundles'
        AND column_name = 'is_dev'
    ) THEN
        ALTER TABLE IF EXISTS bundles
        ADD COLUMN is_dev BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;

DROP TABLE IF EXISTS public.addon_versions; -- replaced by bundles
DROP TABLE IF EXISTS public.dependency_packages; -- stored as json files


-- Delete project-level roles. They are hard to migrate,
-- so users will have to re-create them (collateral damage, sorry)
CREATE OR REPLACE FUNCTION delete_project_roles ()
   RETURNS VOID  AS
   $$
   DECLARE rec RECORD;
   BEGIN
       -- Get all the schemas
        FOR rec IN
        select distinct nspname
         from pg_namespace
         where nspname like 'project_%'
           LOOP
             EXECUTE 'DROP TABLE IF EXISTS ' || rec.nspname || '.roles';
           END LOOP;
           RETURN;
   END;
   $$ LANGUAGE plpgsql;

SELECT delete_project_roles();
DROP FUNCTION IF EXISTS delete_project_roles();

-- Rename roles table to access_groups
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'access_groups') THEN
    ALTER TABLE IF EXISTS public.roles RENAME TO access_groups;
  ELSE
    DROP TABLE IF EXISTS public.roles;
  END IF;
END $$;

-- Create access_groups table in all project schemas
CREATE OR REPLACE FUNCTION create_access_groups_in_projects ()
   RETURNS VOID  AS
   $$
   DECLARE rec RECORD;
   BEGIN
        FOR rec IN select distinct nspname from pg_namespace where nspname like 'project_%'
        LOOP
             EXECUTE 'CREATE TABLE IF NOT EXISTS '
            || rec.nspname ||
            '.access_groups(name VARCHAR PRIMARY KEY REFERENCES public.access_groups(name), data JSONB NOT NULL DEFAULT ''{}''::JSONB)';
        END LOOP;
        RETURN;
   END;
   $$ LANGUAGE plpgsql;

SELECT create_access_groups_in_projects();
DROP FUNCTION IF EXISTS create_access_groups_in_projects();


----------------
-- AYON 0.4.8 --
----------------

-- Add is_dev column to bundles
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'bundles'
        AND column_name = 'active_user'
    ) THEN
        ALTER TABLE IF EXISTS bundles
        ADD COLUMN active_user VARCHAR REFERENCES public.users(name) ON DELETE SET NULL;

    END IF;
END $$;

-- Check again for the active_user column, because it might have been created in the
-- previous step.
-- But if bundle table still does not exist, let the public.schema.sql create it later
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'bundles'
        AND column_name = 'active_user'
    ) THEN
        CREATE UNIQUE INDEX IF NOT EXISTS bundle_active_user_idx
        ON public.bundles(active_user) WHERE (active_user IS NOT NULL);
    END IF;
END $$;


---------------
-- AYON 0.6 --
---------------

-- To every project project schema, add thumbnail_id column to tasks table
-- and create a foreign key constraint to the thumbnails table

CREATE OR REPLACE FUNCTION add_thumbnail_id_to_tasks ()
   RETURNS VOID  AS
   $$
   DECLARE rec RECORD;
   BEGIN
        FOR rec IN select distinct nspname from pg_namespace where nspname like 'project_%'
        LOOP
             EXECUTE
              'ALTER TABLE IF EXISTS ' || rec.nspname || '.tasks ' ||
              'ADD COLUMN IF NOT EXISTS thumbnail_id UUID ' ||
              'REFERENCES ' || rec.nspname || '.thumbnails(id) ON DELETE SET NULL';
        END LOOP;
        RETURN;
   END;
   $$ LANGUAGE plpgsql;

SELECT add_thumbnail_id_to_tasks();
DROP FUNCTION IF EXISTS add_thumbnail_id_to_tasks();

-------------------
-- AYON 1.0.0-RC --
-------------------

-- Copy siteId to instanceId, if instanceId does not exist
-- (this is a one-time migration)


DO $$
BEGIN
    -- Check if the 'config' table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'config') THEN

        INSERT INTO config (key, value)
        SELECT 'instanceId', value
        FROM config
        WHERE key = 'siteId'
        AND NOT EXISTS (
            SELECT 1
            FROM config
            WHERE key = 'instanceId'
        );
    END IF;
END $$;

--------------------
-- AYON 1.0.0-RC5 --
--------------------

-- refactor links

CREATE OR REPLACE FUNCTION refactor_links() RETURNS VOID  AS
$$
DECLARE rec RECORD;
BEGIN
  FOR rec IN select distinct nspname from pg_namespace where nspname like 'project_%'
  LOOP
    IF NOT EXISTS(
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = rec.nspname
      AND table_name = 'links'
      AND column_name = 'name'
    )
    THEN
      -- project links table does not have name column, so we need to create it
      -- and do some data migration
      RAISE WARNING 'Refactoring links in %', rec.nspname;
      EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);

      ALTER TABLE IF EXISTS links ADD COLUMN name VARCHAR;
      ALTER TABLE links RENAME COLUMN link_name TO link_type;
      ALTER TABLE links ADD COLUMN author VARCHAR NULL;
      UPDATE links SET author = data->>'author';

      DROP INDEX link_unique_idx;
    END IF;
  END LOOP;
  RETURN;
END;
$$ LANGUAGE plpgsql;

SELECT refactor_links();
DROP FUNCTION IF EXISTS refactor_links();

