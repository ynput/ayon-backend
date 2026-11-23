--
-- Trait columns of representations
--
-- Two columns derived from `traits` by a trigger, for filtering:
--   trait_ids    - versioned and versionless ids of the traits present
--   trait_fields - the short scalar fields of each trait, keyed by
--                  versioned trait id (see public.trait_fields_of)
--
-- Filtering on the full `traits` column is slow, because file lists make
-- it large. `trait_fields` leaves them out.
--
-- This migration only adds the functions, the columns (constant defaults,
-- no table rewrite) and the trigger. Filling existing rows and building the
-- indexes would take long on large projects, so the background worker
-- TraitColumnsBackfill does it in small batches and builds the indexes
-- CONCURRENTLY.
--
-- The functions are also in schema.public.sql (fresh installs do not run
-- migrations). Keep both copies the same.
--

CREATE OR REPLACE FUNCTION public.trait_field_indexable(value JSONB)
RETURNS BOOLEAN LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE jsonb_typeof(value)
    WHEN 'number' THEN TRUE
    WHEN 'boolean' THEN TRUE
    WHEN 'string' THEN length(value #>> '{}') <= 64
    WHEN 'array' THEN
      jsonb_array_length(value) BETWEEN 1 AND 32
      AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(value) item
        WHERE NOT (
          jsonb_typeof(item) IN ('number', 'boolean')
          OR (jsonb_typeof(item) = 'string' AND length(item #>> '{}') <= 64)
        )
      )
    ELSE FALSE
  END
$$;

CREATE OR REPLACE FUNCTION public.trait_fields_of(traits JSONB)
RETURNS JSONB LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT COALESCE(jsonb_object_agg(t.key, f.fields), '{}'::JSONB)
  FROM jsonb_each(
    CASE WHEN jsonb_typeof(traits) = 'object' THEN traits ELSE '{}'::JSONB END
  ) t
  CROSS JOIN LATERAL (
    SELECT jsonb_object_agg(v.key, v.value) AS fields
    FROM jsonb_each(
      CASE WHEN jsonb_typeof(t.value) = 'object' THEN t.value ELSE '{}'::JSONB END
    ) v
    WHERE public.trait_field_indexable(v.value)
  ) f
  WHERE f.fields IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION public.trait_ids_of(traits JSONB)
RETURNS VARCHAR[] LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  WITH ids AS (
    SELECT jsonb_object_keys(
      CASE WHEN jsonb_typeof(traits) = 'object' THEN traits ELSE '{}'::JSONB END
    ) AS id
  )
  SELECT COALESCE(array_agg(id ORDER BY id), ARRAY[]::VARCHAR[])
  FROM (
    SELECT id FROM ids
    UNION
    SELECT regexp_replace(id, '\.v[0-9]+$', '') FROM ids
  ) all_ids
$$;

CREATE OR REPLACE FUNCTION public.set_representation_trait_columns()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.trait_ids := public.trait_ids_of(NEW.traits);
  NEW.trait_fields := public.trait_fields_of(NEW.traits);
  RETURN NEW;
END
$$;

DO $$
DECLARE rec RECORD;
BEGIN
  -- Only schemas that need it, so a migrated database costs one query
  FOR rec IN
    SELECT ns.nspname AS project_schema
    FROM pg_namespace ns
    JOIN pg_class cl
      ON cl.relnamespace = ns.oid
      AND cl.relname = 'representations'
    WHERE
      ns.nspname LIKE 'project_%'
      AND NOT EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = cl.oid AND attname = 'trait_fields' AND NOT attisdropped
      )
    LOOP
        BEGIN
          RAISE WARNING 'Adding trait columns to %', rec.project_schema;
          EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.project_schema);

          -- Constant defaults: no table rewrite
          ALTER TABLE representations
            ADD COLUMN IF NOT EXISTS trait_ids VARCHAR[] NOT NULL DEFAULT ARRAY[]::VARCHAR[],
            ADD COLUMN IF NOT EXISTS trait_fields JSONB NOT NULL DEFAULT '{}'::JSONB;

          DROP TRIGGER IF EXISTS representation_trait_columns ON representations;
          CREATE TRIGGER representation_trait_columns
            BEFORE INSERT OR UPDATE OF traits ON representations
            FOR EACH ROW EXECUTE FUNCTION public.set_representation_trait_columns();

          -- Existing rows are filled and indexed by the background worker
          -- (ayon_server/traits/backfill.py), so this migration stays instant.

        EXCEPTION
          WHEN OTHERS THEN
             RAISE WARNING 'Skipping schema % due to error: %', rec.project_schema, SQLERRM;
        END;
    END LOOP;
END $$;
