DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'bundles'
        AND column_name = 'is_archived'
    ) THEN
        ALTER TABLE bundles
        ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;


----------------
-- Ayon 0.4.0 --
----------------

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'bundles'
        AND column_name = 'is_dev'
    ) THEN
        ALTER TABLE bundles
        ADD COLUMN is_dev BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;

DROP TABLE IF EXISTS public.addon_versions; -- replaced by bundles
DROP TABLE IF EXISTS public.dependency_packages; -- stored as json files


CREATE OR REPLACE FUNCTION migrate_roles () 
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

SELECT migrate_roles();

-- last, rename public roles to access_groups
ALTER TABLE IF EXISTS public.roles RENAME TO access_groups;

CREATE OR REPLACE FUNCTION migrate_roles () 
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

SELECT migrate_roles();
DROP function IF EXISTS migrate_roles();
