begin;

insert into auth.users (id, aud, role, email, raw_app_meta_data, raw_user_meta_data)
values (
  '10000000-0000-4000-8000-000000000041',
  'authenticated',
  'authenticated',
  'phase4@example.test',
  '{"provider":"email","providers":["email"]}'::jsonb,
  '{}'::jsonb
);

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-4000-8000-000000000041","role":"authenticated","aud":"authenticated"}',
  true
);

insert into public.workspaces (id, name, created_by)
values (
  'a0000000-0000-4000-8000-000000000041',
  'Phase 4 acceptance',
  '10000000-0000-4000-8000-000000000041'
);

insert into public.document_uploads (
  id, workspace_id, uploaded_by, object_path, filename,
  expected_content_type, expected_size_bytes, expected_sha256, expires_at
)
values (
  '20000000-0000-4000-8000-000000000041',
  'a0000000-0000-4000-8000-000000000041',
  '10000000-0000-4000-8000-000000000041',
  'a0000000-0000-4000-8000-000000000041/10000000-0000-4000-8000-000000000041/20000000-0000-4000-8000-000000000041/guide.txt',
  'guide.txt', 'text/plain', 5, repeat('b', 64), now() + interval '1 hour'
);

reset role;
insert into storage.objects (bucket_id, name, owner_id)
values (
  'workspace-documents',
  'a0000000-0000-4000-8000-000000000041/10000000-0000-4000-8000-000000000041/20000000-0000-4000-8000-000000000041/guide.txt',
  '10000000-0000-4000-8000-000000000041'
);

set local role service_role;
select set_config('request.jwt.claims', '{"role":"service_role"}', true);

do $$
declare
  finalized jsonb;
  reindex_job jsonb;
  claimed record;
  document_id uuid;
  job_id uuid;
  embedding jsonb;
  source jsonb;
begin
  select jsonb_agg(case when value = 1 then 1.0 else 0.0 end order by value)
  into embedding
  from generate_series(1, 768) value;

  finalized := public.finalize_document_upload(
    '20000000-0000-4000-8000-000000000041',
    '10000000-0000-4000-8000-000000000041',
    repeat('b', 64), 5, 'text/plain',
    '90000000-0000-4000-8000-000000000041'
  );
  document_id := (finalized #>> '{document,id}')::uuid;
  job_id := (finalized #>> '{job,id}')::uuid;

  select * into claimed from public.claim_document_ingestion(120, 1);
  perform public.start_document_ingestion(job_id, claimed.msg_id);
  perform public.complete_document_ingestion(
    job_id,
    '[{"page_number":1,"content":"# Guide\n\nhello"}]'::jsonb,
    jsonb_build_array(jsonb_build_object(
      'chunk_index', 0, 'content', E'# Guide\n\nhello', 'page_start', 1, 'page_end', 1,
      'section_heading', 'Guide', 'char_start', 0, 'char_end', 14, 'token_count', 4,
      'embedding', embedding
    )),
    1, 'heading_recursive', 'gemini-embedding-001', 768
  );
  perform public.archive_document_ingestion(claimed.msg_id);

  reindex_job := public.enqueue_document_reindex(
    document_id,
    'a0000000-0000-4000-8000-000000000041',
    '10000000-0000-4000-8000-000000000041',
    '90000000-0000-4000-8000-000000000042',
    'fixed'
  );
  job_id := (reindex_job ->> 'id')::uuid;

  select * into claimed from public.claim_document_ingestion(120, 1);
  perform public.start_document_ingestion(job_id, claimed.msg_id);
  source := public.load_document_for_indexing(document_id);
  if source #>> '{pages,0,content}' <> E'# Guide\n\nhello' then
    raise exception 'Re-indexing did not retain exact source pages';
  end if;

  perform public.complete_document_ingestion(
    job_id,
    '[]'::jsonb,
    jsonb_build_array(jsonb_build_object(
      'chunk_index', 0, 'content', E'# Guide\n\nhello', 'page_start', 1, 'page_end', 1,
      'section_heading', null, 'char_start', 0, 'char_end', 14, 'token_count', 4,
      'embedding', embedding
    )),
    2, 'fixed', 'gemini-embedding-001', 768
  );
  perform public.complete_document_ingestion(
    job_id,
    '[]'::jsonb,
    jsonb_build_array(jsonb_build_object(
      'chunk_index', 0, 'content', E'# Guide\n\nhello', 'page_start', 1, 'page_end', 1,
      'section_heading', null, 'char_start', 0, 'char_end', 14, 'token_count', 4,
      'embedding', embedding
    )),
    2, 'fixed', 'gemini-embedding-001', 768
  );

  if (
    select count(*) from public.document_chunks
    where document_chunks.document_id = document_id
      and processing_version = 2
      and embedding is not null
  ) <> 1 then
    raise exception 'Version replacement was not atomic and idempotent';
  end if;
  if exists (
    select 1 from public.document_chunks
    where document_chunks.document_id = document_id
      and processing_version <> 2
  ) then
    raise exception 'Superseded chunk versions were retained';
  end if;
  if not exists (
    select 1 from public.documents
    where documents.id = document_id
      and index_version = 2
      and target_index_version = 2
      and chunk_strategy = 'fixed'
      and embedding_dimensions = 768
      and indexed_at is not null
      and status = 'ready'
  ) then
    raise exception 'Document index metadata was not committed';
  end if;

  perform public.archive_document_ingestion(claimed.msg_id);
end;
$$;

rollback;
