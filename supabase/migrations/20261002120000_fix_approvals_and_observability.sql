create or replace function app_private.expire_approval_requests(p_workspace_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.approval_requests
  set escalation_level = least(
        5,
        greatest(
          escalation_level,
          floor(extract(epoch from (now() - created_at)) / 3600)::integer
        )
      )
  where workspace_id = p_workspace_id
    and status = 'pending'
    and created_at < now() - interval '1 hour';

  with expired as (
    update public.approval_requests
    set status = 'expired', decided_at = now(),
        reviewer_comment = 'The approval window expired without a decision.'
    where workspace_id = p_workspace_id
      and status = 'pending'
      and expires_at <= now()
    returning run_id
  )
  update public.rag_runs run
  set status = 'failed',
      current_node = 'approval',
      error = jsonb_build_object(
        'code', 'APPROVAL_EXPIRED',
        'detail', 'The workflow stopped because its approval request expired.',
        'retryable', true
      ),
      completed_at = now()
  where run.workspace_id = p_workspace_id
    and run.id in (select run_id from expired);
end;
$$;

create or replace function public.get_workspace_observability(
  p_workspace_id uuid,
  p_actor_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  total_runs bigint;
  successful_runs bigint;
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id);
  select count(*), count(*) filter (where status = 'completed')
  into total_runs, successful_runs
  from public.rag_runs
  where workspace_id = p_workspace_id
    and created_at >= now() - interval '24 hours';
  return jsonb_build_object(
    'window_hours', 24,
    'total_runs', total_runs,
    'successful_runs', successful_runs,
    'failed_runs', (
      select count(*) from public.rag_runs
      where workspace_id = p_workspace_id
        and status in ('failed', 'timed_out')
        and created_at >= now() - interval '24 hours'
    ),
    'success_rate', case when total_runs = 0 then 1
      else round(successful_runs::numeric / total_runs, 4) end,
    'p95_latency_ms', coalesce((
      select percentile_cont(0.95) within group (
        order by (timings ->> 'total_ms')::numeric
      )
      from public.rag_runs
      where workspace_id = p_workspace_id
        and timings ? 'total_ms'
        and created_at >= now() - interval '24 hours'
    ), 0),
    'input_tokens', coalesce((
      select sum(input_tokens) from public.rag_runs
      where workspace_id = p_workspace_id
        and created_at >= now() - interval '24 hours'
    ), 0),
    'output_tokens', coalesce((
      select sum(output_tokens) from public.rag_runs
      where workspace_id = p_workspace_id
        and created_at >= now() - interval '24 hours'
    ), 0),
    'active_runs', (
      select count(*) from public.rag_runs
      where workspace_id = p_workspace_id
        and status in ('accepted', 'running', 'awaiting_approval', 'cancelling')
    ),
    'trace_count', (
      select count(*) from public.rag_runs
      where workspace_id = p_workspace_id
        and created_at >= now() - interval '30 days'
    ),
    'trace_limit', 50,
    'retention_days', 30
  );
end;
$$;

revoke execute on function public.get_workspace_observability(uuid, uuid) from public;
grant execute on function public.get_workspace_observability(uuid, uuid) to authenticated;
