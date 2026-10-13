-- Add bundle modification timestamps, preserving creation time for existing rows.

ALTER TABLE public.bundles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

UPDATE public.bundles
SET updated_at = created_at
WHERE updated_at IS NULL;

ALTER TABLE public.bundles
  ALTER COLUMN updated_at SET DEFAULT NOW(),
  ALTER COLUMN updated_at SET NOT NULL;
