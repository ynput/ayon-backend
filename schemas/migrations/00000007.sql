-----------------
-- Ayon 1.10.7 --
-----------------

-- Add views tables to projects

DO $$
DECLARE rec RECORD;
BEGIN
  FOR rec IN (
    SELECT DISTINCT nspname FROM pg_namespace 
    WHERE nspname LIKE 'project_%'
    AND nspname NOT IN (
      SELECT DISTINCT table_schema FROM information_schema.tables 
      WHERE table_name = 'views'
    )
  )
  LOOP
    BEGIN
      EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);
      RAISE WARNING 'Creating views table in %', rec.nspname;

      CREATE TABLE IF NOT EXISTS views(
        id UUID NOT NULL PRIMARY KEY,
        view_type VARCHAR NOT NULL,
        label VARCHAR NOT NULL,
        position INTEGER NOT NULL DEFAULT 0,

        owner VARCHAR,
        visibility VARCHAR NOT NULL DEFAULT 'private' CHECK (visibility IN ('public', 'private')),
        personal BOOLEAN NOT NULL DEFAULT TRUE,

        access JSONB NOT NULL DEFAULT '{}'::JSONB,
        data JSONB NOT NULL DEFAULT '{}'::JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );

      CREATE UNIQUE INDEX IF NOT EXISTS unique_personal_view ON views(view_type, owner) WHERE personal;
      CREATE INDEX IF NOT EXISTS view_type_idx ON views(view_type);
      CREATE INDEX IF NOT EXISTS view_owner_idx ON views(owner);

    EXCEPTION
      WHEN OTHERS THEN RAISE WARNING 'Skipping schema % due to error: %', rec.nspname, SQLERRM;
    END;
  END LOOP;
  RETURN;
END $$;



-- TODO: can be removed in 1.11.0

DO $$
DECLARE rec RECORD;
BEGIN
    FOR rec IN SELECT DISTINCT nspname FROM pg_namespace WHERE nspname LIKE 'project_%'
    LOOP
        BEGIN
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);
          ALTER TABLE IF EXISTS views ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
          ALTER TABLE IF EXISTS views ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.nspname, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;

ALTER TABLE IF EXISTS public.views ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE IF EXISTS public.views ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
