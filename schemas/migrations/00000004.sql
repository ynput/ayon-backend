----------------
-- AYON 1.5.7 --
----------------

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


CREATE OR REPLACE FUNCTION add_traits_column_to_representations()
   RETURNS VOID  AS
   $$
   DECLARE rec RECORD;
   BEGIN
        FOR rec IN select distinct nspname from pg_namespace where nspname like 'project_%'
        LOOP
             EXECUTE
              'ALTER TABLE IF EXISTS ' || rec.nspname || '.representations ' ||
              'ADD COLUMN IF NOT EXISTS traits JSONB';
        END LOOP;
        RETURN;
   END;
   $$ LANGUAGE plpgsql;

SELECT add_traits_column_to_representations();
DROP FUNCTION IF EXISTS add_traits_column_to_representations();
