create extension if not exists pg_trgm with schema extensions;

create table public.query_embedding_cache (
  query_hash text not null,
  embedding_model text not null,
  embedding_dimensions integer not null,
  embedding extensions.halfvec(768) not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  hit_count bigint not null default 0,
  primary key (query_hash, embedding_model, embedding_dimensions),
  constraint query_embedding_cache_hash
    check (query_hash ~ '^[a-f0-9]{64}$'),
  constraint query_embedding_cache_dimensions
    check (embedding_dimensions = 768),
  constraint query_embedding_cache_expiry
    check (expires_at > created_at),
  constraint query_embedding_cache_hit_count
    check (hit_count >= 0)
);

create index query_embedding_cache_expiry_idx
  on public.query_embedding_cache (expires_at);

create table public.retrieval_cache (
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  request_hash text not null,
  index_fingerprint text not null,
  response jsonb not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  hit_count bigint not null default 0,
  primary key (workspace_id, request_hash, index_fingerprint),
  constraint retrieval_cache_request_hash
    check (request_hash ~ '^[a-f0-9]{64}$'),
  constraint retrieval_cache_index_fingerprint
    check (index_fingerprint ~ '^[a-f0-9]{32}$'),
  constraint retrieval_cache_response_object
    check (jsonb_typeof(response) = 'object'),
  constraint retrieval_cache_expiry
    check (expires_at > created_at),
  constraint retrieval_cache_hit_count
    check (hit_count >= 0)
);

create index retrieval_cache_expiry_idx
  on public.retrieval_cache (expires_at);

create table public.retrieval_traces (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  actor_id uuid not null references auth.users (id) on delete cascade,
  request_id uuid not null,
  query_hash text not null,
  request_hash text not null,
  mode text not null,
  filters jsonb not null default '{}'::jsonb,
  index_fingerprint text not null,
  embedding_cache_hit boolean not null,
  retrieval_cache_hit boolean not null,
  dense_candidate_count integer not null,
  sparse_candidate_count integer not null,
  selected_count integer not null,
  rankings jsonb not null default '[]'::jsonb,
  embedding_ms numeric(10, 3),
  database_ms numeric(10, 3),
  total_ms numeric(10, 3),
  created_at timestamptz not null default now(),
  constraint retrieval_traces_query_hash
    check (query_hash ~ '^[a-f0-9]{64}$'),
  constraint retrieval_traces_request_hash
    check (request_hash ~ '^[a-f0-9]{64}$'),
  constraint retrieval_traces_mode
    check (mode in ('hybrid', 'dense', 'sparse')),
  constraint retrieval_traces_filters_object
    check (jsonb_typeof(filters) = 'object'),
  constraint retrieval_traces_index_fingerprint
    check (index_fingerprint ~ '^[a-f0-9]{32}$'),
  constraint retrieval_traces_candidate_counts
    check (
      dense_candidate_count >= 0
      and sparse_candidate_count >= 0
      and selected_count >= 0
    ),
  constraint retrieval_traces_rankings_array
    check (jsonb_typeof(rankings) = 'array'),
  constraint retrieval_traces_durations
    check (
      (embedding_ms is null or embedding_ms >= 0)
      and (database_ms is null or database_ms >= 0)
      and (total_ms is null or total_ms >= 0)
    )
);

create index retrieval_traces_workspace_created_idx
  on public.retrieval_traces (workspace_id, created_at desc);
create index retrieval_traces_actor_created_idx
  on public.retrieval_traces (actor_id, created_at desc);

alter table public.query_embedding_cache enable row level security;
alter table public.retrieval_cache enable row level security;
alter table public.retrieval_traces enable row level security;

revoke all on table public.query_embedding_cache from public, anon, authenticated;
revoke all on table public.retrieval_cache from public, anon, authenticated;
revoke all on table public.retrieval_traces from public, anon, authenticated;

grant all on table public.query_embedding_cache to service_role;
grant all on table public.retrieval_cache to service_role;
grant select, insert, update, delete on table public.retrieval_traces to service_role;
grant select on table public.retrieval_traces to authenticated;

create policy retrieval_traces_select_authorized
on public.retrieval_traces
for select
to authenticated
using (
  (select app_private.has_workspace_role(
    workspace_id,
    array['owner', 'reviewer']::public.workspace_role[]
  ))
);

create or replace function public.get_query_embedding_cache(
  p_query_hash text,
  p_embedding_model text,
  p_embedding_dimensions integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  cached_embedding extensions.halfvec(768);
begin
  delete from public.query_embedding_cache
  where query_hash = p_query_hash
    and embedding_model = p_embedding_model
    and embedding_dimensions = p_embedding_dimensions
    and expires_at <= now();

  update public.query_embedding_cache
  set hit_count = hit_count + 1
  where query_hash = p_query_hash
    and embedding_model = p_embedding_model
    and embedding_dimensions = p_embedding_dimensions
    and expires_at > now()
  returning embedding into cached_embedding;

  if cached_embedding is null then
    return null;
  end if;
  return to_jsonb(cached_embedding::text);
end;
$$;

create or replace function public.put_query_embedding_cache(
  p_query_hash text,
  p_embedding_model text,
  p_embedding_dimensions integer,
  p_embedding jsonb,
  p_ttl_seconds integer
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_query_hash !~ '^[a-f0-9]{64}$'
    or p_embedding_dimensions <> 768
    or p_ttl_seconds not between 60 and 604800
    or jsonb_array_length(p_embedding) <> 768
  then
    raise exception 'Invalid query embedding cache entry.' using errcode = '22023';
  end if;

  insert into public.query_embedding_cache (
    query_hash,
    embedding_model,
    embedding_dimensions,
    embedding,
    expires_at
  )
  values (
    p_query_hash,
    p_embedding_model,
    p_embedding_dimensions,
    p_embedding::text::extensions.halfvec(768),
    now() + make_interval(secs => p_ttl_seconds)
  )
  on conflict (query_hash, embedding_model, embedding_dimensions)
  do update set
    embedding = excluded.embedding,
    created_at = now(),
    expires_at = excluded.expires_at,
    hit_count = 0;
  return true;
end;
$$;

create or replace function public.hybrid_search(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_request_id uuid,
  p_query_text text,
  p_query_hash text,
  p_request_hash text,
  p_query_embedding jsonb,
  p_embedding_cache_hit boolean,
  p_mode text default 'hybrid',
  p_match_count integer default 6,
  p_candidate_count integer default 30,
  p_rrf_k integer default 60,
  p_dense_weight numeric default 1,
  p_sparse_weight numeric default 1,
  p_duplicate_threshold numeric default 0.92,
  p_document_ids uuid[] default null,
  p_created_after timestamptz default null,
  p_created_before timestamptz default null,
  p_content_types text[] default null,
  p_tags text[] default null,
  p_cache_ttl_seconds integer default 900,
  p_filters jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  query_vector extensions.halfvec(768);
  fingerprint text;
  cached_response jsonb;
  response_body jsonb;
  trace_id uuid := gen_random_uuid();
  dense_count integer := 0;
  sparse_count integer := 0;
  selected_count integer := 0;
  ranking_trace jsonb := '[]'::jsonb;
begin
  if not exists (
    select 1
    from public.workspace_members member
    where member.workspace_id = p_workspace_id
      and member.user_id = p_actor_id
  ) then
    raise exception 'Workspace access is required.' using errcode = '42501';
  end if;
  if nullif(trim(p_query_text), '') is null
    or char_length(p_query_text) > 2000
    or p_query_hash !~ '^[a-f0-9]{64}$'
    or p_request_hash !~ '^[a-f0-9]{64}$'
    or p_mode not in ('hybrid', 'dense', 'sparse')
    or p_match_count not between 1 and 20
    or p_candidate_count not between p_match_count and 100
    or p_rrf_k not between 1 and 1000
    or p_dense_weight < 0
    or p_sparse_weight < 0
    or p_duplicate_threshold not between 0.8 and 1
    or p_cache_ttl_seconds not between 0 and 3600
    or jsonb_array_length(p_query_embedding) <> 768
    or jsonb_typeof(p_filters) <> 'object'
  then
    raise exception 'Invalid hybrid search request.' using errcode = '22023';
  end if;

  query_vector := p_query_embedding::text::extensions.halfvec(768);
  select md5(coalesce(string_agg(
    document.id::text || ':' || document.index_version::text,
    ',' order by document.id
  ), 'empty'))
  into fingerprint
  from public.documents document
  where document.workspace_id = p_workspace_id
    and document.status = 'ready';

  if p_cache_ttl_seconds > 0 then
    delete from public.retrieval_cache
    where workspace_id = p_workspace_id
      and request_hash = p_request_hash
      and index_fingerprint = fingerprint
      and expires_at <= now();

    update public.retrieval_cache
    set hit_count = hit_count + 1
    where workspace_id = p_workspace_id
      and request_hash = p_request_hash
      and index_fingerprint = fingerprint
      and expires_at > now()
    returning response into cached_response;
  end if;

  if cached_response is not null then
    dense_count := coalesce((cached_response ->> 'dense_candidate_count')::integer, 0);
    sparse_count := coalesce((cached_response ->> 'sparse_candidate_count')::integer, 0);
    selected_count := jsonb_array_length(coalesce(cached_response -> 'items', '[]'::jsonb));
    ranking_trace := coalesce(cached_response -> 'rankings', '[]'::jsonb);

    insert into public.retrieval_traces (
      id, workspace_id, actor_id, request_id, query_hash, request_hash, mode,
      filters, index_fingerprint, embedding_cache_hit, retrieval_cache_hit,
      dense_candidate_count, sparse_candidate_count, selected_count, rankings
    )
    values (
      trace_id, p_workspace_id, p_actor_id, p_request_id, p_query_hash,
      p_request_hash, p_mode, p_filters, fingerprint, p_embedding_cache_hit,
      true, dense_count, sparse_count, selected_count, ranking_trace
    );

    return (cached_response - 'rankings')
      || jsonb_build_object('trace_id', trace_id, 'cache_hit', true);
  end if;

  perform set_config('hnsw.iterative_scan', 'relaxed_order', true);

  with
  semantic as materialized (
    select
      chunk.id,
      1 - (chunk.embedding <=> query_vector) as semantic_score,
      row_number() over (
        order by chunk.embedding <=> query_vector, chunk.id
      )::integer as semantic_rank
    from public.document_chunks chunk
    join public.documents document
      on document.id = chunk.document_id
      and document.workspace_id = chunk.workspace_id
    where p_mode <> 'sparse'
      and chunk.workspace_id = p_workspace_id
      and chunk.embedding is not null
      and document.status = 'ready'
      and chunk.processing_version = document.index_version
      and (p_document_ids is null or chunk.document_id = any(p_document_ids))
      and (p_created_after is null or document.created_at >= p_created_after)
      and (p_created_before is null or document.created_at < p_created_before)
      and (p_content_types is null or document.content_type = any(p_content_types))
      and (p_tags is null or document.tags && p_tags)
    order by chunk.embedding <=> query_vector, chunk.id
    limit p_candidate_count
  ),
  sparse as materialized (
    select
      chunk.id,
      ts_rank_cd(
        chunk.search_vector,
        websearch_to_tsquery('english', p_query_text),
        32
      ) as sparse_score,
      row_number() over (
        order by
          ts_rank_cd(
            chunk.search_vector,
            websearch_to_tsquery('english', p_query_text),
            32
          ) desc,
          chunk.id
      )::integer as sparse_rank
    from public.document_chunks chunk
    join public.documents document
      on document.id = chunk.document_id
      and document.workspace_id = chunk.workspace_id
    where p_mode <> 'dense'
      and chunk.workspace_id = p_workspace_id
      and document.status = 'ready'
      and chunk.processing_version = document.index_version
      and chunk.search_vector @@ websearch_to_tsquery('english', p_query_text)
      and (p_document_ids is null or chunk.document_id = any(p_document_ids))
      and (p_created_after is null or document.created_at >= p_created_after)
      and (p_created_before is null or document.created_at < p_created_before)
      and (p_content_types is null or document.content_type = any(p_content_types))
      and (p_tags is null or document.tags && p_tags)
    order by sparse_score desc, chunk.id
    limit p_candidate_count
  ),
  fused as materialized (
    select
      coalesce(semantic.id, sparse.id) as id,
      semantic.semantic_rank,
      sparse.sparse_rank,
      semantic.semantic_score,
      sparse.sparse_score,
      (
        case when semantic.semantic_rank is null then 0
          else p_dense_weight / (p_rrf_k + semantic.semantic_rank)
        end
        +
        case when sparse.sparse_rank is null then 0
          else p_sparse_weight / (p_rrf_k + sparse.sparse_rank)
        end
      )::numeric as rrf_score
    from semantic
    full outer join sparse on sparse.id = semantic.id
  ),
  enriched as materialized (
    select
      fused.*,
      chunk.workspace_id,
      chunk.document_id,
      chunk.chunk_index,
      chunk.content,
      chunk.page_start,
      chunk.page_end,
      chunk.section_heading,
      chunk.char_start,
      chunk.char_end,
      chunk.token_count,
      document.filename,
      document.title,
      document.content_type,
      document.tags,
      document.created_at as document_created_at
    from fused
    join public.document_chunks chunk on chunk.id = fused.id
    join public.documents document on document.id = chunk.document_id
  ),
  deduplicated as materialized (
    select candidate.*
    from enriched candidate
    where not exists (
      select 1
      from enriched better
      where better.id <> candidate.id
        and better.document_id = candidate.document_id
        and (
          better.rrf_score > candidate.rrf_score
          or (better.rrf_score = candidate.rrf_score and better.id < candidate.id)
        )
        and extensions.similarity(better.content, candidate.content)
          >= p_duplicate_threshold
    )
  ),
  selected as materialized (
    select
      deduplicated.*,
      row_number() over (
        order by rrf_score desc, id
      )::integer as final_rank
    from deduplicated
    order by rrf_score desc, id
    limit p_match_count
  )
  select
    (select count(*) from semantic),
    (select count(*) from sparse),
    (select count(*) from selected),
    coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'chunk_id', selected.id,
          'document_id', selected.document_id,
          'chunk_index', selected.chunk_index,
          'content', selected.content,
          'page_start', selected.page_start,
          'page_end', selected.page_end,
          'section_heading', selected.section_heading,
          'char_start', selected.char_start,
          'char_end', selected.char_end,
          'token_count', selected.token_count,
          'filename', selected.filename,
          'title', selected.title,
          'content_type', selected.content_type,
          'tags', selected.tags,
          'document_created_at', selected.document_created_at,
          'semantic_rank', selected.semantic_rank,
          'sparse_rank', selected.sparse_rank,
          'semantic_score', selected.semantic_score,
          'sparse_score', selected.sparse_score,
          'rrf_score', selected.rrf_score,
          'final_rank', selected.final_rank
        )
        order by selected.final_rank
      )
      from selected
    ), '[]'::jsonb),
    coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'chunk_id', selected.id,
          'semantic_rank', selected.semantic_rank,
          'sparse_rank', selected.sparse_rank,
          'rrf_score', selected.rrf_score,
          'final_rank', selected.final_rank
        )
        order by selected.final_rank
      )
      from selected
    ), '[]'::jsonb)
  into dense_count, sparse_count, selected_count, response_body, ranking_trace;

  response_body := jsonb_build_object(
    'index_fingerprint', fingerprint,
    'dense_candidate_count', dense_count,
    'sparse_candidate_count', sparse_count,
    'items', response_body,
    'rankings', ranking_trace
  );

  if p_cache_ttl_seconds > 0 then
    insert into public.retrieval_cache (
      workspace_id, request_hash, index_fingerprint, response, expires_at
    )
    values (
      p_workspace_id,
      p_request_hash,
      fingerprint,
      response_body,
      now() + make_interval(secs => p_cache_ttl_seconds)
    )
    on conflict (workspace_id, request_hash, index_fingerprint)
    do update set
      response = excluded.response,
      created_at = now(),
      expires_at = excluded.expires_at,
      hit_count = 0;
  end if;

  insert into public.retrieval_traces (
    id, workspace_id, actor_id, request_id, query_hash, request_hash, mode,
    filters, index_fingerprint, embedding_cache_hit, retrieval_cache_hit,
    dense_candidate_count, sparse_candidate_count, selected_count, rankings
  )
  values (
    trace_id, p_workspace_id, p_actor_id, p_request_id, p_query_hash,
    p_request_hash, p_mode, p_filters, fingerprint, p_embedding_cache_hit,
    false, dense_count, sparse_count, selected_count, ranking_trace
  );

  delete from public.retrieval_traces trace
  where trace.workspace_id = p_workspace_id
    and (
      trace.created_at < now() - interval '30 days'
      or trace.id in (
        select older.id
        from public.retrieval_traces older
        where older.workspace_id = p_workspace_id
        order by older.created_at desc, older.id
        offset 50
      )
    );

  return (response_body - 'rankings')
    || jsonb_build_object('trace_id', trace_id, 'cache_hit', false);
end;
$$;

create or replace function public.update_retrieval_trace_timings(
  p_trace_id uuid,
  p_workspace_id uuid,
  p_actor_id uuid,
  p_embedding_ms numeric,
  p_database_ms numeric,
  p_total_ms numeric
)
returns boolean
language sql
security definer
set search_path = ''
as $$
  update public.retrieval_traces
  set embedding_ms = greatest(p_embedding_ms, 0),
      database_ms = greatest(p_database_ms, 0),
      total_ms = greatest(p_total_ms, 0)
  where id = p_trace_id
    and workspace_id = p_workspace_id
    and actor_id = p_actor_id
  returning true;
$$;

create or replace function app_private.invalidate_workspace_retrieval_cache()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  affected_workspace_id uuid;
begin
  affected_workspace_id := case
    when tg_op = 'DELETE' then old.workspace_id
    else new.workspace_id
  end;
  delete from public.retrieval_cache
  where workspace_id = affected_workspace_id;
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

create trigger documents_invalidate_retrieval_cache
after insert or delete or update of index_version, status, tags, content_type
on public.documents
for each row execute function app_private.invalidate_workspace_retrieval_cache();

revoke execute on function public.get_query_embedding_cache(text, text, integer)
  from public, anon, authenticated;
revoke execute on function public.put_query_embedding_cache(
  text, text, integer, jsonb, integer
) from public, anon, authenticated;
revoke execute on function public.hybrid_search(
  uuid, uuid, uuid, text, text, text, jsonb, boolean, text, integer, integer,
  integer, numeric, numeric, numeric, uuid[], timestamptz, timestamptz,
  text[], text[], integer, jsonb
) from public, anon, authenticated;
revoke execute on function public.update_retrieval_trace_timings(
  uuid, uuid, uuid, numeric, numeric, numeric
) from public, anon, authenticated;
revoke execute on function app_private.invalidate_workspace_retrieval_cache()
  from public, anon, authenticated, service_role;

grant execute on function public.get_query_embedding_cache(text, text, integer)
  to service_role;
grant execute on function public.put_query_embedding_cache(
  text, text, integer, jsonb, integer
) to service_role;
grant execute on function public.hybrid_search(
  uuid, uuid, uuid, text, text, text, jsonb, boolean, text, integer, integer,
  integer, numeric, numeric, numeric, uuid[], timestamptz, timestamptz,
  text[], text[], integer, jsonb
) to service_role;
grant execute on function public.update_retrieval_trace_timings(
  uuid, uuid, uuid, numeric, numeric, numeric
) to service_role;
