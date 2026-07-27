begin;

insert into auth.users (id, aud, role, email, raw_app_meta_data, raw_user_meta_data)
values
  (
    '10000000-0000-4000-8000-000000000061',
    'authenticated', 'authenticated', 'phase6-owner@example.test', '{}', '{}'
  ),
  (
    '10000000-0000-4000-8000-000000000062',
    'authenticated', 'authenticated', 'phase6-other@example.test', '{}', '{}'
  );

insert into public.workspaces (id, name, created_by)
values
  (
    'a0000000-0000-4000-8000-000000000061',
    'Phase 6 owner workspace',
    '10000000-0000-4000-8000-000000000061'
  ),
  (
    'a0000000-0000-4000-8000-000000000062',
    'Phase 6 other workspace',
    '10000000-0000-4000-8000-000000000062'
  );

insert into public.documents (
  id, workspace_id, uploaded_by, object_path, filename, content_type,
  size_bytes, sha256, status, processing_version, index_version,
  target_index_version, chunk_strategy, embedding_model,
  embedding_dimensions, indexed_at, page_count, chunk_count, tags
)
values (
  '40000000-0000-4000-8000-000000000061',
  'a0000000-0000-4000-8000-000000000061',
  '10000000-0000-4000-8000-000000000061',
  'phase6/operations.md', 'operations.md', 'text/markdown',
  1000, repeat('6', 64), 'ready', 1, 1, 1, 'heading_recursive',
  'gemini-embedding-001', 768, now(), 2, 1, array['operations']
);

insert into public.document_chunks (
  id, workspace_id, document_id, chunk_index, processing_version, strategy,
  content, page_start, page_end, section_heading, char_start, char_end, token_count
)
values (
  '50000000-0000-4000-8000-000000000061',
  'a0000000-0000-4000-8000-000000000061',
  '40000000-0000-4000-8000-000000000061',
  0, 1, 'heading_recursive',
  'Rotate the emergency token and record the audit event.',
  2, 2, 'Emergency reset', 0, 54, 9
);

do $$
declare
  conversation_one jsonb;
  conversation_retry jsonb;
  accepted jsonb;
  accepted_retry jsonb;
  run_id uuid;
  first_event jsonb;
  second_event jsonb;
  cancel_result jsonb;
  completion_result jsonb;
  message_count integer;
  evidence_count integer;
begin
  conversation_one := public.create_conversation(
    'a0000000-0000-4000-8000-000000000061',
    '10000000-0000-4000-8000-000000000061',
    'Emergency access',
    'phase6-conversation-key'
  );
  conversation_retry := public.create_conversation(
    'a0000000-0000-4000-8000-000000000061',
    '10000000-0000-4000-8000-000000000061',
    'Changed title',
    'phase6-conversation-key'
  );
  if conversation_one ->> 'id' <> conversation_retry ->> 'id' then
    raise exception 'Conversation idempotency failed';
  end if;

  begin
    perform public.create_conversation(
      'a0000000-0000-4000-8000-000000000061',
      '10000000-0000-4000-8000-000000000062',
      'Cross workspace',
      'phase6-cross-workspace'
    );
    raise exception 'Cross-workspace conversation creation unexpectedly succeeded';
  exception
    when insufficient_privilege then null;
  end;

  accepted := public.start_simple_rag_run(
    'a0000000-0000-4000-8000-000000000061',
    '10000000-0000-4000-8000-000000000061',
    (conversation_one ->> 'id')::uuid,
    'How is the emergency token rotated?',
    null,
    'phase6-message-request-key',
    'rag-system-v1+answer-v1',
    'gemini-3.1-flash-lite'
  );
  accepted_retry := public.start_simple_rag_run(
    'a0000000-0000-4000-8000-000000000061',
    '10000000-0000-4000-8000-000000000061',
    (conversation_one ->> 'id')::uuid,
    'A different duplicate body',
    null,
    'phase6-message-request-key',
    'rag-system-v1+answer-v1',
    'gemini-3.1-flash-lite'
  );
  if accepted ->> 'run_id' <> accepted_retry ->> 'run_id'
    or accepted ->> 'message_id' <> accepted_retry ->> 'message_id'
  then
    raise exception 'Run idempotency failed';
  end if;
  run_id := (accepted ->> 'run_id')::uuid;

  select count(*) into message_count
  from public.messages
  where conversation_id = (conversation_one ->> 'id')::uuid
    and role = 'user';
  if message_count <> 1 then
    raise exception 'Idempotent run created % user messages', message_count;
  end if;

  perform public.store_rag_evidence(
    run_id,
    'a0000000-0000-4000-8000-000000000061',
    null,
    jsonb_build_array(jsonb_build_object(
      'citation_id', 'C1',
      'ordinal', 1,
      'document_id', '40000000-0000-4000-8000-000000000061',
      'chunk_id', '50000000-0000-4000-8000-000000000061',
      'label', 'operations.md, page 2',
      'page', 2,
      'section', 'Emergency reset',
      'quote', 'Rotate the emergency token and record the audit event.',
      'source_url', '/v1/documents/40000000-0000-4000-8000-000000000061/source?page=2',
      'semantic_rank', 1,
      'sparse_rank', 1,
      'semantic_score', 0.8,
      'sparse_score', 0.7,
      'rrf_score', 0.0328
    ))
  );
  select count(*) into evidence_count
  from public.rag_evidence
  where rag_evidence.run_id = run_id and citation_id = 'C1';
  if evidence_count <> 1 then
    raise exception 'Stable evidence citation was not persisted';
  end if;

  begin
    perform public.store_rag_evidence(
      run_id,
      'a0000000-0000-4000-8000-000000000061',
      null,
      jsonb_build_array(jsonb_build_object(
        'citation_id', 'X1',
        'ordinal', 1,
        'document_id', '40000000-0000-4000-8000-000000000061',
        'chunk_id', '50000000-0000-4000-8000-000000000061',
        'label', 'invalid',
        'page', 2,
        'quote', 'invalid',
        'source_url', '/invalid',
        'rrf_score', 0.1
      ))
    );
    raise exception 'Invalid citation identifier unexpectedly persisted';
  exception
    when check_violation then null;
  end;

  first_event := public.append_rag_run_event(
    run_id, 'a0000000-0000-4000-8000-000000000061',
    'answer.delta', '{"delta":"Grounded [C1]."}'
  );
  second_event := public.append_rag_run_event(
    run_id, 'a0000000-0000-4000-8000-000000000061',
    'citations.available', '{"citations":[{"citation_id":"C1"}]}'
  );
  if (first_event ->> 'sequence')::integer <> 1
    or (second_event ->> 'sequence')::integer <> 2
  then
    raise exception 'Run event sequence is not deterministic';
  end if;

  cancel_result := public.request_rag_run_cancel(
    'a0000000-0000-4000-8000-000000000061',
    '10000000-0000-4000-8000-000000000061',
    run_id
  );
  if cancel_result ->> 'status' <> 'cancelling' then
    raise exception 'Run cancellation was not persisted';
  end if;

  completion_result := public.complete_rag_run(
    run_id,
    'a0000000-0000-4000-8000-000000000061',
    'This answer must not be published [C1].',
    'grounded',
    0.9,
    '[]',
    'gemini-3.1-flash-lite',
    'rag-system-v1+answer-v1',
    '{}'
  );
  if coalesce((completion_result ->> 'cancelled')::boolean, false) is not true
    or completion_result -> 'run' ->> 'status' <> 'cancelled'
  then
    raise exception 'Cancellation lost the atomic completion race';
  end if;

  select count(*) into message_count
  from public.messages
  where conversation_id = (conversation_one ->> 'id')::uuid
    and role = 'assistant';
  if message_count <> 0 then
    raise exception 'Cancelled run published an assistant message';
  end if;
end;
$$;

select true as phase6_grounded_rag_acceptance;

rollback;
