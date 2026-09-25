----------------
-- AYON 1.5.0 --
----------------

-- Add meta column to thumbnails
-- Remove files.author foreign key

DO $$
DECLARE rec RECORD;
BEGIN
    FOR rec IN SELECT DISTINCT nspname FROM pg_namespace WHERE nspname LIKE 'project_%'
    LOOP
        BEGIN
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);
          ALTER TABLE IF EXISTS thumbnails ADD COLUMN IF NOT EXISTS meta JSONB DEFAULT '{}'::JSONB;
          ALTER TABLE IF EXISTS files DROP CONSTRAINT IF EXISTS files_author_fkey;
        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.nspname, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;
