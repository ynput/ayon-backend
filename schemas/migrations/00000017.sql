--
-- Add the entity_search table (project-wide text search) to all project schemas
--
-- The table starts empty, so its indexes are cheap to create.
-- The IndexEntitySearch maintenance task fills it.
--

CREATE EXTENSION IF NOT EXISTS unaccent SCHEMA public;

DO $$
DECLARE rec RECORD;
BEGIN
  FOR rec IN
    SELECT ns.nspname AS project_schema
    FROM pg_namespace ns
    LEFT JOIN pg_class cl
      ON cl.relnamespace = ns.oid
      AND cl.relname = 'entity_search'
    WHERE
      ns.nspname LIKE 'project_%'
      AND cl.oid IS NULL
    LOOP
        BEGIN
          RAISE WARNING 'Adding entity_search table to %', rec.project_schema;
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.project_schema);

          CREATE TABLE IF NOT EXISTS entity_search (
              entity_id UUID PRIMARY KEY,
              entity_type VARCHAR NOT NULL,
              folder_id UUID NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
              task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
              product_id UUID REFERENCES products(id) ON DELETE CASCADE,
              version_id UUID REFERENCES versions(id) ON DELETE CASCADE,
              activity_id UUID GENERATED ALWAYS AS
                  (CASE WHEN entity_type = 'comment' THEN entity_id END) STORED
                  REFERENCES activities(id) ON DELETE CASCADE,
              literals TEXT,
              attributes TEXT,
              search_vector tsvector NOT NULL,
              updated_at TIMESTAMPTZ
          );

          CREATE INDEX IF NOT EXISTS entity_search_vector_idx ON entity_search USING gin(search_vector);
          CREATE INDEX IF NOT EXISTS entity_search_literals_idx ON entity_search
              USING gin(literals public.gin_trgm_ops);
          CREATE INDEX IF NOT EXISTS entity_search_attributes_idx ON entity_search
              USING gin(attributes public.gin_trgm_ops);
          CREATE INDEX IF NOT EXISTS entity_search_folder_idx ON entity_search(folder_id);
          CREATE INDEX IF NOT EXISTS entity_search_task_idx ON entity_search(task_id)
              WHERE task_id IS NOT NULL;
          CREATE INDEX IF NOT EXISTS entity_search_product_idx ON entity_search(product_id)
              WHERE product_id IS NOT NULL;
          CREATE INDEX IF NOT EXISTS entity_search_version_idx ON entity_search(version_id)
              WHERE version_id IS NOT NULL;
          CREATE INDEX IF NOT EXISTS entity_search_activity_idx ON entity_search(activity_id)
              WHERE activity_id IS NOT NULL;

        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.project_schema, SQLERRM;
        END;
    END LOOP;
END $$;
