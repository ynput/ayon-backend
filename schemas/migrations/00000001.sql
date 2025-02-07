----------------
-- AYON 1.0.8 --
----------------

CREATE EXTENSION IF NOT EXISTS "pg_trgm";
ALTER EXTENSION pg_trgm SET SCHEMA public;

-- Create activities tables in all project schemas

DO $$
DECLARE rec RECORD;
BEGIN
    FOR rec IN select distinct nspname from pg_namespace where nspname like 'project_%'
    LOOP
        EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);

        CREATE TABLE IF NOT EXISTS activities (
            id UUID PRIMARY KEY,
            activity_type VARCHAR NOT NULL,
            body TEXT NOT NULL,
            data JSONB NOT NULL DEFAULT '{}'::JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            creation_order SERIAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_activity_type ON activities(activity_type);

        CREATE TABLE IF NOT EXISTS activity_references (
            id UUID PRIMARY KEY, -- generate uuid1 in python
            activity_id UUID NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
            reference_type VARCHAR NOT NULL,
            entity_type VARCHAR NOT NULL, -- referenced entity type
            entity_id UUID,      -- referenced entity id
            entity_name VARCHAR, -- if entity_type is user, this will be the user name
            active BOOLEAN NOT NULL DEFAULT TRUE,
            data JSONB NOT NULL DEFAULT '{}'::JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            creation_order SERIAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_activity_id ON activity_references(activity_id);
        CREATE INDEX IF NOT EXISTS idx_activity_entity_id ON activity_references(entity_id);
        CREATE INDEX IF NOT EXISTS idx_activity_reference_created_at
            ON activity_references(created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_reference_unique
            ON activity_references(activity_id, entity_id, entity_name, reference_type);

        CREATE TABLE IF NOT EXISTS entity_paths (
            entity_id UUID PRIMARY KEY,
            entity_type VARCHAR NOT NULL,
            path VARCHAR NOT NULL
        );

        CREATE INDEX IF NOT EXISTS entity_paths_path_idx
            ON entity_paths USING GIN (path public.gin_trgm_ops);

        CREATE TABLE IF NOT EXISTS files (
            id UUID PRIMARY KEY,
            size BIGINT NOT NULL,
            author VARCHAR REFERENCES public.users(name) ON DELETE SET NULL ON UPDATE CASCADE,
            activity_id UUID REFERENCES activities(id) ON DELETE SET NULL,
            data JSONB NOT NULL DEFAULT '{}'::JSONB, -- contains mime, original file name etc
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_files_activity_id ON files(activity_id);

        -- Activity feed view was moved to migration 5 in 1.7.1
        -- We're updating the view to include the tags column
        -- so it doesn't need to be created here just to be dropped and recreated later

    END LOOP;
    RETURN;
END $$;
