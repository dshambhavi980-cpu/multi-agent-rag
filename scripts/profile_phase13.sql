-- Replace both UUIDs with a workspace and one of its members before running.
explain (analyze, buffers, format text)
select public.hybrid_search(
  p_workspace_id => '00000000-0000-0000-0000-000000000000'::uuid,
  p_actor_id => '00000000-0000-0000-0000-000000000000'::uuid,
  p_request_id => gen_random_uuid(),
  p_query_text => 'capacity planning',
  p_query_hash => repeat('a', 64),
  p_request_hash => repeat('b', 64),
  p_query_embedding => to_jsonb(array_fill(0.001::numeric, array[768])),
  p_embedding_cache_hit => false,
  p_match_count => 6,
  p_candidate_count => 30,
  p_cache_ttl_seconds => 0
);

select public.phase_13_capacity_snapshot(
  '00000000-0000-0000-0000-000000000000'::uuid
);
