-----------------
-- Ayon 1.13.0 --
-----------------

-- 
-- Use weak references to product types
--

DO $$
DECLARE rec RECORD;
BEGIN
FOR rec IN
  SELECT DISTINCT
    tc.table_schema project_schema,
    tc.table_name,
    kcu.column_name,
    tc.constraint_name,
    pc.confupdtype
  FROM
    information_schema.table_constraints AS tc
  JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
    AND kcu.column_name = 'product_type'
  JOIN pg_constraint AS pc
    ON tc.constraint_name = pc.conname
    AND tc.table_schema = pc.connamespace::regnamespace::text
  WHERE
    tc.table_schema LIKE 'project_%'
    AND tc.table_name = 'products'
    AND tc.constraint_type = 'FOREIGN KEY'
  LOOP
    RAISE WARNING 'Removing product type reference from %.%', rec.project_schema, rec.table_name;
    EXECUTE format(
      'ALTER TABLE %I.%I DROP CONSTRAINT %I;',
      rec.project_schema,
      rec.table_name,
      rec.constraint_name
    );
  END LOOP;
END $$;

--
-- Add product_base_type to products table in project schemas if it doesn't exist
--

DO $$
DECLARE rec RECORD;
BEGIN
  FOR rec IN SELECT t.table_schema, t.table_name
    FROM information_schema.tables t
    LEFT JOIN information_schema.columns c
    ON t.table_schema = c.table_schema
    AND t.table_name = c.table_name
    AND c.column_name = 'product_base_type'
    WHERE t.table_schema LIKE 'project_%'
    AND t.table_name = 'products'
    GROUP BY t.table_schema, t.table_name
    HAVING COUNT(c.column_name) = 0
    LOOP
        BEGIN
          RAISE WARNING 'Adding product_base_type to %.%', rec.table_schema, rec.table_name;
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.table_schema);
          EXECUTE 'ALTER TABLE ' || quote_ident(rec.table_name) || ' ADD COLUMN IF NOT EXISTS product_base_type VARCHAR;';
        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.table_schema, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;

--
-- Add created_by and updated_by to project level entities
--

DO $$
DECLARE rec RECORD;
BEGIN
  FOR rec IN SELECT t.table_schema, t.table_name
    FROM information_schema.tables t
    LEFT JOIN information_schema.columns c
    ON t.table_schema = c.table_schema
    AND t.table_name = c.table_name
    AND c.column_name IN ('created_by', 'updated_by')
    WHERE t.table_schema LIKE 'project_%'
    AND t.table_name IN (
      'folders',
      'tasks',
      'products',
      'versions',
      'representations'
    )
    GROUP BY t.table_schema, t.table_name
    HAVING COUNT(c.column_name) < 2
    LOOP
        BEGIN
          RAISE WARNING 'Adding created_by and updated_by to %.%', rec.table_schema, rec.table_name;
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.table_schema);
          EXECUTE 'ALTER TABLE ' || quote_ident(rec.table_name) || ' ADD COLUMN IF NOT EXISTS created_by VARCHAR;';
          EXECUTE 'ALTER TABLE ' || quote_ident(rec.table_name) || ' ADD COLUMN IF NOT EXISTS updated_by VARCHAR;';
        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.table_schema, SQLERRM;
        END;
    END LOOP;
    RETURN;
END $$;

