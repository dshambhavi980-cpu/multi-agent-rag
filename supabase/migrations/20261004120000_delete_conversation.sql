create or replace function public.delete_conversation(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_conversation_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id, p_conversation_id);

  delete from public.rag_runs
  where conversation_id = p_conversation_id
    and workspace_id = p_workspace_id;

  delete from public.messages
  where conversation_id = p_conversation_id
    and workspace_id = p_workspace_id;

  delete from public.conversations
  where id = p_conversation_id
    and workspace_id = p_workspace_id;

  return true;
end;
$$;

revoke execute on function public.delete_conversation(uuid, uuid, uuid) from public, anon, authenticated;
grant execute on function public.delete_conversation(uuid, uuid, uuid) to service_role;
