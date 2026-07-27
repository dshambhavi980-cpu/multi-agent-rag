create or replace function app_private.audit_membership_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  affected_workspace_id uuid;
  affected_user_id uuid;
  affected_role public.workspace_role;
begin
  if tg_op = 'DELETE'
    and pg_catalog.current_setting('app.deleting_workspace_id', true) = old.workspace_id::text
  then
    return old;
  end if;

  affected_workspace_id :=
    case when tg_op = 'DELETE' then old.workspace_id else new.workspace_id end;
  affected_user_id := case when tg_op = 'DELETE' then old.user_id else new.user_id end;
  affected_role := case when tg_op = 'DELETE' then old.role else new.role end;

  insert into public.application_events (
    workspace_id,
    actor_id,
    event_type,
    target_type,
    target_id,
    metadata
  )
  values (
    affected_workspace_id,
    (select auth.uid()),
    'workspace_member.' || lower(tg_op),
    'user',
    affected_user_id,
    jsonb_build_object('role', affected_role)
  );
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;
