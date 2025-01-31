----------------
-- AYON 1.5 --
----------------

-- Add meta column to thumbnails
-- Remove files.author foreign key

CREATE OR REPLACE FUNCTION add_meta_column_to_thumbnails()
   RETURNS VOID  AS
   $$
   DECLARE rec RECORD;
   BEGIN
        FOR rec IN select distinct nspname from pg_namespace where nspname like 'project_%'
        LOOP
            EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);
            ALTER TABLE IF EXISTS thumbnails ADD COLUMN IF NOT EXISTS meta JSONB DEFAULT '{}'::JSONB;
            ALTER TABLE IF EXISTS files DROP CONSTRAINT IF EXISTS files_author_fkey;
        END LOOP;
        RETURN;
   END;
   $$ LANGUAGE plpgsql;

SELECT add_meta_column_to_thumbnails();
DROP FUNCTION IF EXISTS add_meta_column_to_thumbnails();
