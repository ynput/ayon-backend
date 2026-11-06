-- Add bundle modification timestamps, preserving creation time for existing rows.

-- Checked first: ALTER TABLE locks the table even if there is nothing to do
-- (and setup runs on every start)

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_attribute
    WHERE attrelid = 'public.bundles'::regclass
    AND attname = 'updated_at' AND attnotnull AND atthasdef AND NOT attisdropped
  ) THEN
    ALTER TABLE public.bundles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

    UPDATE public.bundles
    SET updated_at = created_at
    WHERE updated_at IS NULL;

    ALTER TABLE public.bundles
      ALTER COLUMN updated_at SET DEFAULT NOW(),
      ALTER COLUMN updated_at SET NOT NULL;
  END IF;
END $$;
