create extension if not exists vector with schema extensions;
create extension if not exists pgmq;

create schema if not exists app_private;
revoke all on schema app_private from public, anon;
grant usage on schema app_private to authenticated;

create type public.workspace_role as enum ('owner', 'reviewer', 'member');

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint profiles_display_name_length
    check (display_name is null or char_length(display_name) between 1 and 120)
);

create table public.workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_by uuid not null references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint workspaces_name_length check (char_length(name) between 2 and 80)
);

create table public.workspace_members (
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role public.workspace_role not null default 'member',
  invited_by uuid references auth.users (id) on delete set null,
  joined_at timestamptz not null default now(),
  primary key (workspace_id, user_id)
);

create table public.application_events (
  id bigint generated always as identity primary key,
  workspace_id uuid references public.workspaces (id) on delete set null,
  actor_id uuid references auth.users (id) on delete set null,
  event_type text not null,
  target_type text,
  target_id uuid,
  request_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint application_events_type_length
    check (char_length(event_type) between 3 and 120),
  constraint application_events_metadata_object
    check (jsonb_typeof(metadata) = 'object')
);

create index workspaces_created_by_idx
  on public.workspaces (created_by);
create index workspace_members_user_workspace_idx
  on public.workspace_members (user_id, workspace_id);
create index workspace_members_workspace_role_idx
  on public.workspace_members (workspace_id, role);
create index workspace_members_invited_by_idx
  on public.workspace_members (invited_by)
  where invited_by is not null;
create index application_events_workspace_created_idx
  on public.application_events (workspace_id, created_at desc);
create index application_events_actor_created_idx
  on public.application_events (actor_id, created_at desc)
  where actor_id is not null;

create or replace function app_private.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function app_private.is_workspace_member(target_workspace_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select (select auth.uid()) is not null
    and exists (
      select 1
      from public.workspace_members member
      where member.workspace_id = target_workspace_id
        and member.user_id = (select auth.uid())
    );
$$;

create or replace function app_private.has_workspace_role(
  target_workspace_id uuid,
  allowed_roles public.workspace_role[]
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select (select auth.uid()) is not null
    and exists (
      select 1
      from public.workspace_members member
      where member.workspace_id = target_workspace_id
        and member.user_id = (select auth.uid())
        and member.role = any (allowed_roles)
    );
$$;

create or replace function app_private.shares_workspace(other_user_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select (select auth.uid()) is not null
    and exists (
      select 1
      from public.workspace_members mine
      join public.workspace_members theirs
        on theirs.workspace_id = mine.workspace_id
      where mine.user_id = (select auth.uid())
        and theirs.user_id = other_user_id
    );
$$;

create or replace function app_private.storage_workspace_id(object_name text)
returns uuid
language plpgsql
immutable
security invoker
set search_path = ''
as $$
declare
  first_segment text;
begin
  first_segment := split_part(object_name, '/', 1);
  if first_segment ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' then
    return first_segment::uuid;
  end if;
  return null;
end;
$$;

create or replace function app_private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, avatar_url)
  values (
    new.id,
    nullif(trim(coalesce(new.raw_user_meta_data ->> 'full_name', '')), ''),
    nullif(trim(coalesce(new.raw_user_meta_data ->> 'avatar_url', '')), '')
  )
  on conflict (id) do nothing;

  insert into public.application_events (
    actor_id,
    event_type,
    target_type,
    target_id
  )
  values (new.id, 'auth.user_created', 'user', new.id);

  return new;
end;
$$;

create or replace function app_private.bootstrap_workspace_owner()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.workspace_members (
    workspace_id,
    user_id,
    role,
    invited_by
  )
  values (new.id, new.created_by, 'owner', new.created_by);
  return new;
end;
$$;

create or replace function app_private.prevent_last_workspace_owner()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
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

create or replace function app_private.audit_workspace_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  event_workspace_id uuid;
  event_target_id uuid;
begin
  event_workspace_id := case when tg_op = 'DELETE' then null else new.id end;
  event_target_id := case when tg_op = 'DELETE' then old.id else new.id end;

  insert into public.application_events (
    workspace_id,
    actor_id,
    event_type,
    target_type,
    target_id
  )
  values (
    event_workspace_id,
    (select auth.uid()),
    'workspace.' || lower(tg_op),
    'workspace',
    event_target_id
  );
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

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

revoke execute on all functions in schema app_private
  from public, anon, authenticated, service_role;
grant execute on function app_private.is_workspace_member(uuid) to authenticated;
grant execute on function app_private.has_workspace_role(uuid, public.workspace_role[])
  to authenticated;
grant execute on function app_private.shares_workspace(uuid) to authenticated;
grant execute on function app_private.storage_workspace_id(text) to authenticated;

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function app_private.set_updated_at();

create trigger workspaces_set_updated_at
before update on public.workspaces
for each row execute function app_private.set_updated_at();

create trigger on_auth_user_created
after insert on auth.users
for each row execute function app_private.handle_new_user();

create trigger on_workspace_created_add_owner
after insert on public.workspaces
for each row execute function app_private.bootstrap_workspace_owner();

create trigger workspace_members_retain_owner
before update or delete on public.workspace_members
for each row execute function app_private.prevent_last_workspace_owner();

create trigger workspaces_audit_changes
after insert or update or delete on public.workspaces
for each row execute function app_private.audit_workspace_change();

create trigger workspace_members_audit_changes
after insert or update or delete on public.workspace_members
for each row execute function app_private.audit_membership_change();

alter table public.profiles enable row level security;
alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.application_events enable row level security;

create policy profiles_select_shared_workspace
on public.profiles
for select
to authenticated
using (
  id = (select auth.uid())
  or (select app_private.shares_workspace(id))
);

create policy profiles_update_self
on public.profiles
for update
to authenticated
using (id = (select auth.uid()))
with check (id = (select auth.uid()));

create policy workspaces_select_member
on public.workspaces
for select
to authenticated
using ((select app_private.is_workspace_member(id)));

create policy workspaces_insert_creator
on public.workspaces
for insert
to authenticated
with check (created_by = (select auth.uid()));

create policy workspaces_update_owner
on public.workspaces
for update
to authenticated
using (
  (select app_private.has_workspace_role(
    id,
    array['owner']::public.workspace_role[]
  ))
)
with check (
  created_by = (select auth.uid())
  or (select app_private.has_workspace_role(
    id,
    array['owner']::public.workspace_role[]
  ))
);

create policy workspaces_delete_owner
on public.workspaces
for delete
to authenticated
using (
  (select app_private.has_workspace_role(
    id,
    array['owner']::public.workspace_role[]
  ))
);

create policy workspace_members_select_member
on public.workspace_members
for select
to authenticated
using ((select app_private.is_workspace_member(workspace_id)));

create policy workspace_members_insert_owner
on public.workspace_members
for insert
to authenticated
with check (
  invited_by = (select auth.uid())
  and (select app_private.has_workspace_role(
    workspace_id,
    array['owner']::public.workspace_role[]
  ))
);

create policy workspace_members_update_owner
on public.workspace_members
for update
to authenticated
using (
  (select app_private.has_workspace_role(
    workspace_id,
    array['owner']::public.workspace_role[]
  ))
)
with check (
  (select app_private.has_workspace_role(
    workspace_id,
    array['owner']::public.workspace_role[]
  ))
);

create policy workspace_members_delete_owner
on public.workspace_members
for delete
to authenticated
using (
  (select app_private.has_workspace_role(
    workspace_id,
    array['owner']::public.workspace_role[]
  ))
);

create policy application_events_select_authorized
on public.application_events
for select
to authenticated
using (
  (workspace_id is null and actor_id = (select auth.uid()))
  or (select app_private.has_workspace_role(
    workspace_id,
    array['owner', 'reviewer']::public.workspace_role[]
  ))
);

revoke all on public.profiles from public, anon, authenticated;
revoke all on public.workspaces from public, anon, authenticated;
revoke all on public.workspace_members from public, anon, authenticated;
revoke all on public.application_events from public, anon, authenticated;

grant select, update (display_name, avatar_url) on public.profiles to authenticated;
grant select, insert, update (name), delete on public.workspaces to authenticated;
grant select, insert, update (role), delete on public.workspace_members to authenticated;
grant select on public.application_events to authenticated;

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'workspace-documents',
  'workspace-documents',
  false,
  26214400,
  array[
    'application/pdf',
    'text/plain',
    'text/markdown',
    'text/html'
  ]
)
on conflict (id) do update
set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create policy workspace_documents_select_member
on storage.objects
for select
to authenticated
using (
  bucket_id = 'workspace-documents'
  and (select app_private.is_workspace_member(
    app_private.storage_workspace_id(name)
  ))
);

create policy workspace_documents_insert_member
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'workspace-documents'
  and split_part(name, '/', 2) = (select auth.uid())::text
  and (select app_private.is_workspace_member(
    app_private.storage_workspace_id(name)
  ))
);

create policy workspace_documents_update_uploader_or_owner
on storage.objects
for update
to authenticated
using (
  bucket_id = 'workspace-documents'
  and (
    owner_id = (select auth.uid())::text
    or (select app_private.has_workspace_role(
      app_private.storage_workspace_id(name),
      array['owner']::public.workspace_role[]
    ))
  )
)
with check (
  bucket_id = 'workspace-documents'
  and split_part(name, '/', 2) = (select auth.uid())::text
  and (select app_private.is_workspace_member(
    app_private.storage_workspace_id(name)
  ))
);

create policy workspace_documents_delete_uploader_or_owner
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'workspace-documents'
  and (
    owner_id = (select auth.uid())::text
    or (select app_private.has_workspace_role(
      app_private.storage_workspace_id(name),
      array['owner']::public.workspace_role[]
    ))
  )
);
