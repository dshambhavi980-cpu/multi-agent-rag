begin;

insert into auth.users (id, aud, role, email, raw_app_meta_data, raw_user_meta_data)
values
  (
    '10000000-0000-4000-8000-000000000051',
    'authenticated', 'authenticated', 'phase5-a@example.test', '{}', '{}'
  ),
  (
    '10000000-0000-4000-8000-000000000052',
    'authenticated', 'authenticated', 'phase5-b@example.test', '{}', '{}'
  );

insert into public.workspaces (id, name, created_by)
values
  (
    'a0000000-0000-4000-8000-000000000051',
    'Phase 5 workspace A',
    '10000000-0000-4000-8000-000000000051'
  ),
  (
    'a0000000-0000-4000-8000-000000000052',
    'Phase 5 workspace B',
    '10000000-0000-4000-8000-000000000052'
  );

insert into public.documents (
  id, workspace_id, uploaded_by, object_path, filename, content_type,
  size_bytes, sha256, status, processing_version, index_version,
  target_index_version, chunk_strategy, embedding_model,
  embedding_dimensions, indexed_at, page_count, chunk_count, tags
)
values
  (
    '40000000-0000-4000-8000-000000000051',
    'a0000000-0000-4000-8000-000000000051',
    '10000000-0000-4000-8000-000000000051',
    'phase5-a/recovery.md', 'recovery.md', 'text/markdown', 100,
    repeat('1', 64), 'ready', 1, 1, 1, 'heading_recursive',
    'gemini-embedding-001', 768, now(), 1, 1, array['support']
  ),
  (
    '40000000-0000-4000-8000-000000000052',
    'a0000000-0000-4000-8000-000000000051',
    '10000000-0000-4000-8000-000000000051',
    'phase5-a/operations.md', 'operations.md', 'text/markdown', 200,
    repeat('2', 64), 'ready', 1, 1, 1, 'heading_recursive',
    'gemini-embedding-001', 768, now(), 1, 2, array['operations']
  ),
  (
    '40000000-0000-4000-8000-000000000053',
    'a0000000-0000-4000-8000-000000000052',
    '10000000-0000-4000-8000-000000000052',
    'phase5-b/private.md', 'private.md', 'text/markdown', 100,
    repeat('3', 64), 'ready', 1, 1, 1, 'heading_recursive',
    'gemini-embedding-001', 768, now(), 1, 1, array['private']
  );

do $$
declare
  query_vector jsonb;
  exact_vector jsonb;
  relevant_vector jsonb;
  duplicate_vector jsonb;
  first_result jsonb;
  cached_result jsonb;
  dense_result jsonb;
  filtered_result jsonb;
  repeated_result jsonb;
  cached_embedding jsonb;
begin
  select jsonb_agg(case when value = 1 then 1.0 else 0.0 end order by value)
  into query_vector
  from generate_series(1, 768) value;
  exact_vector := query_vector;

  select jsonb_agg(
    case when value = 1 then 0.8 when value = 2 then 0.6 else 0.0 end
    order by value
  )
  into relevant_vector
  from generate_series(1, 768) value;

  select jsonb_agg(
    case when value = 1 then 0.79 when value = 2 then 0.61 else 0.0 end
    order by value
  )
  into duplicate_vector
  from generate_series(1, 768) value;

  perform public.put_query_embedding_cache(
    repeat('f', 64),
    'gemini-embedding-001',
    768,
    query_vector,
    60
  );
  cached_embedding := public.get_query_embedding_cache(
    repeat('f', 64),
    'gemini-embedding-001',
    768
  );
  if jsonb_array_length((cached_embedding #>> '{}')::jsonb) <> 768 then
    raise exception 'Query embedding cache did not preserve 768 dimensions';
  end if;

  insert into public.document_chunks (
    id, workspace_id, document_id, chunk_index, processing_version, strategy,
    content, page_start, page_end, section_heading, char_start, char_end,
    token_count, embedding, embedding_model, embedded_at
  )
  values
    (
      '50000000-0000-4000-8000-000000000051',
      'a0000000-0000-4000-8000-000000000051',
      '40000000-0000-4000-8000-000000000051',
      0, 1, 'heading_recursive',
      'Account recovery restores access after identity verification.',
      1, 1, 'Recovery', 0, 61, 8,
      exact_vector::text::extensions.halfvec(768),
      'gemini-embedding-001', now()
    ),
    (
      '50000000-0000-4000-8000-000000000052',
      'a0000000-0000-4000-8000-000000000051',
      '40000000-0000-4000-8000-000000000052',
      0, 1, 'heading_recursive',
      'ZX-42 reset: rotate the emergency token, then verify the audit event.',
      1, 1, 'ZX-42 procedure', 0, 68, 11,
      relevant_vector::text::extensions.halfvec(768),
      'gemini-embedding-001', now()
    ),
    (
      '50000000-0000-4000-8000-000000000053',
      'a0000000-0000-4000-8000-000000000051',
      '40000000-0000-4000-8000-000000000052',
      1, 1, 'heading_recursive',
      'ZX-42 reset: rotate the emergency token and verify the audit event.',
      1, 1, 'ZX-42 procedure', 69, 135, 11,
      duplicate_vector::text::extensions.halfvec(768),
      'gemini-embedding-001', now()
    ),
    (
      '50000000-0000-4000-8000-000000000054',
      'a0000000-0000-4000-8000-000000000052',
      '40000000-0000-4000-8000-000000000053',
      0, 1, 'heading_recursive',
      'ZX-42 reset private workspace secret.',
      1, 1, 'Private', 0, 37, 6,
      exact_vector::text::extensions.halfvec(768),
      'gemini-embedding-001', now()
    );

  first_result := public.hybrid_search(
    p_workspace_id => 'a0000000-0000-4000-8000-000000000051',
    p_actor_id => '10000000-0000-4000-8000-000000000051',
    p_request_id => '90000000-0000-4000-8000-000000000051',
    p_query_text => 'ZX-42 reset',
    p_query_hash => repeat('a', 64),
    p_request_hash => repeat('b', 64),
    p_query_embedding => query_vector,
    p_embedding_cache_hit => false,
    p_mode => 'hybrid',
    p_match_count => 3,
    p_candidate_count => 10
  );
  if (first_result ->> 'cache_hit')::boolean then
    raise exception 'First hybrid request unexpectedly hit the cache';
  end if;
  if first_result #>> '{items,0,chunk_id}'
    <> '50000000-0000-4000-8000-000000000052'
  then
    raise exception 'Hybrid search did not promote the exact ZX-42 procedure';
  end if;
  if first_result::text like '%50000000-0000-4000-8000-000000000053%' then
    raise exception 'Near-duplicate chunk was not removed';
  end if;
  if first_result::text like '%50000000-0000-4000-8000-000000000054%' then
    raise exception 'Cross-workspace chunk leaked into retrieval';
  end if;

  cached_result := public.hybrid_search(
    p_workspace_id => 'a0000000-0000-4000-8000-000000000051',
    p_actor_id => '10000000-0000-4000-8000-000000000051',
    p_request_id => '90000000-0000-4000-8000-000000000052',
    p_query_text => 'ZX-42 reset',
    p_query_hash => repeat('a', 64),
    p_request_hash => repeat('b', 64),
    p_query_embedding => query_vector,
    p_embedding_cache_hit => true,
    p_mode => 'hybrid',
    p_match_count => 3,
    p_candidate_count => 10
  );
  if not (cached_result ->> 'cache_hit')::boolean then
    raise exception 'Repeat hybrid request did not hit the cache';
  end if;
  if first_result -> 'items' <> cached_result -> 'items' then
    raise exception 'Cached retrieval changed deterministic ordering';
  end if;

  repeated_result := public.hybrid_search(
    p_workspace_id => 'a0000000-0000-4000-8000-000000000051',
    p_actor_id => '10000000-0000-4000-8000-000000000051',
    p_request_id => '90000000-0000-4000-8000-000000000056',
    p_query_text => 'ZX-42 reset',
    p_query_hash => repeat('a', 64),
    p_request_hash => repeat('6', 64),
    p_query_embedding => query_vector,
    p_embedding_cache_hit => true,
    p_mode => 'hybrid',
    p_match_count => 3,
    p_candidate_count => 10,
    p_cache_ttl_seconds => 0
  );
  if first_result -> 'items' <> repeated_result -> 'items' then
    raise exception 'Uncached retrieval changed deterministic ordering';
  end if;

  dense_result := public.hybrid_search(
    p_workspace_id => 'a0000000-0000-4000-8000-000000000051',
    p_actor_id => '10000000-0000-4000-8000-000000000051',
    p_request_id => '90000000-0000-4000-8000-000000000053',
    p_query_text => 'ZX-42 reset',
    p_query_hash => repeat('a', 64),
    p_request_hash => repeat('c', 64),
    p_query_embedding => query_vector,
    p_embedding_cache_hit => true,
    p_mode => 'dense',
    p_match_count => 3,
    p_candidate_count => 10
  );
  if dense_result #>> '{items,0,chunk_id}'
    <> '50000000-0000-4000-8000-000000000051'
  then
    raise exception 'Dense benchmark did not retain its semantic distractor';
  end if;

  filtered_result := public.hybrid_search(
    p_workspace_id => 'a0000000-0000-4000-8000-000000000051',
    p_actor_id => '10000000-0000-4000-8000-000000000051',
    p_request_id => '90000000-0000-4000-8000-000000000054',
    p_query_text => 'ZX-42 reset',
    p_query_hash => repeat('a', 64),
    p_request_hash => repeat('d', 64),
    p_query_embedding => query_vector,
    p_embedding_cache_hit => true,
    p_mode => 'hybrid',
    p_match_count => 3,
    p_candidate_count => 10,
    p_tags => array['operations']
  );
  if exists (
    select 1
    from jsonb_array_elements(filtered_result -> 'items') item
    where item ->> 'document_id' <> '40000000-0000-4000-8000-000000000052'
  ) then
    raise exception 'Tag filter returned another document';
  end if;

  begin
    perform public.hybrid_search(
      p_workspace_id => 'a0000000-0000-4000-8000-000000000051',
      p_actor_id => '10000000-0000-4000-8000-000000000052',
      p_request_id => '90000000-0000-4000-8000-000000000055',
      p_query_text => 'ZX-42 reset',
      p_query_hash => repeat('a', 64),
      p_request_hash => repeat('e', 64),
      p_query_embedding => query_vector,
      p_embedding_cache_hit => false
    );
    raise exception 'Non-member hybrid search unexpectedly succeeded';
  exception
    when insufficient_privilege then null;
  end;

  if (
    select count(*) from public.retrieval_traces
    where workspace_id = 'a0000000-0000-4000-8000-000000000051'
  ) <> 5 then
    raise exception 'Retrieval trace count did not match executed searches';
  end if;
  if exists (
    select 1 from public.retrieval_traces
    where rankings::text like '%ZX-42%'
  ) then
    raise exception 'Ranking traces persisted raw query or content';
  end if;

  update public.documents
  set tags = array_append(tags, 'changed')
  where id = '40000000-0000-4000-8000-000000000052';
  if exists (
    select 1 from public.retrieval_cache
    where workspace_id = 'a0000000-0000-4000-8000-000000000051'
  ) then
    raise exception 'Document metadata change did not invalidate retrieval cache';
  end if;
end;
$$;

rollback;
