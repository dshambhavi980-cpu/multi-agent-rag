create or replace function public.resume_agent_run(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_run_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  result public.rag_runs;
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id, null, p_run_id);
  update public.rag_runs
  set status = 'running',
      error = null,
      completed_at = null,
      started_at = now()
  where id = p_run_id
    and workspace_id = p_workspace_id
    and mode = 'agentic'
    and status in ('accepted', 'running', 'failed', 'timed_out')
  returning * into result;
  if result.id is null then
    raise exception 'Agent run is not resumable.' using errcode = '55000';
  end if;
  return to_jsonb(result);
end;
$$;

revoke execute on function public.resume_agent_run(uuid, uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.resume_agent_run(uuid, uuid, uuid)
  to service_role;
