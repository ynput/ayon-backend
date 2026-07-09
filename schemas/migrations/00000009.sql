-----------------
-- Ayon 1.12.1 --
-----------------

-- Add entity_list_folders table to all project schemas if it doesn't exist
-- and add entity_list_folder_id to entity_lists table that references it

DO $$
DECLARE rec RECORD;
BEGIN
FOR rec IN 
    SELECT ns.nspname AS project_schema
    FROM pg_namespace ns
    JOIN pg_class c 
      ON c.relnamespace = ns.oid
    LEFT JOIN pg_class folders
      ON folders.relnamespace = ns.oid
      AND folders.relname = 'entity_list_folders'
    LEFT JOIN pg_attribute a 
      ON a.attrelid = c.oid 
      AND a.attnum > 0 
      AND a.attname = 'entity_list_folder_id'
    WHERE 
      ns.nspname LIKE 'project_%'
      AND c.relname = 'entity_lists'
      AND (folders.oid IS NULL OR a.attname IS NULL)
    LOOP
        BEGIN
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.project_schema);

          CREATE TABLE IF NOT EXISTS entity_list_folders (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              label VARCHAR NOT NULL,
              position INTEGER NOT NULL DEFAULT 0,
              parent_id UUID REFERENCES entity_list_folders(id) ON DELETE CASCADE,
              owner VARCHAR,
              access JSONB DEFAULT '{}'::JSONB,
              data JSONB DEFAULT '{}'::JSONB
          );

          CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_list_folder_parent_label 
            ON entity_list_folders(COALESCE(parent_id::varchar, ''), LOWER(label));

          ALTER TABLE entity_lists ADD COLUMN IF NOT EXISTS 
            entity_list_folder_id UUID 
            REFERENCES entity_list_folders(id) ON DELETE SET NULL; 

        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.project_schema, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;
