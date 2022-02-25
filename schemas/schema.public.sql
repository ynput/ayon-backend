-- DELETE PUBLIC TABLES

DROP TABLE IF EXISTS public.projects CASCADE;
DROP TABLE IF EXISTS public.users CASCADE;

-- DELETE PROJECT SCHEMAS

CREATE OR REPLACE FUNCTION drop_all () 
   RETURNS VOID  AS
   $$
   DECLARE rec RECORD; 
   BEGIN
       -- Get all the schemas
        FOR rec IN
        select distinct nspname
         from pg_namespace
         where nspname like 'project_%'  
           LOOP
             EXECUTE 'DROP SCHEMA ' || rec.nspname || ' CASCADE'; 
           END LOOP; 
           RETURN; 
   END;
   $$ LANGUAGE plpgsql;

select drop_all();


-- Projects


CREATE TABLE public.projects(
    name VARCHAR NOT NULL PRIMARY KEY,
    library BOOLEAN NOT NULL DEFAULT FALSE,
    config JSONB NOT NULL DEFAULT '{}'::JSONB,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);

CREATE UNIQUE INDEX projectname_idx ON public.projects (LOWER(name));

-- Users

CREATE TABLE public.users(
    name VARCHAR NOT NULL PRIMARY KEY,

    attrib JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
    updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
);

CREATE UNIQUE INDEX username_idx ON public.projects (LOWER(name));

-- Roles

CREATE TABLE public.roles(
    name VARCHAR NOT NULL, 
    project_name VARCHAR NOT NULL DEFAULT '_', 
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (name, project_name)
);

-- Attributes

CREATE TABLE public.attributes(
    name VARCHAR NOT NULL PRIMARY KEY,
    scope VARCHAR[],
    builtin BOOLEAN NOT NULL DEFAULT FALSE,
    data JSONB NOT NULL DEFAULT '{}':: JSONB
);
