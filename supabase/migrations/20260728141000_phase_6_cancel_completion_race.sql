create or replace function public.complete_rag_run(
  p_run_id uuid,
  p_workspace_id uuid,
  p_content text,
  p_answer_status text,
  p_confidence numeric,
  p_citations jsonb,
  p_model text,
  p_prompt_version text,
  p_timings jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  run_row public.rag_runs;
  output_id uuid;
begin
  select * into strict run_row
  from public.rag_runs
  where id = p_run_id and workspace_id = p_workspace_id
  for update;
  if run_row.status = 'cancelling' then
    update public.rag_runs set status = 'cancelled', completed_at = now()
    where id = p_run_id and workspace_id = p_workspace_id
    returning * into run_row;
    return jsonb_build_object('run', to_jsonb(run_row), 'cancelled', true);
  end if;
  if run_row.status in ('cancelled', 'failed', 'timed_out') then
    return jsonb_build_object('run', to_jsonb(run_row), 'cancelled', true);
  end if;
  insert into public.messages (
    workspace_id, conversation_id, role, content, answer_status,
    confidence, citations, model, prompt_version
  ) values (
    p_workspace_id, run_row.conversation_id, 'assistant', p_content,
    p_answer_status, p_confidence, p_citations, p_model, p_prompt_version
  ) returning id into output_id;
  update public.rag_runs set
    status = 'completed',
    current_node = 'complete',
    step_count = least(step_count + 1, 8),
    output_message_id = output_id,
    accumulated_text = p_content,
    answer_status = p_answer_status,
    confidence = p_confidence,
    timings = p_timings,
    completed_at = now()
  where id = p_run_id and workspace_id = p_workspace_id
  returning * into run_row;
  update public.conversations set updated_at = now()
  where id = run_row.conversation_id and workspace_id = p_workspace_id;
  return jsonb_build_object('run', to_jsonb(run_row), 'message_id', output_id);
end;
$$;

revoke execute on function public.complete_rag_run(
  uuid, uuid, text, text, numeric, jsonb, text, text, jsonb
) from public, anon, authenticated;
grant execute on function public.complete_rag_run(
  uuid, uuid, text, text, numeric, jsonb, text, text, jsonb
) to service_role;
