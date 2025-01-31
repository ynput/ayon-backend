----------------
-- AYON 1.3.1 --
----------------

-- Allow renaming users with developmnent bundle

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        JOIN pg_attribute a ON a.attnum = ANY (conkey) AND a.attrelid = conrelid
        JOIN pg_attribute af ON af.attnum = ANY (confkey) AND af.attrelid = confrelid
        WHERE confupdtype = 'c'
          AND contype = 'f'
          AND conrelid = 'public.bundles'::regclass
          AND a.attname = 'active_user'
    ) THEN
        -- Drop the existing foreign key constraint
        ALTER TABLE public.bundles
        DROP CONSTRAINT IF EXISTS bundles_active_user_fkey;

        -- Add a new foreign key constraint with ON UPDATE CASCADE
        ALTER TABLE public.bundles
        ADD CONSTRAINT bundles_active_user_fkey
        FOREIGN KEY (active_user)
        REFERENCES public.users(name)
        ON DELETE SET NULL
        ON UPDATE CASCADE;
    END IF;
END $$;

-- Allow renaming users with site settings

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        JOIN pg_attribute a ON a.attnum = ANY (conkey) AND a.attrelid = conrelid
        JOIN pg_attribute af ON af.attnum = ANY (confkey) AND af.attrelid = confrelid
        WHERE confupdtype = 'c'
          AND contype = 'f'
          AND conrelid = 'public.site_settings'::regclass
          AND a.attname = 'user_name'
    ) THEN
        -- Drop the existing foreign key constraint
        ALTER TABLE public.site_settings
        DROP CONSTRAINT IF EXISTS site_settings_user_name_fkey;

        -- Add a new foreign key constraint with ON UPDATE CASCADE
        ALTER TABLE public.site_settings
        ADD CONSTRAINT site_settings_user_name_fkey
        FOREIGN KEY (user_name)
        REFERENCES public.users(name)
        ON DELETE SET NULL
        ON UPDATE CASCADE;
    END IF;
END $$;

-- Allow renaming users with project.custom_roots and project.project_site_settings set

DO $$
DECLARE
    project_schema TEXT;
    table_name TEXT;
    column_name TEXT;
    constraint_name TEXT;
BEGIN
    FOR project_schema IN
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name LIKE 'project_%'
    LOOP
        FOR table_name, column_name, constraint_name IN
            SELECT
                tc.table_name,
                kcu.column_name,
                tc.constraint_name
            FROM
                information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
            WHERE
                tc.constraint_type = 'FOREIGN KEY'
                AND kcu.table_schema = project_schema
                AND kcu.column_name = 'user_name'
        LOOP
            -- Drop existing foreign key constraint
            EXECUTE format('
                ALTER TABLE %I.%I
                DROP CONSTRAINT %I;
            ', project_schema, table_name, constraint_name);

            -- Add new foreign key constraint with ON UPDATE CASCADE
            EXECUTE format('
                ALTER TABLE %I.%I
                ADD CONSTRAINT %I
                FOREIGN KEY (%I)
                REFERENCES public.users(name)
                ON DELETE CASCADE
                ON UPDATE CASCADE;
            ', project_schema, table_name, constraint_name, column_name);
        END LOOP;
    END LOOP;
END $$;
