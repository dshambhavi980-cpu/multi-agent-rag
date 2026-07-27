begin;

insert into auth.users (id, aud, role, email, raw_app_meta_data, raw_user_meta_data)
values (
  '10000000-0000-4000-8000-000000000031',
  'authenticated',
  'authenticated',
  'phase3@example.test',
  '{"provider":"email","providers":["email"]}'::jsonb,
  '{}'::jsonb
);

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-4000-8000-000000000031","role":"authenticated","aud":"authenticated"}',
  true
);

insert into public.workspaces (id, name, created_by)
values (
  'a0000000-0000-4000-8000-000000000031',
  'Phase 3 acceptance',
  '10000000-0000-4000-8000-000000000031'
);

insert into public.document_uploads (
  id, workspace_id, uploaded_by, object_path, filename,
  expected_content_type, expected_size_bytes, expected_sha256, expires_at
)
values
  (
    '20000000-0000-4000-8000-000000000031',
    'a0000000-0000-4000-8000-000000000031',
    '10000000-0000-4000-8000-000000000031',
    'a0000000-0000-4000-8000-000000000031/10000000-0000-4000-8000-000000000031/20000000-0000-4000-8000-000000000031/guide.txt',
    'guide.txt', 'text/plain', 5, repeat('a', 64), now() + interval '1 hour'
  ),
  (
    '20000000-0000-4000-8000-000000000032',
    'a0000000-0000-4000-8000-000000000031',
    '10000000-0000-4000-8000-000000000031',
    'a0000000-0000-4000-8000-000000000031/10000000-0000-4000-8000-000000000031/20000000-0000-4000-8000-000000000032/guide.txt',
    'guide.txt', 'text/plain', 5, repeat('a', 64), now() + interval '1 hour'
  );

reset role;
insert into storage.objects (bucket_id, name, owner_id)
values
  (
    'workspace-documents',
    'a0000000-0000-4000-8000-000000000031/10000000-0000-4000-8000-000000000031/20000000-0000-4000-8000-000000000031/guide.txt',
    '10000000-0000-4000-8000-000000000031'
  ),
  (
    'workspace-documents',
    'a0000000-0000-4000-8000-000000000031/10000000-0000-4000-8000-000000000031/20000000-0000-4000-8000-000000000032/guide.txt',
    '10000000-0000-4000-8000-000000000031'
  );

set local role service_role;
select set_config('request.jwt.claims', '{"role":"service_role"}', true);

do $$
declare
  first_result jsonb;
  duplicate_result jsonb;
  claimed record;
  job_id uuid;
  target_document_id uuid;
  stored_chunks integer;
  embedding jsonb;
begin
  select jsonb_agg(case when value = 1 then 1.0 else 0.0 end order by value)
  into embedding
  from generate_series(1, 768) value;

  first_result := public.finalize_document_upload(
    '20000000-0000-4000-8000-000000000031',
    '10000000-0000-4000-8000-000000000031',
    repeat('a', 64), 5, 'text/plain',
    '90000000-0000-4000-8000-000000000031'
  );
  if (first_result ->> 'deduplicated')::boolean then
    raise exception 'First upload was unexpectedly deduplicated';
  end if;
  job_id := (first_result #>> '{job,id}')::uuid;
  target_document_id := (first_result #>> '{document,id}')::uuid;

  select * into claimed
  from public.claim_document_ingestion(120, 1);
  if claimed.msg_id is null then
    raise exception 'The queued ingestion job could not be claimed';
  end if;
  if not (
    public.start_document_ingestion(job_id, claimed.msg_id) ->> 'should_process'
  )::boolean then
    raise exception 'The claimed ingestion job did not start';
  end if;

  perform public.complete_document_ingestion(
    job_id,
    '[{"page_number":1,"content":"hello"}]'::jsonb,
    jsonb_build_array(jsonb_build_object(
      'chunk_index', 0, 'content', 'hello', 'page_start', 1, 'page_end', 1,
      'section_heading', null, 'char_start', 0, 'char_end', 5, 'token_count', 1,
      'embedding', embedding
    )),
    1,
    'heading_recursive',
    'gemini-embedding-001',
    768
  );
  perform public.complete_document_ingestion(
    job_id,
    '[{"page_number":1,"content":"hello"}]'::jsonb,
    jsonb_build_array(jsonb_build_object(
      'chunk_index', 0, 'content', 'hello', 'page_start', 1, 'page_end', 1,
      'section_heading', null, 'char_start', 0, 'char_end', 5, 'token_count', 1,
      'embedding', embedding
    )),
    1,
    'heading_recursive',
    'gemini-embedding-001',
    768
  );

  select count(*) into stored_chunks
  from public.document_chunks as chunk
  where chunk.document_id = target_document_id;
  if stored_chunks <> 1 then
    raise exception 'Idempotent completion stored % chunks', stored_chunks;
  end if;

  duplicate_result := public.finalize_document_upload(
    '20000000-0000-4000-8000-000000000032',
    '10000000-0000-4000-8000-000000000031',
    repeat('a', 64), 5, 'text/plain',
    '90000000-0000-4000-8000-000000000032'
  );
  if not (duplicate_result ->> 'deduplicated')::boolean then
    raise exception 'Second upload was not deduplicated';
  end if;
  if (select count(*) from public.documents where workspace_id =
      'a0000000-0000-4000-8000-000000000031') <> 1 then
    raise exception 'Checksum deduplication created duplicate documents';
  end if;

  perform public.archive_document_ingestion(claimed.msg_id);
end;
$$;

rollback;
