create or replace function public.delete_memory_item(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_memory_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id);
  update public.memory_items
  set deleted_at = now()
  where id = p_memory_id
    and workspace_id = p_workspace_id
    and owner_id = p_actor_id
    and deleted_at is null;
  if found then
    return true;
  end if;
  if exists (
    select 1
    from public.memory_items
    where id = p_memory_id
      and workspace_id = p_workspace_id
      and owner_id = p_actor_id
      and deleted_at is not null
  ) then
    return true;
  end if;
  raise exception 'Memory not found.' using errcode = 'P0002';
end;
$$;

revoke execute on function public.delete_memory_item(uuid, uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.delete_memory_item(uuid, uuid, uuid)
  to service_role;
