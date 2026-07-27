create type public.document_status as enum (
  'uploaded',
  'queued',
  'processing',
  'ready',
  'failed',
  'quarantined'
);

create type public.ingestion_job_status as enum (
  'queued',
  'processing',
  'completed',
  'failed',
  'quarantined'
);

create table public.document_uploads (
  id uuid primary key,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  uploaded_by uuid not null references auth.users (id) on delete cascade,
  object_path text not null unique,
  filename text not null,
  expected_content_type text not null,
  expected_size_bytes bigint not null,
  expected_sha256 text not null,
  completed_at timestamptz,
  document_id uuid,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  constraint document_uploads_filename_length
    check (char_length(filename) between 1 and 255),
  constraint document_uploads_content_type
    check (
      expected_content_type in (
        'application/pdf',
        'text/plain',
        'text/markdown',
        'text/html'
      )
    ),
  constraint document_uploads_size
    check (expected_size_bytes between 1 and 26214400),
  constraint document_uploads_sha256
    check (expected_sha256 ~ '^[a-f0-9]{64}$'),
  constraint document_uploads_object_path
    check (
      split_part(object_path, '/', 1) = workspace_id::text
      and split_part(object_path, '/', 2) = uploaded_by::text
      and split_part(object_path, '/', 3) = id::text
    )
);

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  uploaded_by uuid not null references auth.users (id) on delete restrict,
  object_path text not null unique,
  filename text not null,
  title text,
  content_type text not null,
  size_bytes bigint not null,
  sha256 text not null,
  status public.document_status not null default 'uploaded',
  processing_version integer not null default 1,
  page_count integer,
  chunk_count integer not null default 0,
  tags text[] not null default '{}',
  failure_code text,
  failure_detail text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, workspace_id),
  constraint documents_filename_length check (char_length(filename) between 1 and 255),
  constraint documents_title_length check (title is null or char_length(title) <= 255),
  constraint documents_content_type
    check (
      content_type in (
        'application/pdf',
        'text/plain',
        'text/markdown',
        'text/html'
      )
    ),
  constraint documents_size check (size_bytes between 1 and 26214400),
  constraint documents_sha256 check (sha256 ~ '^[a-f0-9]{64}$'),
  constraint documents_processing_version check (processing_version > 0),
  constraint documents_page_count check (page_count is null or page_count >= 0),
  constraint documents_chunk_count check (chunk_count >= 0),
  constraint documents_tags_count check (cardinality(tags) <= 20)
);

alter table public.document_uploads
  add constraint document_uploads_document_id_fkey
  foreign key (document_id) references public.documents (id) on delete set null;

create table public.document_pages (
  id bigint generated always as identity primary key,
  workspace_id uuid not null,
  document_id uuid not null,
  page_number integer not null,
  content text not null,
  char_count integer not null,
  created_at timestamptz not null default now(),
  unique (document_id, page_number),
  foreign key (document_id, workspace_id)
    references public.documents (id, workspace_id) on delete cascade,
  constraint document_pages_page_number check (page_number > 0),
  constraint document_pages_char_count check (char_count >= 0),
  constraint document_pages_content_length check (char_length(content) = char_count)
);

create table public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  document_id uuid not null,
  chunk_index integer not null,
  processing_version integer not null,
  strategy text not null default 'provenance_v1',
  content text not null,
  page_start integer not null,
  page_end integer not null,
  section_heading text,
  char_start integer,
  char_end integer,
  token_count integer,
  search_vector tsvector generated always as (
    to_tsvector('english', content)
  ) stored,
  created_at timestamptz not null default now(),
  unique (document_id, processing_version, chunk_index),
  foreign key (document_id, workspace_id)
    references public.documents (id, workspace_id) on delete cascade,
  constraint document_chunks_index check (chunk_index >= 0),
  constraint document_chunks_version check (processing_version > 0),
  constraint document_chunks_content check (char_length(content) > 0),
  constraint document_chunks_pages check (page_start > 0 and page_end >= page_start),
  constraint document_chunks_offsets
    check (
      (char_start is null and char_end is null)
      or (char_start is not null and char_end is not null and char_end >= char_start)
    ),
  constraint document_chunks_token_count check (token_count is null or token_count >= 0)
);

create table public.ingestion_jobs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  document_id uuid not null,
  status public.ingestion_job_status not null default 'queued',
  stage text,
  progress numeric(5, 4) not null default 0,
  attempt integer not null default 0,
  max_attempts integer not null default 3,
  queue_message_id bigint,
  locked_at timestamptz,
  error_code text,
  error_detail text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  foreign key (document_id, workspace_id)
    references public.documents (id, workspace_id) on delete cascade,
  constraint ingestion_jobs_progress check (progress between 0 and 1),
  constraint ingestion_jobs_attempt check (attempt >= 0 and max_attempts between 1 and 10)
);

create unique index documents_workspace_sha256_idx
  on public.documents (workspace_id, sha256);
create index documents_workspace_status_created_idx
  on public.documents (workspace_id, status, created_at desc);
create index documents_uploaded_by_idx
  on public.documents (uploaded_by);
create index document_uploads_workspace_created_idx
  on public.document_uploads (workspace_id, created_at desc);
create index document_uploads_uploaded_by_idx
  on public.document_uploads (uploaded_by);
create index document_uploads_document_id_idx
  on public.document_uploads (document_id)
  where document_id is not null;
create index document_pages_workspace_document_idx
  on public.document_pages (workspace_id, document_id, page_number);
create index document_chunks_workspace_document_idx
  on public.document_chunks (workspace_id, document_id, processing_version, chunk_index);
create index document_chunks_search_idx
  on public.document_chunks using gin (search_vector);
create index ingestion_jobs_workspace_status_created_idx
  on public.ingestion_jobs (workspace_id, status, created_at);
create index ingestion_jobs_document_created_idx
  on public.ingestion_jobs (document_id, created_at desc);
create unique index ingestion_jobs_queue_message_idx
  on public.ingestion_jobs (queue_message_id)
  where queue_message_id is not null;
create unique index ingestion_jobs_one_active_document_idx
  on public.ingestion_jobs (document_id)
  where status in ('queued', 'processing');

create or replace function app_private.validate_document_status_transition()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.status = new.status then
    return new;
  end if;

  if not (
    (old.status = 'uploaded' and new.status in ('queued', 'failed', 'quarantined'))
    or (old.status = 'queued' and new.status in ('processing', 'failed', 'quarantined'))
    or (old.status = 'processing' and new.status in ('queued', 'ready', 'failed', 'quarantined'))
    or (old.status in ('failed', 'quarantined') and new.status = 'queued')
  ) then
    raise exception 'Invalid document status transition: % -> %', old.status, new.status
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create or replace function app_private.audit_document_status()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' or old.status is distinct from new.status then
    insert into public.application_events (
      workspace_id,
      actor_id,
      event_type,
      target_type,
      target_id,
      metadata
    )
    values (
      new.workspace_id,
      coalesce((select auth.uid()), new.uploaded_by),
      'document.status_changed',
      'document',
      new.id,
      jsonb_build_object(
        'from', case when tg_op = 'INSERT' then null else old.status::text end,
        'to', new.status::text
      )
    );
  end if;
  return new;
end;
$$;

create trigger documents_set_updated_at
before update on public.documents
for each row execute function app_private.set_updated_at();

create trigger ingestion_jobs_set_updated_at
before update on public.ingestion_jobs
for each row execute function app_private.set_updated_at();

create trigger documents_validate_status
before update of status on public.documents
for each row execute function app_private.validate_document_status_transition();

create trigger documents_audit_insert
after insert on public.documents
for each row execute function app_private.audit_document_status();

create trigger documents_audit_status_update
after update of status on public.documents
for each row execute function app_private.audit_document_status();

revoke execute on function app_private.validate_document_status_transition()
  from public, anon, authenticated, service_role;
revoke execute on function app_private.audit_document_status()
  from public, anon, authenticated, service_role;

do $$
begin
  if not exists (
    select 1 from pgmq.meta where queue_name = 'document_ingestion'
  ) then
    perform pgmq.create('document_ingestion');
  end if;
end;
$$;

create or replace function public.finalize_document_upload(
  p_upload_id uuid,
  p_actor_id uuid,
  p_actual_sha256 text,
  p_actual_size_bytes bigint,
  p_actual_content_type text,
  p_request_id uuid,
  p_title text default null,
  p_tags text[] default '{}'
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  upload_row public.document_uploads;
  document_row public.documents;
  job_row public.ingestion_jobs;
  message_id bigint;
begin
  select * into upload_row
  from public.document_uploads
  where id = p_upload_id
  for update;

  if upload_row.id is null then
    raise exception 'Upload session not found.' using errcode = 'P0002';
  end if;
  if upload_row.uploaded_by <> p_actor_id then
    raise exception 'Upload owner mismatch.' using errcode = '42501';
  end if;
  if upload_row.expires_at < now() and upload_row.completed_at is null then
    raise exception 'Upload session expired.' using errcode = '22023';
  end if;
  if p_actual_sha256 !~ '^[a-f0-9]{64}$'
    or p_actual_sha256 <> upload_row.expected_sha256
    or p_actual_size_bytes <> upload_row.expected_size_bytes
    or p_actual_content_type <> upload_row.expected_content_type
  then
    raise exception 'Uploaded object does not match the declared metadata.'
      using errcode = '22023';
  end if;
  if not exists (
    select 1
    from public.workspace_members member
    where member.workspace_id = upload_row.workspace_id
      and member.user_id = p_actor_id
  ) then
    raise exception 'Workspace membership is required.' using errcode = '42501';
  end if;
  if not exists (
    select 1
    from storage.objects object
    where object.bucket_id = 'workspace-documents'
      and object.name = upload_row.object_path
      and object.owner_id = p_actor_id::text
  ) then
    raise exception 'Uploaded object is missing or has the wrong owner.'
      using errcode = 'P0002';
  end if;

  if upload_row.completed_at is not null then
    select * into document_row from public.documents where id = upload_row.document_id;
    select * into job_row
    from public.ingestion_jobs
    where document_id = document_row.id
    order by created_at desc
    limit 1;
    return jsonb_build_object(
      'deduplicated', upload_row.object_path <> document_row.object_path,
      'document', to_jsonb(document_row),
      'job', to_jsonb(job_row),
      'duplicate_object_path',
        case
          when upload_row.object_path <> document_row.object_path
          then upload_row.object_path
          else null
        end
    );
  end if;

  select * into document_row
  from public.documents
  where workspace_id = upload_row.workspace_id
    and sha256 = p_actual_sha256;

  if document_row.id is not null then
    update public.document_uploads
    set completed_at = now(), document_id = document_row.id
    where id = upload_row.id;
    select * into job_row
    from public.ingestion_jobs
    where document_id = document_row.id
    order by created_at desc
    limit 1;
    return jsonb_build_object(
      'deduplicated', true,
      'document', to_jsonb(document_row),
      'job', to_jsonb(job_row),
      'duplicate_object_path', upload_row.object_path
    );
  end if;

  if (
    select count(*)
    from public.documents
    where workspace_id = upload_row.workspace_id
  ) >= 100 then
    raise exception 'Workspace document limit reached.' using errcode = 'P0001';
  end if;

  insert into public.documents (
    workspace_id,
    uploaded_by,
    object_path,
    filename,
    title,
    content_type,
    size_bytes,
    sha256,
    status,
    tags
  )
  values (
    upload_row.workspace_id,
    p_actor_id,
    upload_row.object_path,
    upload_row.filename,
    nullif(trim(p_title), ''),
    p_actual_content_type,
    p_actual_size_bytes,
    p_actual_sha256,
    'uploaded',
    coalesce(p_tags, '{}')
  )
  returning * into document_row;

  insert into public.ingestion_jobs (
    workspace_id,
    document_id,
    status,
    stage,
    progress
  )
  values (
    upload_row.workspace_id,
    document_row.id,
    'queued',
    'queued',
    0
  )
  returning * into job_row;

  select pgmq.send(
    queue_name => 'document_ingestion',
    msg => jsonb_build_object(
      'job_id', job_row.id,
      'document_id', document_row.id,
      'workspace_id', document_row.workspace_id,
      'object_path', document_row.object_path,
      'content_type', document_row.content_type,
      'filename', document_row.filename,
      'processing_version', document_row.processing_version
    ),
    delay => 0
  )
  into message_id;

  update public.ingestion_jobs
  set queue_message_id = message_id
  where id = job_row.id
  returning * into job_row;

  update public.documents
  set status = 'queued'
  where id = document_row.id
  returning * into document_row;

  update public.document_uploads
  set completed_at = now(), document_id = document_row.id
  where id = upload_row.id;

  insert into public.application_events (
    workspace_id,
    actor_id,
    event_type,
    target_type,
    target_id,
    request_id,
    metadata
  )
  values (
    document_row.workspace_id,
    p_actor_id,
    'document.upload_completed',
    'document',
    document_row.id,
    p_request_id,
    jsonb_build_object('job_id', job_row.id)
  );

  return jsonb_build_object(
    'deduplicated', false,
    'document', to_jsonb(document_row),
    'job', to_jsonb(job_row),
    'duplicate_object_path', null
  );
end;
$$;

create or replace function public.claim_document_ingestion(
  p_visibility_seconds integer default 120,
  p_batch_size integer default 1
)
returns table (
  msg_id bigint,
  read_ct bigint,
  enqueued_at timestamptz,
  vt timestamptz,
  message jsonb
)
language sql
security definer
set search_path = ''
as $$
  select queue_message.msg_id,
         queue_message.read_ct,
         queue_message.enqueued_at,
         queue_message.vt,
         queue_message.message
  from pgmq.read(
    queue_name => 'document_ingestion',
    vt => least(greatest(p_visibility_seconds, 30), 900),
    qty => least(greatest(p_batch_size, 1), 10)
  ) as queue_message;
$$;

create or replace function public.start_document_ingestion(
  p_job_id uuid,
  p_message_id bigint
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  job_row public.ingestion_jobs;
  document_row public.documents;
begin
  select * into job_row
  from public.ingestion_jobs
  where id = p_job_id
  for update;

  if job_row.id is null then
    return jsonb_build_object('should_process', false, 'reason', 'job_missing');
  end if;
  if job_row.status = 'completed' then
    return jsonb_build_object('should_process', false, 'reason', 'already_completed');
  end if;
  if job_row.status in ('failed', 'quarantined') then
    return jsonb_build_object('should_process', false, 'reason', 'terminal');
  end if;
  if job_row.queue_message_id <> p_message_id then
    return jsonb_build_object('should_process', false, 'reason', 'message_mismatch');
  end if;
  if job_row.attempt >= job_row.max_attempts then
    update public.ingestion_jobs
    set status = 'failed',
        stage = 'failed',
        error_code = 'RETRY_LIMIT_EXCEEDED',
        error_detail = 'The ingestion retry limit was exceeded.',
        completed_at = now()
    where id = job_row.id;
    update public.documents
    set status = 'failed',
        failure_code = 'RETRY_LIMIT_EXCEEDED',
        failure_detail = 'The ingestion retry limit was exceeded.'
    where id = job_row.document_id;
    return jsonb_build_object('should_process', false, 'reason', 'retry_limit');
  end if;

  update public.ingestion_jobs
  set status = 'processing',
      stage = 'downloading',
      progress = 0.05,
      attempt = attempt + 1,
      locked_at = now(),
      error_code = null,
      error_detail = null
  where id = job_row.id
  returning * into job_row;

  update public.documents
  set status = 'processing',
      failure_code = null,
      failure_detail = null
  where id = job_row.document_id
  returning * into document_row;

  return jsonb_build_object(
    'should_process', true,
    'job', to_jsonb(job_row),
    'document', to_jsonb(document_row)
  );
end;
$$;

create or replace function public.complete_document_ingestion(
  p_job_id uuid,
  p_pages jsonb,
  p_chunks jsonb
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  job_row public.ingestion_jobs;
  document_row public.documents;
begin
  select * into job_row
  from public.ingestion_jobs
  where id = p_job_id
  for update;

  if job_row.id is null then
    raise exception 'Ingestion job not found.' using errcode = 'P0002';
  end if;
  if job_row.status = 'completed' then
    return true;
  end if;
  if jsonb_array_length(coalesce(p_pages, '[]'::jsonb)) > 1000
    or jsonb_array_length(coalesce(p_chunks, '[]'::jsonb)) > 10000
  then
    raise exception 'Parsed output exceeds the configured limits.'
      using errcode = '54000';
  end if;

  select * into document_row
  from public.documents
  where id = job_row.document_id
  for update;

  delete from public.document_pages where document_id = document_row.id;
  delete from public.document_chunks where document_id = document_row.id;

  insert into public.document_pages (
    workspace_id,
    document_id,
    page_number,
    content,
    char_count
  )
  select document_row.workspace_id,
         document_row.id,
         parsed.page_number,
         parsed.content,
         char_length(parsed.content)
  from jsonb_to_recordset(coalesce(p_pages, '[]'::jsonb))
    as parsed(page_number integer, content text);

  insert into public.document_chunks (
    workspace_id,
    document_id,
    chunk_index,
    processing_version,
    strategy,
    content,
    page_start,
    page_end,
    section_heading,
    char_start,
    char_end,
    token_count
  )
  select document_row.workspace_id,
         document_row.id,
         parsed.chunk_index,
         document_row.processing_version,
         'provenance_v1',
         parsed.content,
         parsed.page_start,
         parsed.page_end,
         parsed.section_heading,
         parsed.char_start,
         parsed.char_end,
         parsed.token_count
  from jsonb_to_recordset(coalesce(p_chunks, '[]'::jsonb))
    as parsed(
      chunk_index integer,
      content text,
      page_start integer,
      page_end integer,
      section_heading text,
      char_start integer,
      char_end integer,
      token_count integer
    );

  update public.documents
  set status = 'ready',
      page_count = jsonb_array_length(coalesce(p_pages, '[]'::jsonb)),
      chunk_count = jsonb_array_length(coalesce(p_chunks, '[]'::jsonb)),
      failure_code = null,
      failure_detail = null
  where id = document_row.id;

  update public.ingestion_jobs
  set status = 'completed',
      stage = 'completed',
      progress = 1,
      locked_at = null,
      completed_at = now(),
      error_code = null,
      error_detail = null
  where id = job_row.id;

  return true;
end;
$$;

create or replace function public.fail_document_ingestion(
  p_job_id uuid,
  p_error_code text,
  p_error_detail text,
  p_quarantined boolean,
  p_retryable boolean
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  job_row public.ingestion_jobs;
  should_retry boolean;
  terminal_job_status public.ingestion_job_status;
  terminal_document_status public.document_status;
begin
  select * into job_row
  from public.ingestion_jobs
  where id = p_job_id
  for update;

  if job_row.id is null then
    raise exception 'Ingestion job not found.' using errcode = 'P0002';
  end if;

  should_retry := p_retryable and job_row.attempt < job_row.max_attempts;
  if should_retry then
    update public.ingestion_jobs
    set status = 'queued',
        stage = 'retry_wait',
        progress = 0,
        locked_at = null,
        error_code = left(p_error_code, 120),
        error_detail = left(p_error_detail, 1000)
    where id = job_row.id;
    update public.documents
    set status = 'queued',
        failure_code = left(p_error_code, 120),
        failure_detail = left(p_error_detail, 1000)
    where id = job_row.document_id;
    return jsonb_build_object(
      'retry', true,
      'delay_seconds', least(60, (2 ^ greatest(job_row.attempt, 1))::integer)
    );
  end if;

  terminal_job_status := (
    case when p_quarantined then 'quarantined' else 'failed' end
  )::public.ingestion_job_status;
  terminal_document_status := (
    case when p_quarantined then 'quarantined' else 'failed' end
  )::public.document_status;

  update public.ingestion_jobs
  set status = terminal_job_status,
      stage = terminal_job_status::text,
      locked_at = null,
      error_code = left(p_error_code, 120),
      error_detail = left(p_error_detail, 1000),
      completed_at = now()
  where id = job_row.id;
  update public.documents
  set status = terminal_document_status,
      failure_code = left(p_error_code, 120),
      failure_detail = left(p_error_detail, 1000)
  where id = job_row.document_id;

  return jsonb_build_object('retry', false, 'delay_seconds', 0);
end;
$$;

create or replace function public.archive_document_ingestion(p_message_id bigint)
returns boolean
language sql
security definer
set search_path = ''
as $$
  select pgmq.archive('document_ingestion', p_message_id);
$$;

create or replace function public.defer_document_ingestion(
  p_message_id bigint,
  p_delay_seconds integer
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform pgmq.set_vt(
    'document_ingestion',
    p_message_id,
    least(greatest(p_delay_seconds, 1), 300)
  );
  return true;
end;
$$;

revoke execute on function public.finalize_document_upload(
  uuid, uuid, text, bigint, text, uuid, text, text[]
) from public, anon, authenticated;
revoke execute on function public.claim_document_ingestion(integer, integer)
  from public, anon, authenticated;
revoke execute on function public.start_document_ingestion(uuid, bigint)
  from public, anon, authenticated;
revoke execute on function public.complete_document_ingestion(uuid, jsonb, jsonb)
  from public, anon, authenticated;
revoke execute on function public.fail_document_ingestion(uuid, text, text, boolean, boolean)
  from public, anon, authenticated;
revoke execute on function public.archive_document_ingestion(bigint)
  from public, anon, authenticated;
revoke execute on function public.defer_document_ingestion(bigint, integer)
  from public, anon, authenticated;

grant execute on function public.finalize_document_upload(
  uuid, uuid, text, bigint, text, uuid, text, text[]
) to service_role;
grant execute on function public.claim_document_ingestion(integer, integer)
  to service_role;
grant execute on function public.start_document_ingestion(uuid, bigint)
  to service_role;
grant execute on function public.complete_document_ingestion(uuid, jsonb, jsonb)
  to service_role;
grant execute on function public.fail_document_ingestion(uuid, text, text, boolean, boolean)
  to service_role;
grant execute on function public.archive_document_ingestion(bigint)
  to service_role;
grant execute on function public.defer_document_ingestion(bigint, integer)
  to service_role;

alter table public.document_uploads enable row level security;
alter table public.documents enable row level security;
alter table public.document_pages enable row level security;
alter table public.document_chunks enable row level security;
alter table public.ingestion_jobs enable row level security;

create policy document_uploads_select_owner
on public.document_uploads
for select
to authenticated
using (
  uploaded_by = (select auth.uid())
  and (select app_private.is_workspace_member(workspace_id))
);

create policy document_uploads_insert_owner
on public.document_uploads
for insert
to authenticated
with check (
  uploaded_by = (select auth.uid())
  and completed_at is null
  and document_id is null
  and expires_at > now()
  and expires_at <= now() + interval '2 hours 5 minutes'
  and (select app_private.is_workspace_member(workspace_id))
);

create policy documents_select_member
on public.documents
for select
to authenticated
using ((select app_private.is_workspace_member(workspace_id)));

create policy document_pages_select_member
on public.document_pages
for select
to authenticated
using ((select app_private.is_workspace_member(workspace_id)));

create policy document_chunks_select_member
on public.document_chunks
for select
to authenticated
using ((select app_private.is_workspace_member(workspace_id)));

create policy ingestion_jobs_select_member
on public.ingestion_jobs
for select
to authenticated
using ((select app_private.is_workspace_member(workspace_id)));

revoke all on public.document_uploads from public, anon, authenticated;
revoke all on public.documents from public, anon, authenticated;
revoke all on public.document_pages from public, anon, authenticated;
revoke all on public.document_chunks from public, anon, authenticated;
revoke all on public.ingestion_jobs from public, anon, authenticated;

grant select, insert on public.document_uploads to authenticated;
grant select on public.documents to authenticated;
grant select on public.document_pages to authenticated;
grant select on public.document_chunks to authenticated;
grant select on public.ingestion_jobs to authenticated;

do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'documents'
  ) then
    alter publication supabase_realtime add table public.documents;
  end if;
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'ingestion_jobs'
  ) then
    alter publication supabase_realtime add table public.ingestion_jobs;
  end if;
end;
$$;
