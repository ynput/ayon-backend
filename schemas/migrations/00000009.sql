-----------------
-- Ayon 1.12.1 --
-----------------

-- Add entity_list_folders table to all project schemas if it doesn't exist
-- and add entity_list_folder_id to entity_lists table that references it

DO $$
DECLARE rec RECORD;
BEGIN
    FOR rec IN SELECT DISTINCT p.nspname FROM pg_namespace p
    LEFT JOIN information_schema.columns c
    ON p.nspname = c.table_schema
    AND c.table_name = 'entity_list_folders'
    WHERE p.nspname LIKE 'project_%'
    AND c.table_name IS NULL
    
    LOOP
        BEGIN
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);

          CREATE TABLE entity_list_folders (
              id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              label VARCHAR NOT NULL,
              position INTEGER NOT NULL DEFAULT 0,
              parent_id UUID REFERENCES entity_list_folders(id) ON DELETE CASCADE,
              owner VARCHAR,
              access JSONB DEFAULT '{}'::JSONB,
              data JSONB DEFAULT '{}'::JSONB
          );

          CREATE UNIQUE INDEX uq_entity_list_folder_parent_label 
            ON entity_list_folders(COALESCE(parent_id::varchar, ''), LOWER(label));

          ALTER TABLE entity_lists ADD COLUMN IF NOT EXISTS 
            entity_list_folder_id UUID 
            REFERENCES entity_list_folders(id) ON DELETE SET NULL; 

        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.nspname, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;

