create index if not exists conversations_owner_idx
  on public.conversations (owner_id);
create index if not exists messages_conversation_workspace_idx
  on public.messages (conversation_id, workspace_id);
create index if not exists rag_runs_conversation_workspace_idx
  on public.rag_runs (conversation_id, workspace_id);
create index if not exists rag_runs_input_message_workspace_idx
  on public.rag_runs (input_message_id, workspace_id);
create index if not exists rag_runs_output_message_workspace_idx
  on public.rag_runs (output_message_id, workspace_id)
  where output_message_id is not null;
create index if not exists rag_runs_owner_idx
  on public.rag_runs (owner_id);
create index if not exists rag_runs_retrieval_trace_idx
  on public.rag_runs (retrieval_trace_id)
  where retrieval_trace_id is not null;
create index if not exists rag_runs_replayed_from_idx
  on public.rag_runs (replayed_from_run_id)
  where replayed_from_run_id is not null;
create index if not exists rag_evidence_run_workspace_idx
  on public.rag_evidence (run_id, workspace_id);
create index if not exists rag_evidence_document_workspace_idx
  on public.rag_evidence (document_id, workspace_id);
create index if not exists rag_run_events_run_workspace_idx
  on public.rag_run_events (run_id, workspace_id);
create index if not exists operational_events_run_workspace_idx
  on public.operational_events (run_id, workspace_id)
  where run_id is not null;
create index if not exists evaluation_results_workspace_idx
  on public.evaluation_results (workspace_id);
