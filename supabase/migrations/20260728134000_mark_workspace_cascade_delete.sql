create or replace function app_private.mark_workspace_deleting()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform pg_catalog.set_config(
    'app.deleting_workspace_id',
    old.id::text,
    true
  );
  return old;
end;
$$;

create trigger workspaces_mark_deleting
before delete on public.workspaces
for each row execute function app_private.mark_workspace_deleting();

create or replace function app_private.prevent_last_workspace_owner()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'DELETE'
    and pg_catalog.current_setting('app.deleting_workspace_id', true) = old.workspace_id::text
  then
    return old;
  end if;

  if old.role = 'owner'
    and (tg_op = 'DELETE' or new.role <> 'owner' or new.workspace_id <> old.workspace_id)
    and not exists (
      select 1
      from public.workspace_members member
      where member.workspace_id = old.workspace_id
        and member.role = 'owner'
        and member.user_id <> old.user_id
    )
  then
    raise exception 'A workspace must retain at least one owner.'
      using errcode = '23514';
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;
