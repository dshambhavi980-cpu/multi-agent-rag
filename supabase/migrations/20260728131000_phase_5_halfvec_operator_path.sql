alter function public.hybrid_search(
  uuid, uuid, uuid, text, text, text, jsonb, boolean, text, integer, integer,
  integer, numeric, numeric, numeric, uuid[], timestamptz, timestamptz,
  text[], text[], integer, jsonb
) set search_path = pg_catalog, extensions;
