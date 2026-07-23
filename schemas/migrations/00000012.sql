--
-- Add thumbnail_id column to project files
-- 

DO $$
DECLARE rec RECORD;
BEGIN
  FOR rec IN 
    SELECT ns.nspname AS project_schema, cl.relname AS table_name
    FROM pg_namespace ns
    JOIN pg_class cl 
      ON cl.relnamespace = ns.oid
    LEFT JOIN pg_attribute att 
      ON att.attrelid = cl.oid 
      AND att.attname = 'thumbnail_id'
    WHERE 
      ns.nspname LIKE 'project_%'
      AND cl.relname = 'files'
      AND att.attname IS NULL
    LOOP
        BEGIN
          RAISE WARNING 'Adding thumbnail_id to %.%', rec.project_schema, rec.table_name;
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.project_schema);

          ALTER TABLE files ADD COLUMN IF NOT EXISTS thumbnail_id UUID 
            REFERENCES thumbnails(id) ON DELETE SET NULL;
          CREATE INDEX IF NOT EXISTS idx_files_thumbnail_id ON files(thumbnail_id);

        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.project_schema, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;

