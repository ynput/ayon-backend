--
-- Sync productGroup between product data and attributes
--
-- Product group used to be stored in products.data->'productGroup'.
-- It is now a product attribute, but for backwards compatibility
-- both are kept in sync. Copy the value to whichever side is missing it.
--

DO $$
DECLARE rec RECORD;
BEGIN
  FOR rec IN
    SELECT ns.nspname AS project_schema
    FROM pg_namespace ns
    JOIN pg_class cl
      ON cl.relnamespace = ns.oid
    WHERE
      ns.nspname LIKE 'project_%'
      AND cl.relname = 'products'
    LOOP
        BEGIN
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.project_schema);

          UPDATE products
          SET attrib = attrib || jsonb_build_object('productGroup', data->'productGroup')
          WHERE
            jsonb_typeof(data->'productGroup') = 'string'
            AND NOT attrib ? 'productGroup';

          UPDATE products
          SET data = COALESCE(data, '{}'::jsonb)
            || jsonb_build_object('productGroup', attrib->'productGroup')
          WHERE
            jsonb_typeof(attrib->'productGroup') = 'string'
            AND NOT COALESCE(data, '{}'::jsonb) ? 'productGroup';

        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.project_schema, SQLERRM;
        END;
    END LOOP;
END $$;
