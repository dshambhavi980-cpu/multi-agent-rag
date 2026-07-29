create table app_private.api_rate_limits (
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  actor_key text not null,
  bucket text not null,
  window_start timestamptz not null,
  request_count integer not null default 0,
  expires_at timestamptz not null,
  primary key (workspace_id, actor_key, bucket, window_start),
  constraint api_rate_limits_bucket_length check (char_length(bucket) between 1 and 80),
  constraint api_rate_limits_count_positive check (request_count > 0)
);

create index api_rate_limits_expiry_idx
  on app_private.api_rate_limits (expires_at);

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
    ceil(extract(epoch from current_window + make_interval(secs => p_window_seconds) - current_time))::integer
  );
  return jsonb_build_object(
    'allowed', current_count <= p_limit,
    'remaining', greatest(p_limit - current_count, 0),
    'retry_after', retry_after,
    'limit', p_limit
  );
end;
$$;

create or replace function public.recover_stale_work()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  recovered_ingestion integer := 0;
  failed_rag integer := 0;
  failed_evaluations integer := 0;
begin
  with recovered as (
    update public.ingestion_jobs
    set status = case when attempt >= max_attempts then 'quarantined' else 'queued' end,
        stage = case when attempt >= max_attempts then 'quarantined' else 'recovered' end,
        locked_at = null,
        error_code = case when attempt >= max_attempts then 'POISON_MESSAGE' else null end,
        error_detail = case
          when attempt >= max_attempts then 'Maximum processing attempts were exhausted.'
          else null
        end
    where status = 'processing'
      and locked_at < now() - interval '5 minutes'
    returning 1
  ) select count(*) into recovered_ingestion from recovered;

  with failed as (
    update public.rag_runs
    set status = 'failed',
        error = jsonb_build_object(
          'code', 'PROCESS_RESTARTED',
          'detail', 'Generation was interrupted and can be retried safely.',
          'retryable', true
        ),
        completed_at = now()
    where status in ('accepted', 'running')
      and updated_at < now() - interval '5 minutes'
    returning 1
  ) select count(*) into failed_rag from failed;

  with failed as (
    update public.evaluation_runs
    set status = 'failed',
        error = jsonb_build_object(
          'code', 'PROCESS_RESTARTED',
          'detail', 'Evaluation was interrupted and may be restarted.',
          'retryable', true
        ),
        completed_at = now()
    where status = 'running'
      and started_at < now() - interval '15 minutes'
    returning 1
  ) select count(*) into failed_evaluations from failed;

  delete from app_private.api_rate_limits where expires_at < now();
  return jsonb_build_object(
    'ingestion_jobs', recovered_ingestion,
    'rag_runs', failed_rag,
    'evaluation_runs', failed_evaluations
  );
end;
$$;

create or replace function public.phase_13_capacity_snapshot(p_workspace_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'documents', (select count(*) from public.documents where workspace_id = p_workspace_id),
    'chunks', (select count(*) from public.document_chunks where workspace_id = p_workspace_id),
    'chunk_bytes', coalesce((
      select pg_column_size(array_agg(row(chunk.content, chunk.embedding)))
      from public.document_chunks chunk where chunk.workspace_id = p_workspace_id
    ), 0),
    'bytes_per_1000_chunks', coalesce((
      select round(sum(pg_column_size(row(chunk.content, chunk.embedding)))::numeric * 1000 / nullif(count(*), 0))
      from public.document_chunks chunk where chunk.workspace_id = p_workspace_id
    ), 0),
    'active_ingestion_jobs', (
      select count(*) from public.ingestion_jobs
      where workspace_id = p_workspace_id and status in ('queued', 'processing')
    ),
    'active_rag_runs', (
      select count(*) from public.rag_runs
      where workspace_id = p_workspace_id and status in ('accepted', 'running', 'awaiting_approval')
    )
  );
$$;

revoke all on function public.consume_api_rate_limit(uuid, uuid, text, integer, integer)
  from public, anon, authenticated;
revoke all on function public.recover_stale_work() from public, anon, authenticated;
revoke all on function public.phase_13_capacity_snapshot(uuid) from public, anon, authenticated;
grant execute on function public.consume_api_rate_limit(uuid, uuid, text, integer, integer)
  to service_role;
grant execute on function public.recover_stale_work() to service_role;
grant execute on function public.phase_13_capacity_snapshot(uuid) to service_role;

comment on function public.consume_api_rate_limit(uuid, uuid, text, integer, integer) is
  'Atomically enforces fixed-window user and workspace request limits.';
comment on function public.recover_stale_work() is
  'Recovers durable ingestion work and closes stale non-resumable runs after process restarts.';
