----------------
-- AYON 1.6.0 --
----------------

-- In 1.6.0, we are adding a new column `sender_type` to the `events` table.
-- In project schemas, we are adding new columns `traits` to the `representations` table
-- and `tags` to the `activities` table.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_attribute
        WHERE attrelid = to_regclass('public.events')
        AND attname = 'sender_type' AND NOT attisdropped
    ) THEN
        ALTER TABLE IF EXISTS public.events
        ADD COLUMN sender_type VARCHAR;
    END IF;
END $$;


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
        WHERE cl.relnamespace = ns.oid AND cl.relname = 'representations'
        AND NOT EXISTS (
          SELECT 1 FROM pg_attribute
          WHERE attrelid = cl.oid AND attname = 'traits' AND NOT attisdropped
        )
      )
      OR EXISTS (
        SELECT 1 FROM pg_class cl
        WHERE cl.relnamespace = ns.oid AND cl.relname = 'activities'
        AND NOT EXISTS (
          SELECT 1 FROM pg_attribute
          WHERE attrelid = cl.oid AND attname = 'tags' AND NOT attisdropped
        )
      ))
    LOOP
        BEGIN
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);
          -- ALTER TABLE locks the table even if the column exists
          IF NOT EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid = to_regclass(format('%I.representations', rec.nspname))
            AND attname = 'traits' AND NOT attisdropped
          ) THEN
            ALTER TABLE IF EXISTS representations ADD COLUMN IF NOT EXISTS traits JSONB;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid = to_regclass(format('%I.activities', rec.nspname))
            AND attname = 'tags' AND NOT attisdropped
          ) THEN
            ALTER TABLE IF EXISTS activities ADD COLUMN IF NOT EXISTS tags VARCHAR[] NOT NULL DEFAULT ARRAY[]::VARCHAR[];
          END IF;
        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.nspname, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;
