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
        RAISE WARNING 'Adding sender_type column to events';
        ALTER TABLE IF EXISTS public.events
        ADD COLUMN sender_type VARCHAR;
    END IF;
END $$;


