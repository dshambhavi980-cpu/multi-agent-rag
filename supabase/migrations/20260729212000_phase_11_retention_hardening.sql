create or replace function public.cleanup_observability_retention()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  deleted_events integer;
  deleted_run_events integer;
  deleted_steps integer;
  deleted_tool_calls integer;
  deleted_evidence integer;
begin
  delete from public.operational_events
  where occurred_at < now() - interval '30 days'
     or run_id in (
       select id from (
         select id, row_number() over (
           partition by workspace_id order by created_at desc
         ) as ordinal
         from public.rag_runs
       ) ranked
       where ranked.ordinal > 50
     );
  get diagnostics deleted_events = row_count;

  delete from public.rag_run_events detail
  where detail.run_id in (
    select run.id from (
      select id, completed_at, row_number() over (
        partition by workspace_id order by created_at desc
      ) as ordinal
      from public.rag_runs
      where status in ('completed', 'failed', 'cancelled', 'timed_out')
    ) run
    where run.completed_at < now() - interval '30 days' or run.ordinal > 50
  );
  get diagnostics deleted_run_events = row_count;

  delete from public.agent_steps detail
  where detail.run_id in (
    select run.id from (
      select id, completed_at, row_number() over (
        partition by workspace_id order by created_at desc
      ) as ordinal
      from public.rag_runs
      where status in ('completed', 'failed', 'cancelled', 'timed_out')
    ) run
    where run.completed_at < now() - interval '30 days' or run.ordinal > 50
  );
  get diagnostics deleted_steps = row_count;

  delete from public.tool_calls detail
  where detail.run_id in (
    select run.id from (
      select id, completed_at, row_number() over (
        partition by workspace_id order by created_at desc
      ) as ordinal
      from public.rag_runs
      where status in ('completed', 'failed', 'cancelled', 'timed_out')
    ) run
    where run.completed_at < now() - interval '30 days' or run.ordinal > 50
  );
  get diagnostics deleted_tool_calls = row_count;

  delete from public.rag_evidence detail
  where detail.run_id in (
    select run.id from (
      select id, completed_at, row_number() over (
        partition by workspace_id order by created_at desc
      ) as ordinal
      from public.rag_runs
      where status in ('completed', 'failed', 'cancelled', 'timed_out')
    ) run
    where run.completed_at < now() - interval '30 days' or run.ordinal > 50
  );
  get diagnostics deleted_evidence = row_count;

  return jsonb_build_object(
    'deleted_events', deleted_events,
    'deleted_run_events', deleted_run_events,
    'deleted_steps', deleted_steps,
    'deleted_tool_calls', deleted_tool_calls,
    'deleted_evidence', deleted_evidence,
    'retention_days', 30
  );
end;
$$;

revoke execute on function public.cleanup_observability_retention()
  from public, anon, authenticated;
grant execute on function public.cleanup_observability_retention()
  to service_role;
