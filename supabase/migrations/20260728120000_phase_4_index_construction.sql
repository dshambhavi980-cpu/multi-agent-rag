create table public.index_profiles (
  version integer primary key,
  strategy text not null,
  target_chars integer not null,
  overlap_chars integer not null default 0,
  embedding_model text not null,
  embedding_dimensions integer not null,
  is_active boolean not null default false,
  created_at timestamptz not null default now(),
  constraint index_profiles_version check (version > 0),
  constraint index_profiles_strategy
    check (strategy in ('fixed', 'recursive', 'heading_recursive')),
  constraint index_profiles_target_chars check (target_chars between 256 and 4000),
  constraint index_profiles_overlap_chars
    check (overlap_chars >= 0 and overlap_chars < target_chars),
  constraint index_profiles_dimensions check (embedding_dimensions = 768)
);

create unique index index_profiles_one_active_idx
  on public.index_profiles (is_active)
  where is_active;

insert into public.index_profiles (
  version,
  strategy,
  target_chars,
  overlap_chars,
  embedding_model,
  embedding_dimensions,
  is_active
)
values (
  1,
  'heading_recursive',
  1800,
  0,
  'gemini-embedding-001',
  768,
  true
);

alter table public.index_profiles enable row level security;
revoke all on table public.index_profiles from public, anon, authenticated;
grant select on table public.index_profiles to service_role;

alter table public.documents
  add column index_version integer not null default 0,
  add column target_index_version integer not null default 1,
  add column chunk_strategy text,
  add column embedding_model text,
  add column embedding_dimensions integer,
  add column indexed_at timestamptz,
  add constraint documents_index_versions
    check (
      index_version >= 0
      and target_index_version > 0
      and target_index_version >= index_version
    ),
  add constraint documents_chunk_strategy
    check (
      chunk_strategy is null
      or chunk_strategy in ('fixed', 'recursive', 'heading_recursive')
    ),
  add constraint documents_embedding_dimensions
    check (embedding_dimensions is null or embedding_dimensions = 768);

alter table public.document_chunks
  add column embedding extensions.halfvec(768),
  add column embedding_model text,
  add column embedded_at timestamptz;

alter table public.document_chunks
  add constraint document_chunks_strategy
    check (strategy in ('provenance_v1', 'fixed', 'recursive', 'heading_recursive')),
  add constraint document_chunks_embedding_metadata
    check (
      (embedding is null and embedding_model is null and embedded_at is null)
      or (embedding is not null and embedding_model is not null and embedded_at is not null)
    );

create index document_chunks_embedding_hnsw_idx
  on public.document_chunks
  using hnsw (embedding extensions.halfvec_cosine_ops)
  where embedding is not null;

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
    or (old.status = 'ready' and new.status = 'queued')
    or (old.status in ('failed', 'quarantined') and new.status = 'queued')
  ) then
    raise exception 'Invalid document status transition: % -> %', old.status, new.status
      using errcode = '23514';
  end if;
  return new;
end;
$$;

revoke execute on function app_private.validate_document_status_transition()
  from public, anon, authenticated, service_role;

drop function public.complete_document_ingestion(uuid, jsonb, jsonb);

create or replace function public.update_document_ingestion_progress(
  p_job_id uuid,
  p_stage text,
  p_progress numeric
)
returns boolean
language sql
security definer
set search_path = ''
as $$
  update public.ingestion_jobs
  set stage = left(p_stage, 80),
      progress = least(greatest(p_progress, 0), 0.99)
  where id = p_job_id
    and status = 'processing'
  returning true;
$$;

create or replace function public.load_document_for_indexing(p_document_id uuid)
returns jsonb
language sql
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'document', to_jsonb(document),
    'pages', coalesce(
      (
        select jsonb_agg(
          jsonb_build_object(
            'page_number', page.page_number,
            'content', page.content
          )
          order by page.page_number
        )
        from public.document_pages page
        where page.document_id = document.id
      ),
      '[]'::jsonb
    )
  )
  from public.documents document
  where document.id = p_document_id;
$$;

create or replace function public.complete_document_ingestion(
  p_job_id uuid,
  p_pages jsonb,
  p_chunks jsonb,
  p_index_version integer,
  p_strategy text,
  p_embedding_model text,
  p_embedding_dimensions integer
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
  if p_index_version <= 0
    or p_index_version <> (
      select target_index_version
      from public.documents
      where id = job_row.document_id
    )
  then
    raise exception 'Index version does not match the document target.'
      using errcode = '22023';
  end if;
  if p_strategy not in ('fixed', 'recursive', 'heading_recursive')
    or p_embedding_dimensions <> 768
    or nullif(trim(p_embedding_model), '') is null
  then
    raise exception 'Invalid index profile.' using errcode = '22023';
  end if;
  if jsonb_array_length(coalesce(p_pages, '[]'::jsonb)) > 1000
    or jsonb_array_length(coalesce(p_chunks, '[]'::jsonb)) > 10000
  then
    raise exception 'Indexed output exceeds the configured limits.'
      using errcode = '54000';
  end if;
  if exists (
    select 1
    from jsonb_array_elements(coalesce(p_chunks, '[]'::jsonb)) chunk
    where jsonb_array_length(chunk -> 'embedding') <> 768
  ) then
    raise exception 'Embedding dimension mismatch.' using errcode = '22023';
  end if;

  select * into document_row
  from public.documents
  where id = job_row.document_id
  for update;

  if jsonb_array_length(coalesce(p_pages, '[]'::jsonb)) > 0 then
    delete from public.document_pages where document_id = document_row.id;
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
    from jsonb_to_recordset(p_pages)
      as parsed(page_number integer, content text);
  end if;

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
    token_count,
    embedding,
    embedding_model,
    embedded_at
  )
  select document_row.workspace_id,
         document_row.id,
         parsed.chunk_index,
         p_index_version,
         p_strategy,
         parsed.content,
         parsed.page_start,
         parsed.page_end,
         parsed.section_heading,
         parsed.char_start,
         parsed.char_end,
         parsed.token_count,
         parsed.embedding::extensions.halfvec(768),
         p_embedding_model,
         now()
  from jsonb_to_recordset(coalesce(p_chunks, '[]'::jsonb))
    as parsed(
      chunk_index integer,
      content text,
      page_start integer,
      page_end integer,
      section_heading text,
      char_start integer,
      char_end integer,
      token_count integer,
      embedding text
    )
  on conflict (document_id, processing_version, chunk_index)
  do update set
    strategy = excluded.strategy,
    content = excluded.content,
    page_start = excluded.page_start,
    page_end = excluded.page_end,
    section_heading = excluded.section_heading,
    char_start = excluded.char_start,
    char_end = excluded.char_end,
    token_count = excluded.token_count,
    embedding = excluded.embedding,
    embedding_model = excluded.embedding_model,
    embedded_at = excluded.embedded_at;

  delete from public.document_chunks
  where document_id = document_row.id
    and processing_version <> p_index_version;

  update public.documents
  set status = 'ready',
      processing_version = p_index_version,
      index_version = p_index_version,
      target_index_version = p_index_version,
      chunk_strategy = p_strategy,
      embedding_model = p_embedding_model,
      embedding_dimensions = p_embedding_dimensions,
      indexed_at = now(),
      page_count = (
        select count(*) from public.document_pages
        where document_id = document_row.id
      ),
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

create or replace function public.enqueue_document_reindex(
  p_document_id uuid,
  p_workspace_id uuid,
  p_actor_id uuid,
  p_request_id uuid,
  p_strategy text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  document_row public.documents;
  profile_row public.index_profiles;
  job_row public.ingestion_jobs;
  message_id bigint;
  next_version integer;
begin
  if not exists (
    select 1
    from public.workspace_members member
    where member.workspace_id = p_workspace_id
      and member.user_id = p_actor_id
      and member.role = 'owner'
  ) then
    raise exception 'Workspace owner access is required.' using errcode = '42501';
  end if;

  select * into document_row
  from public.documents
  where id = p_document_id
    and workspace_id = p_workspace_id
  for update;

  if document_row.id is null then
    raise exception 'Document not found.' using errcode = 'P0002';
  end if;
  if document_row.status <> 'ready' then
    raise exception 'Only ready documents can be re-indexed.' using errcode = '55000';
  end if;
  if exists (
    select 1 from public.ingestion_jobs
    where document_id = document_row.id
      and status in ('queued', 'processing')
  ) then
    raise exception 'An indexing job is already active.' using errcode = '55000';
  end if;

  select * into profile_row
  from public.index_profiles
  where is_active;
  next_version := greatest(document_row.index_version + 1, profile_row.version);

  update public.documents
  set status = 'queued',
      target_index_version = next_version,
      processing_version = next_version,
      failure_code = null,
      failure_detail = null
  where id = document_row.id
  returning * into document_row;

  insert into public.ingestion_jobs (
    workspace_id, document_id, status, stage, progress
  )
  values (
    document_row.workspace_id, document_row.id, 'queued', 'queued', 0
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
      'processing_version', next_version,
      'strategy', coalesce(p_strategy, profile_row.strategy),
      'reindex', true
    ),
    delay => 0
  ) into message_id;

  update public.ingestion_jobs
  set queue_message_id = message_id
  where id = job_row.id
  returning * into job_row;

  insert into public.application_events (
    workspace_id, actor_id, event_type, target_type, target_id, request_id, metadata
  )
  values (
    document_row.workspace_id,
    p_actor_id,
    'document.reindex_queued',
    'document',
    document_row.id,
    p_request_id,
    jsonb_build_object(
      'job_id', job_row.id,
      'index_version', next_version,
      'strategy', coalesce(p_strategy, profile_row.strategy)
    )
  );

  return to_jsonb(job_row);
end;
$$;

create or replace function public.enqueue_workspace_reindex(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_request_id uuid,
  p_strategy text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  document_row record;
  jobs jsonb := '[]'::jsonb;
begin
  for document_row in
    select id
    from public.documents
    where workspace_id = p_workspace_id
      and status = 'ready'
    order by created_at
  loop
    jobs := jobs || jsonb_build_array(
      public.enqueue_document_reindex(
        document_row.id,
        p_workspace_id,
        p_actor_id,
        p_request_id,
        p_strategy
      )
    );
  end loop;
  return jobs;
end;
$$;

revoke execute on function public.update_document_ingestion_progress(uuid, text, numeric)
  from public, anon, authenticated;
revoke execute on function public.load_document_for_indexing(uuid)
  from public, anon, authenticated;
revoke execute on function public.complete_document_ingestion(
  uuid, jsonb, jsonb, integer, text, text, integer
) from public, anon, authenticated;
revoke execute on function public.enqueue_document_reindex(
  uuid, uuid, uuid, uuid, text
) from public, anon, authenticated;
revoke execute on function public.enqueue_workspace_reindex(
  uuid, uuid, uuid, text
) from public, anon, authenticated;

grant execute on function public.update_document_ingestion_progress(uuid, text, numeric)
  to service_role;
grant execute on function public.load_document_for_indexing(uuid)
  to service_role;
grant execute on function public.complete_document_ingestion(
  uuid, jsonb, jsonb, integer, text, text, integer
) to service_role;
grant execute on function public.enqueue_document_reindex(
  uuid, uuid, uuid, uuid, text
) to service_role;
grant execute on function public.enqueue_workspace_reindex(
  uuid, uuid, uuid, text
) to service_role;
