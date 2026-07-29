do $$
declare
  existing_job_id bigint;
begin
  select jobid into existing_job_id
  from cron.job
  where jobname = 'docpilot-observability-retention';
  if existing_job_id is not null then
    perform cron.unschedule(existing_job_id);
  end if;
  perform cron.schedule(
    'docpilot-observability-retention',
    '17 3 * * *',
    'select public.cleanup_observability_retention()'
  );
end;
$$;
