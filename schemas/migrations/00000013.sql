--
-- Add active column to exported_attributes
--
-- Stores the inherited "active" state of a folder (false if the folder
-- itself or any of its parents has active = false). Populated by
-- rebuild_inherited_attributes, defaults to true so existing rows
-- are treated as visible until the next rebuild (that runs automatically 
-- after this migration).
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
      AND att.attname = 'active'
    WHERE
      ns.nspname LIKE 'project_%'
      AND cl.relname = 'exported_attributes'
      AND att.attname IS NULL
    LOOP
        BEGIN
          RAISE WARNING 'Adding active to %.%', rec.project_schema, rec.table_name;
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.project_schema);

          ALTER TABLE exported_attributes ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;

        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.project_schema, SQLERRM;
        END;
    END LOOP;
END $$;
