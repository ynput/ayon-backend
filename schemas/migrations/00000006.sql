----------------
-- Ayon 1.8.2 --
----------------

-- Entity lists for projects

DO $$
DECLARE rec RECORD;
BEGIN
  FOR rec IN (
    SELECT DISTINCT nspname FROM pg_namespace 
    WHERE nspname LIKE 'project_%'
    AND nspname NOT IN (
      SELECT DISTINCT table_schema FROM information_schema.tables 
      WHERE table_name = 'entity_lists'
    )
  )
  LOOP
    BEGIN
      EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);
      RAISE WARNING 'Creating entity list tables in %', rec.nspname;

      CREATE TABLE entity_lists(
        id UUID NOT NULL PRIMARY KEY,
        entity_list_type VARCHAR NOT NULL,
        entity_type VARCHAR NOT NULL,
        label VARCHAR NOT NULL,
        owner VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,

        access JSONB NOT NULL DEFAULT '{}'::JSONB,
        template JSONB NOT NULL DEFAULT '{}'::JSONB,
        attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
        data JSONB NOT NULL DEFAULT '{}'::JSONB,
        tags VARCHAR[] NOT NULL DEFAULT ARRAY[]::VARCHAR[],

        active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        created_by VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,
        updated_by VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,
        creation_order SERIAL NOT NULL
      );

      CREATE UNIQUE INDEX entity_lists_name ON entity_lists (label);
      CREATE INDEX entity_lists_type ON entity_lists (entity_list_type);
      CREATE INDEX entity_list_label ON entity_lists (label);
      CREATE INDEX entity_list_owner ON entity_lists (owner);
      CREATE INDEX entity_list_updated_at ON entity_lists (updated_at);

      CREATE TABLE entity_list_items(
        id UUID NOT NULL PRIMARY KEY,
        entity_list_id UUID NOT NULL REFERENCES entity_lists(id) ON DELETE CASCADE,
        entity_id UUID NOT NULL,

        position INTEGER NOT NULL,
        label VARCHAR,
        attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
        data JSONB NOT NULL DEFAULT '{}'::JSONB,
        tags VARCHAR[] NOT NULL DEFAULT ARRAY[]::VARCHAR[],

        folder_path VARCHAR NOT NULL DEFAULT '',

        created_by VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,
        updated_by VARCHAR REFERENCES public.users(name) ON UPDATE CASCADE ON DELETE SET NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
      );

      CREATE INDEX entity_list_items_entity_list_id ON entity_list_items (entity_list_id);
      CREATE INDEX entity_list_items_entity_id ON entity_list_items (entity_id);
      CREATE INDEX entity_list_items_position ON entity_list_items (position);

      -- Aaaand. done
    EXCEPTION
      WHEN OTHERS THEN RAISE WARNING 'Skipping schema % due to error: %', rec.nspname, SQLERRM;
    END;
  END LOOP;
  RETURN;
END $$;
