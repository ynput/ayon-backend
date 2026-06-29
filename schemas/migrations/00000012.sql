--
-- Add thumbnail_id column to project files
-- 


DO $$
DECLARE rec RECORD;
BEGIN
  FOR rec IN SELECT t.table_schema, t.table_name
    FROM information_schema.tables t
    LEFT JOIN information_schema.columns c
    ON t.table_schema = c.table_schema
    AND t.table_name = c.table_name
    AND c.column_name = 'thumbnail_id'
    WHERE t.table_schema LIKE 'project_%'
    AND t.table_name = 'files'
    GROUP BY t.table_schema, t.table_name
    HAVING COUNT(c.column_name) = 0
    LOOP
        BEGIN
          RAISE WARNING 'Adding thumbnail_id to %.%', rec.table_schema, rec.table_name;
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.table_schema);
          ALTER TABLE files ADD COLUMN IF NOT EXISTS thumbnail_id UUID 
            REFERENCES thumbnails(id) ON DELETE SET NULL;
        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.table_schema, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;

