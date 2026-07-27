create or replace function app_private.prevent_last_workspace_owner()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'DELETE'
    and not exists (
      select 1
      from public.workspaces workspace
      where workspace.id = old.workspace_id
    )
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
