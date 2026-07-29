create or replace function public.list_rag_runs(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_limit integer default 50
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id);
  return jsonb_build_object(
    'items',
    coalesce((
      select jsonb_agg(
        to_jsonb(item) - array[
          'workspace_id', 'owner_id', 'input_message_id', 'request_key',
          'document_ids', 'prompt_version', 'model', 'evidence_count',
          'accumulated_text', 'timings', 'cancel_requested_at', 'started_at',
          'retrieval_trace_id'
        ]
        order by item.created_at desc, item.id desc
      )
      from (
        select run.*, message.content as question
        from public.rag_runs run
        join public.messages message
          on message.id = run.input_message_id
          and message.workspace_id = run.workspace_id
        where run.workspace_id = p_workspace_id and run.owner_id = p_actor_id
        order by run.created_at desc, run.id desc
        limit least(greatest(p_limit, 1), 100)
      ) item
    ), '[]'::jsonb),
    'next_cursor', null
  );
end;
$$;

create or replace function public.get_agent_run_trace(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_run_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  run_row public.rag_runs;
begin
  perform app_private.assert_rag_actor(
    p_workspace_id, p_actor_id, null, p_run_id
  );
  select * into strict run_row from public.rag_runs
  where id = p_run_id and workspace_id = p_workspace_id;
  return jsonb_build_object(
    'run',
    (
      to_jsonb(run_row) - array[
        'workspace_id', 'owner_id', 'input_message_id', 'request_key',
        'document_ids', 'prompt_version', 'model', 'evidence_count',
        'accumulated_text', 'timings', 'cancel_requested_at', 'started_at',
        'retrieval_trace_id'
      ]
    ) || jsonb_build_object(
      'question',
      (
        select message.content from public.messages message
        where message.id = run_row.input_message_id
          and message.workspace_id = p_workspace_id
      )
    ),
    'steps',
    coalesce((
      select jsonb_agg(
        to_jsonb(step) - array['run_id', 'workspace_id']
        order by step.step_number, step.created_at
      )
      from public.agent_steps step
      where step.run_id = p_run_id and step.workspace_id = p_workspace_id
    ), '[]'::jsonb),
    'tool_calls',
    coalesce((
      select jsonb_agg(
        to_jsonb(call) - array['run_id', 'workspace_id', 'sanitized_input']
        order by call.created_at
      )
      from public.tool_calls call
      where call.run_id = p_run_id and call.workspace_id = p_workspace_id
    ), '[]'::jsonb)
  );
end;
$$;

create or replace function public.get_workspace_usage(
  p_workspace_id uuid,
  p_actor_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id);
  return jsonb_build_object(
    'documents', (
      select count(*) from public.documents document
      where document.workspace_id = p_workspace_id
    ),
    'document_bytes', (
      select coalesce(sum(document.size_bytes), 0) from public.documents document
      where document.workspace_id = p_workspace_id
    ),
    'ready_documents', (
      select count(*) from public.documents document
      where document.workspace_id = p_workspace_id and document.status = 'ready'
    ),
    'conversations', (
      select count(*) from public.conversations conversation
      where conversation.workspace_id = p_workspace_id
        and conversation.owner_id = p_actor_id
    ),
    'runs', (
      select count(*) from public.rag_runs run
      where run.workspace_id = p_workspace_id and run.owner_id = p_actor_id
    ),
    'approvals', (
      select count(*) from public.approval_requests approval
      where approval.workspace_id = p_workspace_id
    ),
    'memories', (
      select count(*) from public.memory_items memory
      where memory.workspace_id = p_workspace_id
        and memory.deleted_at is null
        and (memory.expires_at is null or memory.expires_at > now())
    )
  );
end;
$$;

revoke execute on function public.list_rag_runs(uuid, uuid, integer)
  from public, anon, authenticated;
revoke execute on function public.get_agent_run_trace(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.get_workspace_usage(uuid, uuid)
  from public, anon, authenticated;

grant execute on function public.list_rag_runs(uuid, uuid, integer)
  to service_role;
grant execute on function public.get_agent_run_trace(uuid, uuid, uuid)
  to service_role;
grant execute on function public.get_workspace_usage(uuid, uuid)
  to service_role;
