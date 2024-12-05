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


CREATE OR REPLACE FUNCTION add_new_columns()
   RETURNS VOID  AS
   $$
   DECLARE rec RECORD;
   BEGIN
        FOR rec IN select distinct nspname from pg_namespace where nspname like 'project_%'
        LOOP
             EXECUTE
              'ALTER TABLE IF EXISTS ' || rec.nspname || '.representations ' ||
              'ADD COLUMN IF NOT EXISTS traits JSONB';

             EXECUTE
              'ALTER TABLE IF EXISTS ' || rec.nspname || '.activities ' ||
              'ADD COLUMN IF NOT EXISTS tags VARCHAR[] NOT NULL DEFAULT ARRAY[]::VARCHAR[]';
        END LOOP;
        RETURN;
   END;
   $$ LANGUAGE plpgsql;

SELECT add_new_columns();
DROP FUNCTION IF EXISTS add_new_columns();
