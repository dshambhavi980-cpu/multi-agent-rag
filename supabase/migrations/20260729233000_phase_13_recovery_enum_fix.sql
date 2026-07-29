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
    set status = (
          case when attempt >= max_attempts then 'quarantined' else 'queued' end
        )::public.ingestion_job_status,
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

revoke all on function public.recover_stale_work() from public, anon, authenticated;
grant execute on function public.recover_stale_work() to service_role;
