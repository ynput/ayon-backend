-- Use weak references to users in project schemas
-- that allows migrating projects between instances
-- without breaking the foreign keys

-- Warning! This does not cover all cases: custom_roots and project_site_settings
-- still reference users by name. If migration of such projects is needed,
-- these tables should be handled manually.

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
    AND kcu.column_name IN (
      'created_by', 
      'updated_by',  
      'owner'
  )
  JOIN pg_constraint AS pc
    ON tc.constraint_name = pc.conname
    AND tc.table_schema = pc.connamespace::regnamespace::text
  WHERE
    tc.table_schema LIKE 'project_%'
    AND tc.table_name IN (
      'workfiles', 
      'entity_lists', 
      'entity_list_items', 
    )
    AND tc.constraint_type = 'FOREIGN KEY';
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

