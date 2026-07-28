create index agent_steps_run_workspace_idx
  on public.agent_steps (run_id, workspace_id);

create index tool_calls_run_workspace_idx
  on public.tool_calls (run_id, workspace_id);
