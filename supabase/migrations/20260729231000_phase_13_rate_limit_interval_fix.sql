create or replace function public.consume_api_rate_limit(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_bucket text,
  p_limit integer,
  p_window_seconds integer default 60
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_time timestamptz := clock_timestamp();
  current_window timestamptz;
  current_count integer;
  retry_after integer;
begin
  if p_limit < 1 or p_window_seconds < 1 or p_window_seconds > 3600 then
    raise exception 'invalid rate limit configuration' using errcode = '22023';
  end if;
  if not exists (select 1 from public.workspaces where id = p_workspace_id) then
    raise exception 'workspace not found' using errcode = 'P0002';
  end if;

  current_window := to_timestamp(
    floor(extract(epoch from current_time) / p_window_seconds) * p_window_seconds
  );

  insert into app_private.api_rate_limits (
    workspace_id, actor_key, bucket, window_start, request_count, expires_at
  ) values (
    p_workspace_id,
    coalesce(p_actor_id::text, '*'),
    p_bucket,
    current_window,
    1,
    current_window + make_interval(secs => p_window_seconds * 2)
  )
  on conflict (workspace_id, actor_key, bucket, window_start)
  do update set request_count = app_private.api_rate_limits.request_count + 1
  returning request_count into current_count;

  retry_after := greatest(
    1,
    ceil(extract(epoch from (
      current_window + make_interval(secs => p_window_seconds) - current_time
    )))::integer
  );
  return jsonb_build_object(
    'allowed', current_count <= p_limit,
    'remaining', greatest(p_limit - current_count, 0),
    'retry_after', retry_after,
    'limit', p_limit
  );
end;
$$;

revoke all on function public.consume_api_rate_limit(uuid, uuid, text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.consume_api_rate_limit(uuid, uuid, text, integer, integer)
  to service_role;
