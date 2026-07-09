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
    SELECT ns.nspname AS project_schema,
           c.relname AS table_name,
           con.conname AS constraint_name,
           a.attname AS column_name
    FROM pg_constraint con
    JOIN pg_class c ON con.conrelid = c.oid
    JOIN pg_namespace ns ON c.relnamespace = ns.oid
    JOIN pg_attribute a ON a.attnum = ANY (con.conkey) AND a.attrelid = c.oid
    WHERE con.contype = 'f'
      AND con.confupdtype != 'c'
      AND a.attname = 'user_name'
      AND ns.nspname LIKE 'project_%'
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
