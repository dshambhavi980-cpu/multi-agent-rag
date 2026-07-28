create extension if not exists pg_cron with schema pg_catalog;

alter table public.conversations
  add column summary_through_message_id uuid,
  add column summary_message_count integer not null default 0,
  add column summary_updated_at timestamptz,
  add constraint conversations_summary_message_count
    check (summary_message_count >= 0);

create table public.memory_items (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  conversation_id uuid,
  source_message_id uuid,
  content text not null,
  source_type text not null,
  source_excerpt text not null,
  confidence numeric(5, 4) not null,
  visibility text not null default 'private',
  expires_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, workspace_id),
  foreign key (conversation_id, workspace_id)
    references public.conversations (id, workspace_id)
    on delete set null (conversation_id),
  foreign key (source_message_id, workspace_id)
    references public.messages (id, workspace_id)
    on delete set null (source_message_id),
  constraint memory_items_content_length check (char_length(content) between 1 and 2000),
  constraint memory_items_source_type
    check (source_type in ('explicit_user', 'approved')),
  constraint memory_items_source_excerpt_length
    check (char_length(source_excerpt) between 1 and 500),
  constraint memory_items_confidence check (confidence between 0.9 and 1),
  constraint memory_items_visibility check (visibility in ('private', 'workspace')),
  constraint memory_items_expiration check (expires_at is null or expires_at > created_at)
);

create unique index memory_items_active_source_idx
  on public.memory_items (workspace_id, owner_id, source_message_id)
  where source_message_id is not null and deleted_at is null;
create index memory_items_private_retrieval_idx
  on public.memory_items (workspace_id, owner_id, updated_at desc)
  where deleted_at is null and visibility = 'private';
create index memory_items_shared_retrieval_idx
  on public.memory_items (workspace_id, updated_at desc)
  where deleted_at is null and visibility = 'workspace';
create index memory_items_cleanup_idx
  on public.memory_items (expires_at, deleted_at);

create trigger memory_items_set_updated_at
before update on public.memory_items
for each row execute function app_private.set_updated_at();

alter table public.memory_items enable row level security;

create policy memory_items_select_visible
on public.memory_items for select to authenticated
using (
  deleted_at is null
  and (expires_at is null or expires_at > now())
  and (select app_private.is_workspace_member(workspace_id))
  and (
    owner_id = (select auth.uid())
    or visibility = 'workspace'
  )
);

create policy memory_items_delete_owner
on public.memory_items for delete to authenticated
using (
  owner_id = (select auth.uid())
  and (select app_private.is_workspace_member(workspace_id))
);

revoke all on public.memory_items from public, anon, authenticated;
grant select, delete on public.memory_items to authenticated;
grant all on public.memory_items to service_role;

create or replace function public.list_memory_items(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_visibility text default null,
  p_limit integer default 50
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id);
  if p_visibility is not null and p_visibility not in ('private', 'workspace') then
    raise exception 'Invalid memory visibility.' using errcode = '22023';
  end if;
  return jsonb_build_object(
    'items',
    coalesce((
      select jsonb_agg(
        (to_jsonb(item) - 'deleted_at') ||
        jsonb_build_object('can_delete', item.owner_id = p_actor_id)
        order by item.updated_at desc, item.id desc
      )
      from (
        select *
        from public.memory_items memory
        where memory.workspace_id = p_workspace_id
          and memory.deleted_at is null
          and (memory.expires_at is null or memory.expires_at > now())
          and (memory.owner_id = p_actor_id or memory.visibility = 'workspace')
          and (p_visibility is null or memory.visibility = p_visibility)
        order by memory.updated_at desc, memory.id desc
        limit least(greatest(p_limit, 1), 100)
      ) item
    ), '[]'::jsonb),
    'next_cursor', null
  );
end;
$$;

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
  if not found then
    raise exception 'Memory not found.' using errcode = 'P0002';
  end if;
  return true;
end;
$$;

create or replace function public.store_explicit_memory(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_conversation_id uuid,
  p_source_message_id uuid,
  p_content text,
  p_source_excerpt text,
  p_visibility text default 'private',
  p_expires_at timestamptz default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  result public.memory_items;
begin
  perform app_private.assert_rag_actor(
    p_workspace_id, p_actor_id, p_conversation_id
  );
  if p_visibility not in ('private', 'workspace') then
    raise exception 'Invalid memory visibility.' using errcode = '22023';
  end if;
  if not exists (
    select 1
    from public.messages message
    where message.id = p_source_message_id
      and message.workspace_id = p_workspace_id
      and message.conversation_id = p_conversation_id
      and message.role = 'user'
  ) then
    raise exception 'Source message not found.' using errcode = 'P0002';
  end if;
  insert into public.memory_items (
    workspace_id, owner_id, conversation_id, source_message_id,
    content, source_type, source_excerpt, confidence, visibility, expires_at
  ) values (
    p_workspace_id, p_actor_id, p_conversation_id, p_source_message_id,
    trim(p_content), 'explicit_user', left(trim(p_source_excerpt), 500),
    1, p_visibility, p_expires_at
  )
  on conflict (workspace_id, owner_id, source_message_id)
    where source_message_id is not null and deleted_at is null
  do update set
    content = excluded.content,
    source_excerpt = excluded.source_excerpt,
    visibility = excluded.visibility,
    expires_at = excluded.expires_at,
    updated_at = now()
  returning * into result;
  return to_jsonb(result) - 'deleted_at';
end;
$$;

create or replace function public.get_memory_context(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_conversation_id uuid,
  p_recent_message_limit integer default 8,
  p_memory_limit integer default 8
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  conversation_row public.conversations;
begin
  perform app_private.assert_rag_actor(
    p_workspace_id, p_actor_id, p_conversation_id
  );
  select * into strict conversation_row
  from public.conversations
  where id = p_conversation_id and workspace_id = p_workspace_id;
  return jsonb_build_object(
    'summary', conversation_row.summary,
    'summary_message_count', conversation_row.summary_message_count,
    'recent_messages', coalesce((
      select jsonb_agg(to_jsonb(message) order by message.created_at, message.id)
      from (
        select id, role, content, created_at
        from public.messages
        where workspace_id = p_workspace_id
          and conversation_id = p_conversation_id
        order by created_at desc, id desc
        limit least(greatest(p_recent_message_limit, 1), 20)
      ) message
    ), '[]'::jsonb),
    'memories', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'id', memory.id,
          'content', memory.content,
          'source_type', memory.source_type,
          'source_excerpt', memory.source_excerpt,
          'confidence', memory.confidence,
          'visibility', memory.visibility,
          'owner_id', memory.owner_id
        )
        order by memory.updated_at desc, memory.id desc
      )
      from (
        select *
        from public.memory_items item
        where item.workspace_id = p_workspace_id
          and item.deleted_at is null
          and (item.expires_at is null or item.expires_at > now())
          and item.confidence >= 0.9
          and (item.owner_id = p_actor_id or item.visibility = 'workspace')
        order by item.updated_at desc, item.id desc
        limit least(greatest(p_memory_limit, 1), 20)
      ) memory
    ), '[]'::jsonb)
  );
end;
$$;

create or replace function public.refresh_conversation_summary(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_conversation_id uuid,
  p_keep_recent integer default 8
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  total_count integer;
  summary_text text;
  through_id uuid;
  summarized_count integer;
begin
  perform app_private.assert_rag_actor(
    p_workspace_id, p_actor_id, p_conversation_id
  );
  select count(*) into total_count
  from public.messages
  where workspace_id = p_workspace_id and conversation_id = p_conversation_id;

  summarized_count := greatest(total_count - greatest(p_keep_recent, 2), 0);
  if summarized_count = 0 then
    return jsonb_build_object('summary', null, 'summary_message_count', 0);
  end if;

  select
    left(string_agg(
      upper(left(message.role, 1)) || ': ' ||
      left(regexp_replace(message.content, '[[:space:]]+', ' ', 'g'), 320),
      E'\n' order by message.created_at, message.id
    ), 4000),
    (array_agg(message.id order by message.created_at desc, message.id desc))[1]
  into summary_text, through_id
  from (
    select id, role, content, created_at
    from public.messages
    where workspace_id = p_workspace_id and conversation_id = p_conversation_id
    order by created_at, id
    limit summarized_count
  ) message;

  update public.conversations
  set summary = summary_text,
      summary_through_message_id = through_id,
      summary_message_count = summarized_count,
      summary_updated_at = now()
  where id = p_conversation_id and workspace_id = p_workspace_id;
  return jsonb_build_object(
    'summary', summary_text,
    'summary_message_count', summarized_count,
    'summary_through_message_id', through_id
  );
end;
$$;

create or replace function public.cleanup_expired_memory()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  deleted_count integer;
begin
  delete from public.memory_items
  where (expires_at is not null and expires_at < now() - interval '7 days')
     or (deleted_at is not null and deleted_at < now() - interval '30 days');
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

revoke execute on function public.list_memory_items(uuid, uuid, text, integer)
  from public, anon, authenticated;
revoke execute on function public.delete_memory_item(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.store_explicit_memory(
  uuid, uuid, uuid, uuid, text, text, text, timestamptz
) from public, anon, authenticated;
revoke execute on function public.get_memory_context(uuid, uuid, uuid, integer, integer)
  from public, anon, authenticated;
revoke execute on function public.refresh_conversation_summary(uuid, uuid, uuid, integer)
  from public, anon, authenticated;
revoke execute on function public.cleanup_expired_memory()
  from public, anon, authenticated;

grant execute on function public.list_memory_items(uuid, uuid, text, integer)
  to service_role;
grant execute on function public.delete_memory_item(uuid, uuid, uuid)
  to service_role;
grant execute on function public.store_explicit_memory(
  uuid, uuid, uuid, uuid, text, text, text, timestamptz
) to service_role;
grant execute on function public.get_memory_context(uuid, uuid, uuid, integer, integer)
  to service_role;
grant execute on function public.refresh_conversation_summary(uuid, uuid, uuid, integer)
  to service_role;
grant execute on function public.cleanup_expired_memory()
  to service_role;

do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    if not exists (select 1 from cron.job where jobname = 'docpilot-memory-retention') then
      perform cron.schedule(
        'docpilot-memory-retention',
        '17 3 * * *',
        'select public.cleanup_expired_memory()'
      );
    end if;
  end if;
end
$$;
