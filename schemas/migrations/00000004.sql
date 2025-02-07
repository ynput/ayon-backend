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
        FROM information_schema.columns
        WHERE table_name = 'events'
        AND table_schema = 'public'
        AND column_name = 'sender_type'
    ) THEN
        ALTER TABLE IF EXISTS public.events
        ADD COLUMN sender_type VARCHAR;
    END IF;
END $$;


DO $$
DECLARE rec RECORD;
BEGIN
    FOR rec IN SELECT DISTINCT nspname FROM pg_namespace WHERE nspname LIKE 'project_%'
    LOOP
        BEGIN
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);
          ALTER TABLE IF EXISTS representations ADD COLUMN IF NOT EXISTS traits JSONB;
          ALTER TABLE IF EXISTS activities ADD COLUMN IF NOT EXISTS tags VARCHAR[] NOT NULL DEFAULT ARRAY[]::VARCHAR[];
        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.nspname, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;
