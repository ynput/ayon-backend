-- DELETE PUBLIC TABLES

DROP TABLE IF EXISTS public.projects CASCADE;
DROP TABLE IF EXISTS public.users CASCADE;
DROP TABLE IF EXISTS public.access_groups CASCADE;
DROP TABLE IF EXISTS public.attributes CASCADE;
DROP TABLE IF EXISTS public.anatomy_presets CASCADE;
DROP TABLE IF EXISTS public.settings CASCADE;
DROP TABLE IF EXISTS public.addon_versions CASCADE;
DROP TABLE IF EXISTS public.events CASCADE;

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


