-----------------
-- Ayon 1.10.7 --
-----------------

-- Add views tables to projects

DO $$
DECLARE rec RECORD;
BEGIN
  FOR rec IN (
    SELECT nspname FROM pg_namespace ns
    WHERE nspname LIKE 'project_%'
    AND NOT EXISTS (
      SELECT 1 FROM pg_class WHERE relnamespace = ns.oid AND relname = 'views'
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
        working BOOLEAN NOT NULL DEFAULT TRUE,

        access JSONB NOT NULL DEFAULT '{}'::JSONB,
        data JSONB NOT NULL DEFAULT '{}'::JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );

      CREATE UNIQUE INDEX IF NOT EXISTS unique_working_view ON views(view_type, owner) WHERE working;
      CREATE INDEX IF NOT EXISTS view_type_idx ON views(view_type);
      CREATE INDEX IF NOT EXISTS view_owner_idx ON views(owner);

    EXCEPTION
      WHEN OTHERS THEN RAISE WARNING 'Skipping schema % due to error: %', rec.nspname, SQLERRM;
    END;
  END LOOP;
  RETURN;
END $$;



-- Temporary migration to rename personal views to working views
-- This happened during the development, so just a few projects
-- might be affected. This migration will be removed in the future.

-- Only views tables that still need it: ALTER TABLE locks the table
-- even if there is nothing to do (and setup runs on every start)

DO $$
DECLARE rec RECORD;
  BEGIN
  FOR rec IN
    SELECT ns.nspname
    FROM pg_namespace ns
    JOIN pg_class cl ON cl.relnamespace = ns.oid AND cl.relname = 'views'
    WHERE (ns.nspname LIKE 'project_%' OR ns.nspname = 'public')
    AND (
      SELECT count(*) FILTER (WHERE attname = 'personal') = 1
        OR count(*) FILTER (WHERE attname IN ('created_at', 'updated_at')) < 2
      FROM pg_attribute WHERE attrelid = cl.oid AND NOT attisdropped
    )
  LOOP
    EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);
    BEGIN
      ALTER INDEX IF EXISTS unique_personal_view RENAME TO unique_working_view;
      ALTER TABLE views RENAME COLUMN personal to working;
    EXCEPTION
      WHEN OTHERS THEN RAISE NOTICE 'Skipping schema % due to error: %', rec.nspname, SQLERRM;
    END;
    ALTER TABLE IF EXISTS views ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    ALTER TABLE IF EXISTS views ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
  END LOOP;

  RETURN;
END $$;
