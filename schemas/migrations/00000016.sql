--
-- Add documents table to all project schemas
--
-- Stores generic JSON documents saved by addons using the Documents helper.
-- The studio-wide table (public.documents) is created in schema.public.sql.
--

DO $$
DECLARE rec RECORD;
BEGIN
  FOR rec IN
    SELECT ns.nspname AS project_schema
    FROM pg_namespace ns
    LEFT JOIN pg_class cl
      ON cl.relnamespace = ns.oid
      AND cl.relname = 'documents'
    WHERE
      ns.nspname LIKE 'project_%'
      AND cl.oid IS NULL
    LOOP
        BEGIN
          RAISE WARNING 'Adding documents table to %', rec.project_schema;
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.project_schema);

          CREATE TABLE IF NOT EXISTS documents(
            id UUID NOT NULL PRIMARY KEY,
            kind VARCHAR NOT NULL,
            label VARCHAR NOT NULL DEFAULT '',
            data JSONB NOT NULL DEFAULT '{}'::JSONB,
            payload JSONB NOT NULL DEFAULT '{}'::JSONB,
            access JSONB NOT NULL DEFAULT '{}'::JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by VARCHAR,
            updated_by VARCHAR
          );

          CREATE INDEX IF NOT EXISTS document_kind_idx ON documents(kind);
          CREATE INDEX IF NOT EXISTS document_created_by_idx ON documents(created_by);
          CREATE INDEX IF NOT EXISTS document_updated_at_idx ON documents(updated_at);

        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.project_schema, SQLERRM;
        END;
    END LOOP;
END $$;
