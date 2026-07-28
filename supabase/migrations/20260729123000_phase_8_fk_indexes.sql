create index memory_items_conversation_workspace_idx
  on public.memory_items (conversation_id, workspace_id)
  where conversation_id is not null;

create index memory_items_owner_idx
  on public.memory_items (owner_id);

create index memory_items_source_message_workspace_idx
  on public.memory_items (source_message_id, workspace_id)
  where source_message_id is not null;
