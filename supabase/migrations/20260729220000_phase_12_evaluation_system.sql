create table public.evaluation_runs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  suite text not null,
  suite_version integer not null,
  variants text[] not null,
  status text not null default 'queued',
  case_count integer not null,
  request_key text not null,
  metrics jsonb not null default '{}'::jsonb,
  gate_passed boolean,
  gate_failures text[] not null default '{}',
  error jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (workspace_id, owner_id, request_key),
  constraint evaluation_runs_suite_length check (char_length(suite) between 1 and 100),
  constraint evaluation_runs_version check (suite_version > 0),
  constraint evaluation_runs_variants check (
    cardinality(variants) between 1 and 5
    and variants <@ array[
      'keyword_only', 'dense_only', 'hybrid', 'simple_rag', 'agentic'
    ]::text[]
  ),
  constraint evaluation_runs_status check (
    status in ('queued', 'running', 'completed', 'failed', 'cancelled')
  ),
  constraint evaluation_runs_case_count check (case_count between 1 and 50),
  constraint evaluation_runs_key_length check (char_length(request_key) between 16 and 128),
  constraint evaluation_runs_metrics_object check (jsonb_typeof(metrics) = 'object'),
  constraint evaluation_runs_error_object check (
    error is null or jsonb_typeof(error) = 'object'
  )
);

create table public.evaluation_results (
  id uuid primary key default gen_random_uuid(),
  evaluation_id uuid not null references public.evaluation_runs (id) on delete cascade,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  case_id text not null,
  category text not null,
  variant text not null,
  status text not null,
  metrics jsonb not null default '{}'::jsonb,
  latency_ms numeric not null default 0,
  model_calls integer not null default 0,
  prompt_tokens integer not null default 0,
  output_tokens integer not null default 0,
  failure_code text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (evaluation_id, case_id, variant),
  constraint evaluation_results_case_length check (char_length(case_id) between 3 and 100),
  constraint evaluation_results_category check (
    category in (
      'lookup', 'synthesis', 'conflicting_evidence',
      'missing_evidence', 'prompt_injection'
    )
  ),
  constraint evaluation_results_variant check (
    variant in ('keyword_only', 'dense_only', 'hybrid', 'simple_rag', 'agentic')
  ),
  constraint evaluation_results_status check (status in ('passed', 'failed', 'error')),
  constraint evaluation_results_metrics_object check (jsonb_typeof(metrics) = 'object'),
  constraint evaluation_results_nonnegative check (
    latency_ms >= 0 and model_calls >= 0
    and prompt_tokens >= 0 and output_tokens >= 0
  ),
  constraint evaluation_results_details_object check (jsonb_typeof(details) = 'object')
);

create index evaluation_runs_workspace_created_idx
  on public.evaluation_runs (workspace_id, owner_id, created_at desc);
create index evaluation_runs_active_idx
  on public.evaluation_runs (owner_id, created_at)
  where status in ('queued', 'running');
create index evaluation_results_run_idx
  on public.evaluation_results (evaluation_id, case_id, variant);

alter table public.evaluation_runs enable row level security;
alter table public.evaluation_results enable row level security;
revoke all on table public.evaluation_runs from public, anon, authenticated;
revoke all on table public.evaluation_results from public, anon, authenticated;

create or replace function public.create_evaluation_run(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_suite text,
  p_suite_version integer,
  p_variants text[],
  p_case_count integer,
  p_request_key text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  existing public.evaluation_runs;
  created public.evaluation_runs;
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id);
  select * into existing from public.evaluation_runs
  where workspace_id = p_workspace_id
    and owner_id = p_actor_id
    and request_key = p_request_key;
  if found then
    return to_jsonb(existing) || jsonb_build_object('results', '[]'::jsonb);
  end if;
  if exists (
    select 1 from public.evaluation_runs
    where owner_id = p_actor_id and status in ('queued', 'running')
  ) then
    raise exception 'An evaluation is already running.' using errcode = '55000';
  end if;
  insert into public.evaluation_runs (
    workspace_id, owner_id, suite, suite_version, variants, case_count, request_key
  ) values (
    p_workspace_id, p_actor_id, p_suite, p_suite_version,
    p_variants, p_case_count, p_request_key
  ) returning * into created;
  return to_jsonb(created) || jsonb_build_object('results', '[]'::jsonb);
end;
$$;

create or replace function public.start_evaluation_run(
  p_evaluation_id uuid,
  p_workspace_id uuid
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.evaluation_runs
  set status = 'running', started_at = coalesce(started_at, now())
  where id = p_evaluation_id and workspace_id = p_workspace_id
    and status in ('queued', 'running');
  if not found then
    raise exception 'Evaluation run not found.' using errcode = 'P0002';
  end if;
end;
$$;

create or replace function public.record_evaluation_result(
  p_evaluation_id uuid,
  p_workspace_id uuid,
  p_case_id text,
  p_category text,
  p_variant text,
  p_status text,
  p_metrics jsonb,
  p_latency_ms numeric,
  p_model_calls integer,
  p_prompt_tokens integer,
  p_output_tokens integer,
  p_failure_code text,
  p_details jsonb
)
returns void
language sql
security definer
set search_path = ''
as $$
  insert into public.evaluation_results (
    evaluation_id, workspace_id, case_id, category, variant, status,
    metrics, latency_ms, model_calls, prompt_tokens, output_tokens,
    failure_code, details
  ) values (
    p_evaluation_id, p_workspace_id, p_case_id, p_category, p_variant, p_status,
    p_metrics, p_latency_ms, p_model_calls, p_prompt_tokens, p_output_tokens,
    p_failure_code, p_details
  )
  on conflict (evaluation_id, case_id, variant) do update
  set status = excluded.status,
      metrics = excluded.metrics,
      latency_ms = excluded.latency_ms,
      model_calls = excluded.model_calls,
      prompt_tokens = excluded.prompt_tokens,
      output_tokens = excluded.output_tokens,
      failure_code = excluded.failure_code,
      details = excluded.details,
      created_at = now();
$$;

create or replace function public.complete_evaluation_run(
  p_evaluation_id uuid,
  p_workspace_id uuid,
  p_metrics jsonb,
  p_gate_passed boolean,
  p_gate_failures text[],
  p_error jsonb default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  completed public.evaluation_runs;
begin
  update public.evaluation_runs
  set status = case when p_error is null then 'completed' else 'failed' end,
      metrics = p_metrics,
      gate_passed = p_gate_passed,
      gate_failures = p_gate_failures,
      error = p_error,
      completed_at = now()
  where id = p_evaluation_id and workspace_id = p_workspace_id
  returning * into completed;
  if completed.id is null then
    raise exception 'Evaluation run not found.' using errcode = 'P0002';
  end if;
  return to_jsonb(completed) || jsonb_build_object('results', '[]'::jsonb);
end;
$$;

create or replace function public.list_evaluation_runs(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_limit integer default 25
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id);
  return jsonb_build_object(
    'items', coalesce((
      select jsonb_agg(
        (to_jsonb(run) - array['owner_id', 'request_key', 'started_at'])
        || jsonb_build_object('results', '[]'::jsonb)
        order by run.created_at desc
      )
      from (
        select * from public.evaluation_runs
        where workspace_id = p_workspace_id and owner_id = p_actor_id
        order by created_at desc
        limit least(greatest(p_limit, 1), 100)
      ) run
    ), '[]'::jsonb),
    'next_cursor', null
  );
end;
$$;

create or replace function public.get_evaluation_run(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_evaluation_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  run public.evaluation_runs;
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id);
  select * into strict run from public.evaluation_runs
  where id = p_evaluation_id and workspace_id = p_workspace_id
    and owner_id = p_actor_id;
  return (to_jsonb(run) - array['owner_id', 'request_key', 'started_at'])
    || jsonb_build_object(
      'results', coalesce((
        select jsonb_agg(
          to_jsonb(result) - array['evaluation_id', 'workspace_id', 'details']
          order by result.case_id, result.variant
        )
        from public.evaluation_results result
        where result.evaluation_id = p_evaluation_id
          and result.workspace_id = p_workspace_id
      ), '[]'::jsonb)
    );
end;
$$;

create or replace function public.cleanup_evaluation_retention()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  deleted integer;
begin
  delete from public.evaluation_results
  where evaluation_id in (
    select id from (
      select id, row_number() over (
        partition by workspace_id order by created_at desc
      ) as ordinal
      from public.evaluation_runs
      where status in ('completed', 'failed', 'cancelled')
    ) ranked
    where ranked.ordinal > 20
  );
  get diagnostics deleted = row_count;
  return deleted;
end;
$$;

do $$
declare
  existing_job_id bigint;
begin
  select jobid into existing_job_id from cron.job
  where jobname = 'docpilot-evaluation-retention';
  if existing_job_id is not null then
    perform cron.unschedule(existing_job_id);
  end if;
  perform cron.schedule(
    'docpilot-evaluation-retention',
    '41 3 * * *',
    'select public.cleanup_evaluation_retention()'
  );
end;
$$;

revoke execute on function public.create_evaluation_run(
  uuid, uuid, text, integer, text[], integer, text
) from public, anon, authenticated;
revoke execute on function public.start_evaluation_run(uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.record_evaluation_result(
  uuid, uuid, text, text, text, text, jsonb, numeric,
  integer, integer, integer, text, jsonb
) from public, anon, authenticated;
revoke execute on function public.complete_evaluation_run(
  uuid, uuid, jsonb, boolean, text[], jsonb
) from public, anon, authenticated;
revoke execute on function public.list_evaluation_runs(uuid, uuid, integer)
  from public, anon, authenticated;
revoke execute on function public.get_evaluation_run(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.cleanup_evaluation_retention()
  from public, anon, authenticated;

grant execute on function public.create_evaluation_run(
  uuid, uuid, text, integer, text[], integer, text
) to service_role;
grant execute on function public.start_evaluation_run(uuid, uuid) to service_role;
grant execute on function public.record_evaluation_result(
  uuid, uuid, text, text, text, text, jsonb, numeric,
  integer, integer, integer, text, jsonb
) to service_role;
grant execute on function public.complete_evaluation_run(
  uuid, uuid, jsonb, boolean, text[], jsonb
) to service_role;
grant execute on function public.list_evaluation_runs(uuid, uuid, integer)
  to service_role;
grant execute on function public.get_evaluation_run(uuid, uuid, uuid)
  to service_role;
grant execute on function public.cleanup_evaluation_retention() to service_role;
