----------------
-- AYON 1.5.0 --
----------------

-- Add meta column to thumbnails
-- Remove files.author foreign key

DO $$
DECLARE rec RECORD;
BEGIN
    -- Only schemas that need it, so a migrated database costs one query
    FOR rec IN
      SELECT nspname FROM pg_namespace ns
      WHERE nspname LIKE 'project_%'
      AND (
      EXISTS (
        SELECT 1 FROM pg_class cl
        WHERE cl.relnamespace = ns.oid AND cl.relname = 'thumbnails'
        AND NOT EXISTS (
          SELECT 1 FROM pg_attribute
          WHERE attrelid = cl.oid AND attname = 'meta' AND NOT attisdropped
        )
      )
      OR EXISTS (
        SELECT 1 FROM pg_constraint con
        JOIN pg_class cl ON cl.oid = con.conrelid
        WHERE cl.relnamespace = ns.oid AND cl.relname = 'files'
        AND con.conname = 'files_author_fkey'
      ))
    LOOP
        BEGIN
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);
          -- ALTER TABLE locks the table even if there is nothing to do
          IF NOT EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid = to_regclass(format('%I.thumbnails', rec.nspname))
            AND attname = 'meta' AND NOT attisdropped
          ) THEN
            ALTER TABLE IF EXISTS thumbnails ADD COLUMN IF NOT EXISTS meta JSONB DEFAULT '{}'::JSONB;
          END IF;
          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = to_regclass(format('%I.files', rec.nspname))
            AND conname = 'files_author_fkey'
          ) THEN
            ALTER TABLE IF EXISTS files DROP CONSTRAINT IF EXISTS files_author_fkey;
          END IF;
        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.nspname, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;
