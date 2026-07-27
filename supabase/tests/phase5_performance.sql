begin;

insert into auth.users (id, aud, role, email, raw_app_meta_data, raw_user_meta_data)
values (
  '10000000-0000-4000-8000-000000000059',
  'authenticated', 'authenticated', 'phase5-perf@example.test', '{}', '{}'
);

insert into public.workspaces (id, name, created_by)
values (
  'a0000000-0000-4000-8000-000000000059',
  'Phase 5 performance',
  '10000000-0000-4000-8000-000000000059'
);

insert into public.documents (
  id, workspace_id, uploaded_by, object_path, filename, content_type,
  size_bytes, sha256, status, processing_version, index_version,
  target_index_version, chunk_strategy, embedding_model,
  embedding_dimensions, indexed_at, page_count, chunk_count, tags
)
values (
  '40000000-0000-4000-8000-000000000059',
  'a0000000-0000-4000-8000-000000000059',
  '10000000-0000-4000-8000-000000000059',
  'phase5-performance/corpus.md', 'corpus.md', 'text/markdown',
  1000000, repeat('9', 64), 'ready', 1, 1, 1, 'heading_recursive',
  'gemini-embedding-001', 768, now(), 100, 10000, array['benchmark']
);

do $$
declare
  query_vector jsonb;
begin
  select jsonb_agg(case when value = 1 then 1.0 else 0.0 end order by value)
  into query_vector
  from generate_series(1, 768) value;

  insert into public.document_chunks (
    id, workspace_id, document_id, chunk_index, processing_version, strategy,
    content, page_start, page_end, section_heading, char_start, char_end,
    token_count, embedding, embedding_model, embedded_at
  )
  select
    (
      substr(md5(item::text), 1, 8) || '-' ||
      substr(md5(item::text), 9, 4) || '-' ||
      '4' || substr(md5(item::text), 14, 3) || '-' ||
      '8' || substr(md5(item::text), 18, 3) || '-' ||
      substr(md5(item::text), 21, 12)
    )::uuid,
    'a0000000-0000-4000-8000-000000000059'::uuid,
    '40000000-0000-4000-8000-000000000059'::uuid,
    item - 1,
    1,
    'heading_recursive',
    format(
      'Benchmark retrieval chunk %s contains procedure code KEY-%s and operational guidance.',
      lpad(item::text, 5, '0'),
      lpad(item::text, 5, '0')
    ),
    ((item - 1) / 100) + 1,
    ((item - 1) / 100) + 1,
    'Benchmark',
    0,
    80,
    10,
    query_vector::text::extensions.halfvec(768),
    'gemini-embedding-001',
    now()
  from generate_series(1, 10000) item;
end;
$$;

analyze public.document_chunks;
analyze public.documents;

create temporary table phase5_latency_samples (
  sample integer primary key,
  duration_ms numeric not null
) on commit drop;

do $$
declare
  query_vector jsonb;
  started_at timestamptz;
  sample integer;
  duration numeric;
begin
  select jsonb_agg(case when value = 1 then 1.0 else 0.0 end order by value)
  into query_vector
  from generate_series(1, 768) value;

  perform public.hybrid_search(
    p_workspace_id => 'a0000000-0000-4000-8000-000000000059',
    p_actor_id => '10000000-0000-4000-8000-000000000059',
    p_request_id => gen_random_uuid(),
    p_query_text => 'procedure code KEY-05000',
    p_query_hash => repeat('a', 64),
    p_request_hash => repeat('f', 64),
    p_query_embedding => query_vector,
    p_embedding_cache_hit => true,
    p_mode => 'hybrid',
    p_match_count => 6,
    p_candidate_count => 30,
    p_cache_ttl_seconds => 0
  );

  for sample in 1..25 loop
    started_at := clock_timestamp();
    perform public.hybrid_search(
      p_workspace_id => 'a0000000-0000-4000-8000-000000000059',
      p_actor_id => '10000000-0000-4000-8000-000000000059',
      p_request_id => gen_random_uuid(),
      p_query_text => 'procedure code KEY-05000',
      p_query_hash => repeat('a', 64),
      p_request_hash => lpad(to_hex(sample), 64, '0'),
      p_query_embedding => query_vector,
      p_embedding_cache_hit => true,
      p_mode => 'hybrid',
      p_match_count => 6,
      p_candidate_count => 30,
      p_cache_ttl_seconds => 0
    );
    duration := extract(epoch from clock_timestamp() - started_at) * 1000;
    insert into phase5_latency_samples values (sample, duration);
  end loop;
end;
$$;

do $$
declare
  measured_p95 numeric;
begin
  select percentile_cont(0.95) within group (order by duration_ms)
  into measured_p95
  from phase5_latency_samples;
  if measured_p95 >= 500 then
    raise exception 'Warm retrieval p95 % ms exceeded the 500 ms budget', measured_p95;
  end if;
end;
$$;

select
  round(
    (percentile_cont(0.50) within group (order by duration_ms))::numeric,
    3
  )
    as p50_ms,
  round(
    (percentile_cont(0.95) within group (order by duration_ms))::numeric,
    3
  )
    as p95_ms,
  round(max(duration_ms), 3) as max_ms,
  count(*) as samples,
  10000 as workspace_chunks
from phase5_latency_samples;

rollback;
