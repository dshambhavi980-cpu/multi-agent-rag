begin;

set local role authenticated;

do $$
begin
  if has_function_privilege(
    current_user,
    'public.consume_api_rate_limit(uuid,uuid,text,integer,integer)',
    'execute'
  ) then
    raise exception 'authenticated users must not execute service rate-limit functions';
  end if;
  if has_function_privilege(
    current_user,
    'public.recover_stale_work()',
    'execute'
  ) then
    raise exception 'authenticated users must not execute recovery functions';
  end if;
  if has_table_privilege(current_user, 'app_private.api_rate_limits', 'select') then
    raise exception 'authenticated users must not read rate-limit counters';
  end if;
end;
$$;

rollback;
