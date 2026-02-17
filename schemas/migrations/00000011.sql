-----------------
-- Ayon 1.14.0 --
-----------------

-- 
-- 1. Ensure index exists on products(product_base_type)
-- 2. Copy product_type value to product_base_type if product_base_type is null
--


DO $$
DECLARE rec RECORD;
BEGIN
    FOR rec IN select distinct nspname from pg_namespace where nspname like 'project_%'
    LOOP

      BEGIN -- split into multiple transactions to avoid one failure blocking all schemas

        EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);

        CREATE INDEX IF NOT EXISTS product_base_type_idx ON products(product_base_type);

        UPDATE products SET product_base_type = product_type
          WHERE product_base_type IS NULL;


        -- TODO. In 1.15.0, we will enable this constraint after ensuring all existing rows are populated.
        -- We leave it commented out for now, to allow server downgrades from 1.14.x to 1.13.x without issues.

        -- ALTER TABLE products
        --   ALTER COLUMN product_base_type SET NOT NULL;


      EXCEPTION
        WHEN OTHERS THEN 
           RAISE WARNING 'Skipping product base types validation in % due to error: %', rec.nspname, SQLERRM;
      END;

    END LOOP;
    RETURN;
END $$;
