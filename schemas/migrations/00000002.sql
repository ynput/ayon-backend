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
        RAISE WARNING 'Fixing bundles.active_user foreign key';
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
        RAISE WARNING 'Fixing public.site_settings foreign key';
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

-- Allow renaming users with project.custom_roots and project.project_site_settings

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
        AND kcu.column_name = 'user_name'
    JOIN pg_constraint AS pc
        ON tc.constraint_name = pc.conname
        AND tc.table_schema = pc.connamespace::regnamespace::text
        AND pc.confupdtype != 'c'
    WHERE
        tc.table_schema LIKE 'project_%'
        AND tc.constraint_type = 'FOREIGN KEY'
LOOP
    RAISE WARNING 'Fixing user_name foreign key on %.%', rec.project_schema, rec.table_name;

    EXECUTE format(
        'ALTER TABLE %I.%I DROP CONSTRAINT %I;',
        rec.project_schema,
        rec.table_name,
        rec.constraint_name
    );

    EXECUTE format(
        'ALTER TABLE %I.%I ADD CONSTRAINT %I
        FOREIGN KEY (%I) REFERENCES public.users(name)
        ON DELETE CASCADE ON UPDATE CASCADE;',
        rec.project_schema,
        rec.table_name,
        rec.constraint_name,
        rec.column_name
    );
END LOOP;
END $$;
