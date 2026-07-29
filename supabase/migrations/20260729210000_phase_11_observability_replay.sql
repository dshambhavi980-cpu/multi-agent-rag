alter table public.rag_runs
  add column request_id uuid,
  add column trace_id uuid not null default gen_random_uuid(),
  add column input_tokens integer,
  add column output_tokens integer,
  add column token_usage_source text,
  add column replayed_from_run_id uuid references public.rag_runs (id) on delete set null,
  add column replay_mode text,
  add column replay_reason text;

alter table public.rag_runs
  add constraint rag_runs_token_counts check (
    (input_tokens is null or input_tokens >= 0)
    and (output_tokens is null or output_tokens >= 0)
  ),
  add constraint rag_runs_token_usage_source check (
    token_usage_source is null or token_usage_source in ('provider', 'estimated')
  ),
  add constraint rag_runs_replay_mode check (
    replay_mode is null or replay_mode in ('exact_snapshot', 'current_configuration')
  ),
  add constraint rag_runs_replay_reason_length check (
    replay_reason is null or char_length(replay_reason) between 1 and 500
  );

alter table public.agent_steps
  add column request_id uuid,
  add column trace_id uuid;

alter table public.tool_calls
  add column request_id uuid,
  add column trace_id uuid;

create table public.operational_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  request_id uuid,
  trace_id uuid not null,
  run_id uuid,
  event_type text not null,
  severity text not null default 'info',
  latency_ms numeric,
  attributes jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  foreign key (run_id, workspace_id)
    references public.rag_runs (id, workspace_id) on delete cascade,
  constraint operational_events_type_length
    check (char_length(event_type) between 3 and 80),
  constraint operational_events_severity
    check (severity in ('info', 'warning', 'error')),
  constraint operational_events_latency
    check (latency_ms is null or latency_ms >= 0),
  constraint operational_events_attributes
    check (
      jsonb_typeof(attributes) = 'object'
      and octet_length(attributes::text) <= 4096
    )
);

alter table public.operational_events enable row level security;
revoke all on table public.operational_events from public, anon, authenticated;

create unique index rag_runs_trace_id_idx on public.rag_runs (trace_id);
create index rag_runs_request_id_idx on public.rag_runs (request_id)
  where request_id is not null;
create index rag_runs_replay_source_idx
  on public.rag_runs (workspace_id, replayed_from_run_id)
  where replayed_from_run_id is not null;
create index operational_events_trace_idx
  on public.operational_events (workspace_id, trace_id, occurred_at);
create index operational_events_retention_idx
  on public.operational_events (occurred_at);

create or replace function app_private.inherit_run_correlation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  select run.request_id, run.trace_id
  into new.request_id, new.trace_id
  from public.rag_runs run
  where run.id = new.run_id and run.workspace_id = new.workspace_id;
  return new;
end;
$$;

create trigger agent_steps_inherit_correlation
before insert on public.agent_steps
for each row execute function app_private.inherit_run_correlation();

create trigger tool_calls_inherit_correlation
before insert on public.tool_calls
for each row execute function app_private.inherit_run_correlation();

create or replace function public.attach_rag_run_correlation(
  p_run_id uuid,
  p_workspace_id uuid,
  p_request_id uuid
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.rag_runs
  set request_id = coalesce(request_id, p_request_id)
  where id = p_run_id and workspace_id = p_workspace_id;
  if not found then
    raise exception 'Run not found.' using errcode = 'P0002';
  end if;
end;
$$;

create or replace function public.record_rag_run_telemetry(
  p_run_id uuid,
  p_workspace_id uuid,
  p_input_tokens integer,
  p_output_tokens integer,
  p_token_usage_source text,
  p_timings jsonb
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  run_row public.rag_runs;
begin
  if p_input_tokens < 0 or p_output_tokens < 0
     or p_token_usage_source not in ('provider', 'estimated')
     or jsonb_typeof(p_timings) <> 'object' then
    raise exception 'Invalid telemetry.' using errcode = '22023';
  end if;
  update public.rag_runs
  set input_tokens = p_input_tokens,
      output_tokens = p_output_tokens,
      token_usage_source = p_token_usage_source,
      timings = timings || p_timings
  where id = p_run_id and workspace_id = p_workspace_id
  returning * into run_row;
  if run_row.id is null then
    raise exception 'Run not found.' using errcode = 'P0002';
  end if;
  insert into public.operational_events (
    workspace_id, request_id, trace_id, run_id, event_type, latency_ms, attributes
  ) values (
    p_workspace_id, run_row.request_id, run_row.trace_id, p_run_id,
    'run.telemetry', nullif(p_timings ->> 'total_ms', '')::numeric,
    jsonb_build_object(
      'input_tokens', p_input_tokens,
      'output_tokens', p_output_tokens,
      'token_usage_source', p_token_usage_source,
      'model', run_row.model,
      'mode', run_row.mode
    )
  );
end;
$$;

create or replace function public.get_rag_replay_snapshot(
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
  run_row public.rag_runs;
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id, null, p_run_id);
  select * into strict run_row from public.rag_runs
  where id = p_run_id and workspace_id = p_workspace_id;
  if run_row.status not in ('completed', 'failed', 'cancelled', 'timed_out') then
    raise exception 'Only terminal runs can be replayed.' using errcode = '55000';
  end if;
  return jsonb_build_object(
    'conversation_id', run_row.conversation_id,
    'question', run_row.question,
    'document_ids', run_row.document_ids,
    'mode', run_row.mode,
    'model', run_row.model,
    'prompt_version', run_row.prompt_version
  );
end;
$$;

create or replace function public.mark_rag_run_replay(
  p_run_id uuid,
  p_workspace_id uuid,
  p_source_run_id uuid,
  p_replay_mode text,
  p_reason text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_replay_mode not in ('exact_snapshot', 'current_configuration')
     or char_length(trim(p_reason)) not between 1 and 500 then
    raise exception 'Invalid replay metadata.' using errcode = '22023';
  end if;
  if not exists (
    select 1 from public.rag_runs source
    where source.id = p_source_run_id and source.workspace_id = p_workspace_id
  ) then
    raise exception 'Source run not found.' using errcode = 'P0002';
  end if;
  update public.rag_runs
  set replayed_from_run_id = p_source_run_id,
      replay_mode = p_replay_mode,
      replay_reason = trim(p_reason)
  where id = p_run_id and workspace_id = p_workspace_id;
  if not found then
    raise exception 'Replay run not found.' using errcode = 'P0002';
  end if;
end;
$$;

create or replace function public.get_run_observability_trace(
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
  run_row public.rag_runs;
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id, null, p_run_id);
  select * into strict run_row from public.rag_runs
  where id = p_run_id and workspace_id = p_workspace_id;
  return jsonb_build_object(
    'request_id', run_row.request_id,
    'trace_id', run_row.trace_id,
    'run_id', run_row.id,
    'model', run_row.model,
    'prompt_version', run_row.prompt_version,
    'timings', run_row.timings,
    'input_tokens', run_row.input_tokens,
    'output_tokens', run_row.output_tokens,
    'token_usage_source', run_row.token_usage_source,
    'replayed_from_run_id', run_row.replayed_from_run_id,
    'replay_mode', run_row.replay_mode,
    'error', run_row.error,
    'evidence', coalesce((
      select jsonb_agg(jsonb_build_object(
        'citation_id', evidence.citation_id,
        'document_id', evidence.document_id,
        'label', evidence.label,
        'page', evidence.page,
        'section', evidence.section,
        'quote', left(evidence.quote, 500),
        'semantic_score', evidence.semantic_score,
        'sparse_rank', evidence.sparse_rank,
        'rrf_score', evidence.rrf_score
      ) order by evidence.ordinal)
      from public.rag_evidence evidence
      where evidence.run_id = p_run_id and evidence.workspace_id = p_workspace_id
    ), '[]'::jsonb),
    'events', coalesce((
      select jsonb_agg(jsonb_build_object(
        'event_type', event.event_type,
        'occurred_at', event.occurred_at,
        'latency_ms', event.latency_ms,
        'severity', event.severity,
        'attributes', event.attributes
      ) order by event.occurred_at)
      from public.operational_events event
      where event.run_id = p_run_id and event.workspace_id = p_workspace_id
    ), '[]'::jsonb)
  );
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
  where workspace_id = p_workspace_id and owner_id = p_actor_id
    and created_at >= now() - interval '24 hours';
  return jsonb_build_object(
    'window_hours', 24,
    'total_runs', total_runs,
    'successful_runs', successful_runs,
    'failed_runs', (
      select count(*) from public.rag_runs
      where workspace_id = p_workspace_id and owner_id = p_actor_id
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
      where workspace_id = p_workspace_id and owner_id = p_actor_id
        and timings ? 'total_ms'
        and created_at >= now() - interval '24 hours'
    ), 0),
    'input_tokens', coalesce((
      select sum(input_tokens) from public.rag_runs
      where workspace_id = p_workspace_id and owner_id = p_actor_id
        and created_at >= now() - interval '24 hours'
    ), 0),
    'output_tokens', coalesce((
      select sum(output_tokens) from public.rag_runs
      where workspace_id = p_workspace_id and owner_id = p_actor_id
        and created_at >= now() - interval '24 hours'
    ), 0),
    'active_runs', (
      select count(*) from public.rag_runs
      where workspace_id = p_workspace_id and owner_id = p_actor_id
        and status in ('accepted', 'running', 'awaiting_approval', 'cancelling')
    ),
    'trace_count', (
      select count(*) from public.rag_runs
      where workspace_id = p_workspace_id and owner_id = p_actor_id
        and created_at >= now() - interval '30 days'
    ),
    'trace_limit', 50,
    'retention_days', 30
  );
end;
$$;

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

revoke execute on function public.attach_rag_run_correlation(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.record_rag_run_telemetry(uuid, uuid, integer, integer, text, jsonb)
  from public, anon, authenticated;
revoke execute on function public.get_rag_replay_snapshot(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.mark_rag_run_replay(uuid, uuid, uuid, text, text)
  from public, anon, authenticated;
revoke execute on function public.get_run_observability_trace(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.get_workspace_observability(uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.cleanup_observability_retention()
  from public, anon, authenticated;

grant execute on function public.attach_rag_run_correlation(uuid, uuid, uuid)
  to service_role;
grant execute on function public.record_rag_run_telemetry(uuid, uuid, integer, integer, text, jsonb)
  to service_role;
grant execute on function public.get_rag_replay_snapshot(uuid, uuid, uuid)
  to service_role;
grant execute on function public.mark_rag_run_replay(uuid, uuid, uuid, text, text)
  to service_role;
grant execute on function public.get_run_observability_trace(uuid, uuid, uuid)
  to service_role;
grant execute on function public.get_workspace_observability(uuid, uuid)
  to service_role;
grant execute on function public.cleanup_observability_retention()
  to service_role;
