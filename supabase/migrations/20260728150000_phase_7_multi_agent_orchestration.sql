alter table public.rag_runs drop constraint rag_runs_mode;
alter table public.rag_runs
  add constraint rag_runs_mode check (mode in ('simple', 'agentic'));

create table public.agent_steps (
  id uuid primary key,
  run_id uuid not null,
  workspace_id uuid not null,
  step_number integer not null,
  node text not null,
  status text not null,
  summary text not null,
  duration_ms numeric not null,
  created_at timestamptz not null default now(),
  foreign key (run_id, workspace_id)
    references public.rag_runs (id, workspace_id) on delete cascade,
  constraint agent_steps_number check (step_number between 1 and 8),
  constraint agent_steps_node check (
    node in ('supervisor', 'planner', 'retrieval', 'synthesis', 'writer', 'reviewer')
  ),
  constraint agent_steps_status check (status in ('succeeded', 'failed', 'skipped')),
  constraint agent_steps_summary_length check (char_length(summary) between 1 and 500),
  constraint agent_steps_duration check (duration_ms >= 0)
);

create index agent_steps_workspace_run_step_idx
  on public.agent_steps (workspace_id, run_id, step_number, created_at);

create table public.tool_calls (
  id uuid primary key,
  run_id uuid not null,
  workspace_id uuid not null,
  tool_name text not null,
  permission text not null,
  status text not null,
  sanitized_input jsonb not null,
  output_summary jsonb not null,
  duration_ms numeric not null,
  created_at timestamptz not null default now(),
  foreign key (run_id, workspace_id)
    references public.rag_runs (id, workspace_id) on delete cascade,
  constraint tool_calls_name check (tool_name = 'hybrid_document_search'),
  constraint tool_calls_permission check (permission = 'documents:read'),
  constraint tool_calls_status check (status in ('succeeded', 'failed')),
  constraint tool_calls_sanitized_input check (jsonb_typeof(sanitized_input) = 'object'),
  constraint tool_calls_output_summary check (jsonb_typeof(output_summary) = 'object'),
  constraint tool_calls_duration check (duration_ms >= 0)
);

create index tool_calls_workspace_run_created_idx
  on public.tool_calls (workspace_id, run_id, created_at);

create table public.workflow_checkpoints (
  run_id uuid not null,
  workspace_id uuid not null,
  step_number integer not null,
  next_node text not null,
  state jsonb not null,
  checkpoint_version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (run_id, workspace_id),
  foreign key (run_id, workspace_id)
    references public.rag_runs (id, workspace_id) on delete cascade,
  constraint workflow_checkpoints_step check (step_number between 1 and 8),
  constraint workflow_checkpoints_next_node check (
    next_node in ('planner', 'retrieval', 'synthesis', 'writer', 'reviewer', 'complete')
  ),
  constraint workflow_checkpoints_state check (jsonb_typeof(state) = 'object'),
  constraint workflow_checkpoints_version check (checkpoint_version > 0)
);

alter table public.agent_steps enable row level security;
alter table public.tool_calls enable row level security;
alter table public.workflow_checkpoints enable row level security;

revoke all on table public.agent_steps from public, anon, authenticated;
revoke all on table public.tool_calls from public, anon, authenticated;
revoke all on table public.workflow_checkpoints from public, anon, authenticated;

create or replace function public.start_rag_run(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_conversation_id uuid,
  p_content text,
  p_document_ids uuid[],
  p_request_key text,
  p_prompt_version text,
  p_model text,
  p_mode text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  existing_run public.rag_runs;
  input_id uuid;
  run_row public.rag_runs;
  active_agent_runs integer;
begin
  perform app_private.assert_rag_actor(
    p_workspace_id, p_actor_id, p_conversation_id
  );
  if p_mode not in ('simple', 'agentic') then
    raise exception 'Unsupported run mode.' using errcode = '22023';
  end if;
  select * into existing_run
  from public.rag_runs
  where workspace_id = p_workspace_id
    and owner_id = p_actor_id
    and request_key = p_request_key;
  if found then
    return jsonb_build_object(
      'run_id', existing_run.id,
      'message_id', existing_run.input_message_id,
      'status', existing_run.status,
      'events_url', '/v1/runs/' || existing_run.id || '/events'
    );
  end if;
  if p_mode = 'agentic' then
    select count(*) into active_agent_runs
    from public.rag_runs
    where owner_id = p_actor_id
      and mode = 'agentic'
      and status in ('accepted', 'running', 'cancelling');
    if active_agent_runs >= 2 then
      raise exception 'Maximum two concurrent agent runs per user.' using errcode = '55000';
    end if;
  end if;

  insert into public.messages (workspace_id, conversation_id, role, content)
  values (p_workspace_id, p_conversation_id, 'user', trim(p_content))
  returning id into input_id;

  insert into public.rag_runs (
    workspace_id, conversation_id, owner_id, input_message_id,
    request_key, question, document_ids, prompt_version, model, mode
  ) values (
    p_workspace_id, p_conversation_id, p_actor_id, input_id,
    p_request_key, trim(p_content), p_document_ids, p_prompt_version, p_model, p_mode
  ) returning * into run_row;

  update public.conversations
  set updated_at = now(), title = coalesce(title, left(trim(p_content), 80))
  where id = p_conversation_id and workspace_id = p_workspace_id;

  return jsonb_build_object(
    'run_id', run_row.id,
    'message_id', input_id,
    'status', run_row.status,
    'events_url', '/v1/runs/' || run_row.id || '/events'
  );
end;
$$;

create or replace function public.record_agent_step(
  p_step_id uuid,
  p_run_id uuid,
  p_workspace_id uuid,
  p_step_number integer,
  p_node text,
  p_status text,
  p_summary text,
  p_duration_ms numeric
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.agent_steps (
    id, run_id, workspace_id, step_number, node, status, summary, duration_ms
  ) values (
    p_step_id, p_run_id, p_workspace_id, p_step_number, p_node,
    p_status, p_summary, p_duration_ms
  );
  update public.rag_runs
  set current_node = p_node,
      step_count = greatest(step_count, p_step_number),
      status = case when status in ('accepted', 'failed', 'timed_out') then 'running' else status end
  where id = p_run_id and workspace_id = p_workspace_id and mode = 'agentic';
  if not found then
    raise exception 'Agent run not found.' using errcode = 'P0002';
  end if;
end;
$$;

create or replace function public.record_agent_tool_call(
  p_call_id uuid,
  p_run_id uuid,
  p_workspace_id uuid,
  p_tool_name text,
  p_permission text,
  p_status text,
  p_sanitized_input jsonb,
  p_output_summary jsonb,
  p_duration_ms numeric
)
returns void
language sql
security definer
set search_path = ''
as $$
  insert into public.tool_calls (
    id, run_id, workspace_id, tool_name, permission, status,
    sanitized_input, output_summary, duration_ms
  ) values (
    p_call_id, p_run_id, p_workspace_id, p_tool_name, p_permission, p_status,
    p_sanitized_input, p_output_summary, p_duration_ms
  );
$$;

create or replace function public.save_workflow_checkpoint(
  p_run_id uuid,
  p_workspace_id uuid,
  p_step_number integer,
  p_next_node text,
  p_state jsonb
)
returns void
language sql
security definer
set search_path = ''
as $$
  insert into public.workflow_checkpoints (
    run_id, workspace_id, step_number, next_node, state
  ) values (
    p_run_id, p_workspace_id, p_step_number, p_next_node, p_state
  )
  on conflict (run_id, workspace_id) do update
  set step_number = excluded.step_number,
      next_node = excluded.next_node,
      state = excluded.state,
      checkpoint_version = public.workflow_checkpoints.checkpoint_version + 1,
      updated_at = now()
  where excluded.step_number >= public.workflow_checkpoints.step_number;
$$;

create or replace function public.get_workflow_checkpoint(
  p_run_id uuid,
  p_workspace_id uuid
)
returns jsonb
language sql
security definer
set search_path = ''
stable
as $$
  select state
  from public.workflow_checkpoints
  where run_id = p_run_id and workspace_id = p_workspace_id;
$$;

revoke execute on function public.start_rag_run(
  uuid, uuid, uuid, text, uuid[], text, text, text, text
) from public, anon, authenticated;
revoke execute on function public.record_agent_step(
  uuid, uuid, uuid, integer, text, text, text, numeric
) from public, anon, authenticated;
revoke execute on function public.record_agent_tool_call(
  uuid, uuid, uuid, text, text, text, jsonb, jsonb, numeric
) from public, anon, authenticated;
revoke execute on function public.save_workflow_checkpoint(
  uuid, uuid, integer, text, jsonb
) from public, anon, authenticated;
revoke execute on function public.get_workflow_checkpoint(uuid, uuid)
  from public, anon, authenticated;

grant execute on function public.start_rag_run(
  uuid, uuid, uuid, text, uuid[], text, text, text, text
) to service_role;
grant execute on function public.record_agent_step(
  uuid, uuid, uuid, integer, text, text, text, numeric
) to service_role;
grant execute on function public.record_agent_tool_call(
  uuid, uuid, uuid, text, text, text, jsonb, jsonb, numeric
) to service_role;
grant execute on function public.save_workflow_checkpoint(
  uuid, uuid, integer, text, jsonb
) to service_role;
grant execute on function public.get_workflow_checkpoint(uuid, uuid)
  to service_role;
