create index approval_requests_run_workspace_idx
  on public.approval_requests (run_id, workspace_id);
create index approval_requests_requested_by_idx
  on public.approval_requests (requested_by);
create index approval_requests_reviewer_idx
  on public.approval_requests (reviewer_id)
  where reviewer_id is not null;
create index approval_decisions_reviewer_idx
  on public.approval_decisions (reviewer_id);
create index rag_runs_approval_idx
  on public.rag_runs (approval_id)
  where approval_id is not null;

drop policy approval_requests_select_reviewer on public.approval_requests;
create policy approval_requests_select_reviewer
on public.approval_requests for select to authenticated
using (
  (select auth.uid()) is not null
  and exists (
    select 1
    from public.workspace_members member
    where member.workspace_id = approval_requests.workspace_id
      and member.user_id = (select auth.uid())
      and member.role in ('owner', 'member')
  )
  and (
    approval_requests.assigned_to is null
    or approval_requests.assigned_to = (select auth.uid())
    or app_private.has_workspace_role(
      approval_requests.workspace_id,
      array['owner'::public.workspace_role]
    )
  )
);

create or replace function app_private.expire_approval_requests(p_workspace_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.approval_requests
  set escalation_level = least(
        5,
        greatest(
          escalation_level,
          floor(extract(epoch from (now() - created_at)) / 3600)::integer
        )
      )
  where workspace_id = p_workspace_id
    and status = 'pending'
    and created_at < now() - interval '1 hour';

  with expired as (
    update public.approval_requests
    set status = 'expired', decided_at = now(),
        reviewer_comment = 'The approval window expired without a decision.'
    where workspace_id = p_workspace_id
      and status = 'pending'
      and expires_at <= now()
    returning run_id
  )
  update public.rag_runs run
  set status = 'failed',
      current_node = 'approval',
      error = jsonb_build_object(
        'code', 'APPROVAL_EXPIRED',
        'detail', 'The workflow stopped because its approval request expired.',
        'retryable', true
      ),
      completed_at = now()
  where run.workspace_id = p_workspace_id
    and run.id in (select expired.run_id);
end;
$$;
