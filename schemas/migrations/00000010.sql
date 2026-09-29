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
  SELECT
    ns.nspname AS project_schema,
    cl.relname AS table_name,
    con.conname AS constraint_name
  FROM pg_constraint con
  JOIN pg_class cl ON con.conrelid = cl.oid
  JOIN pg_namespace ns ON cl.relnamespace = ns.oid
  JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
  WHERE 
    ns.nspname LIKE 'project_%'
    AND cl.relname = 'products'
    AND att.attname = 'product_type'
    AND con.contype = 'f'

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
  FOR rec IN 
    SELECT ns.nspname AS project_schema, cl.relname AS table_name
    FROM pg_namespace ns
    JOIN pg_class cl 
      ON cl.relnamespace = ns.oid
    LEFT JOIN pg_attribute att 
      ON att.attrelid = cl.oid 
      AND att.attname = 'product_base_type'
    WHERE 
      ns.nspname LIKE 'project_%'
      AND cl.relname = 'products'
      AND att.attname IS NULL
    LOOP
        BEGIN
          RAISE WARNING 'Adding product_base_type to %.%', rec.project_schema, rec.table_name;
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.project_schema);
          EXECUTE 'ALTER TABLE ' || quote_ident(rec.table_name) || ' ADD COLUMN IF NOT EXISTS product_base_type VARCHAR;';
        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.project_schema, SQLERRM;
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

