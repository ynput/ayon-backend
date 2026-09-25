-- Use weak references to users in project schemas
-- that allows migrating projects between instances
-- without breaking the foreign keys


DO $$
DECLARE rec RECORD;
BEGIN
FOR rec IN
  SELECT DISTINCT
    ns.nspname AS project_schema,
    cl.relname AS table_name,
    con.conname AS constraint_name
  FROM pg_constraint con
  JOIN pg_class cl ON con.conrelid = cl.oid
  JOIN pg_namespace ns ON cl.relnamespace = ns.oid
  JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
  WHERE 
    ns.nspname LIKE 'project_%'
    AND cl.relname IN ('workfiles', 'entity_lists', 'entity_list_items', 'project_site_settings', 'custom_roots')
    AND att.attname IN ('created_by', 'updated_by', 'owner', 'user_name', 'site_id')
    AND con.contype = 'f'
LOOP
  RAISE WARNING 'Removing users references from %.%', rec.project_schema, rec.table_name;

  EXECUTE format(
    'ALTER TABLE %I.%I DROP CONSTRAINT %I;',
    rec.project_schema,
    rec.table_name,
    rec.constraint_name
  );
END LOOP;
END $$;
