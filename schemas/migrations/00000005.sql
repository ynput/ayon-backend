----------------
-- Ayon 1.7.1 --
----------------

-- We are replacing activity_feed view with a new version that includes tags column.

DO $$
DECLARE rec RECORD;
BEGIN
    FOR rec IN select distinct nspname from pg_namespace where nspname like 'project_%'
    LOOP
        EXECUTE 'SET LOCAL search_path TO ' || quote_ident(rec.nspname);

        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = rec.nspname
            AND table_name = 'activity_feed'
            AND column_name = 'tags'
        ) THEN
            -- Skip if we already have activity_feed view with tags column
            CONTINUE;
        END IF;

        RAISE WARNING 'Updating activity_feed view in %', rec.nspname;

        -- Since we are changing columns, we cannot just replace the view
        -- So we need to drop and re-create it
        DROP VIEW IF EXISTS activity_feed;

        CREATE OR REPLACE VIEW activity_feed AS
            SELECT
            ref.id as reference_id,
            ref.activity_id as activity_id,
            ref.reference_type as reference_type,

            -- what entity we're referencing
            ref.entity_type as entity_type,
            ref.entity_id as entity_id, -- for project level entities and other activities
            ref.entity_name as entity_name, -- for users
            ref_paths.path as entity_path, -- entity hierarchy position

            -- sorting stuff
            ref.created_at,
            ref.updated_at,
            ref.creation_order,

            -- actual activity
            act.activity_type as activity_type,
            act.body as body,
            act.tags as tags,
            act.data as activity_data,
            ref.data as reference_data,
            ref.active as active

            FROM
            activity_references as ref
            INNER JOIN
            activities as act ON ref.activity_id = act.id
            LEFT JOIN
            entity_paths as ref_paths ON ref.entity_id = ref_paths.entity_id;

    END LOOP;
    RETURN;
END $$;
