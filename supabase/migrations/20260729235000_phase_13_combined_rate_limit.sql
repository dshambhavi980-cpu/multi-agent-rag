create or replace function public.consume_api_request_limits(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_bucket text,
  p_user_limit integer,
  p_workspace_limit integer,
  p_window_seconds integer default 60
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  user_result jsonb;
  workspace_result jsonb;
begin
  user_result := public.consume_api_rate_limit(
    p_workspace_id, p_actor_id, 'user:' || p_bucket, p_user_limit, p_window_seconds
  );
  workspace_result := public.consume_api_rate_limit(
    p_workspace_id, null, 'workspace:' || p_bucket, p_workspace_limit, p_window_seconds
  );
  return jsonb_build_object(
    'allowed', (user_result ->> 'allowed')::boolean
      and (workspace_result ->> 'allowed')::boolean,
    'retry_after', greatest(
      (user_result ->> 'retry_after')::integer,
      (workspace_result ->> 'retry_after')::integer
    ),
    'user_remaining', (user_result ->> 'remaining')::integer,
    'workspace_remaining', (workspace_result ->> 'remaining')::integer
  );
end;
$$;

revoke all on function public.consume_api_request_limits(uuid, uuid, text, integer, integer, integer)
  from public, anon, authenticated;
grant execute on function public.consume_api_request_limits(uuid, uuid, text, integer, integer, integer)
  to service_role;
