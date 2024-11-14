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
             EXECUTE
              'ALTER TABLE IF EXISTS ' || rec.nspname || '.thumbnails ' ||
              'ADD COLUMN IF NOT EXISTS meta JSONB DEFAULT ''{}''::JSONB ';

             EXECUTE
              'ALTER TABLE IF EXISTS ' || rec.nspname || '.files ' ||
              'DROP CONSTRAINT IF EXISTS files_author_fkey';
        END LOOP;
        RETURN;
   END;
   $$ LANGUAGE plpgsql;

SELECT add_meta_column_to_thumbnails();
DROP FUNCTION IF EXISTS add_meta_column_to_thumbnails();


