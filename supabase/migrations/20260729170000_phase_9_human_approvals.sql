alter table public.rag_runs drop constraint rag_runs_status;
alter table public.rag_runs
  add constraint rag_runs_status check (
    status in (
      'accepted', 'running', 'awaiting_approval', 'cancelling', 'cancelled',
      'completed', 'failed', 'timed_out'
    )
  );

create table public.approval_requests (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null,
  workspace_id uuid not null,
  requested_by uuid not null references auth.users (id) on delete cascade,
  assigned_to uuid references auth.users (id) on delete set null,
  status text not null default 'pending',
  risk_level text not null,
  reasons jsonb not null,
  creation_key text not null,
  proposed_output text,
  answer_status text,
  confidence numeric(5, 4),
  citations jsonb not null default '[]'::jsonb,
  model text,
  prompt_version text,
  reviewer_id uuid references auth.users (id) on delete set null,
  reviewer_comment text,
  edited_output text,
  escalation_level integer not null default 0,
  expires_at timestamptz not null,
  decided_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, run_id, creation_key),
  foreign key (run_id, workspace_id)
    references public.rag_runs (id, workspace_id) on delete cascade,
  constraint approval_requests_status check (
    status in ('pending', 'approved', 'rejected', 'revision_requested', 'expired')
  ),
  constraint approval_requests_risk check (
    risk_level in ('low', 'medium', 'high', 'critical')
  ),
  constraint approval_requests_reasons check (
    jsonb_typeof(reasons) = 'array' and jsonb_array_length(reasons) > 0
  ),
  constraint approval_requests_citations check (jsonb_typeof(citations) = 'array'),
  constraint approval_requests_confidence check (
    confidence is null or confidence between 0 and 1
  ),
  constraint approval_requests_creation_key check (
    char_length(creation_key) between 16 and 200
  ),
  constraint approval_requests_output check (
    proposed_output is null or char_length(proposed_output) <= 30000
  ),
  constraint approval_requests_comment check (
    reviewer_comment is null or char_length(reviewer_comment) between 1 and 2000
  ),
  constraint approval_requests_escalation check (escalation_level between 0 and 5)
);

create unique index approval_requests_one_pending_run_idx
  on public.approval_requests (run_id)
  where status = 'pending';
create index approval_requests_queue_idx
  on public.approval_requests (workspace_id, status, risk_level, created_at desc);
create index approval_requests_assignee_idx
  on public.approval_requests (assigned_to, status, created_at desc)
  where assigned_to is not null;

alter table public.rag_runs
  add column approval_id uuid references public.approval_requests (id) on delete set null;

create table public.approval_decisions (
  id uuid primary key default gen_random_uuid(),
  approval_id uuid not null references public.approval_requests (id) on delete cascade,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  reviewer_id uuid not null references auth.users (id) on delete cascade,
  decision_key text not null,
  action text not null,
  comment text not null,
  previous_state jsonb not null,
  final_state jsonb not null,
  created_at timestamptz not null default now(),
  unique (workspace_id, reviewer_id, decision_key),
  constraint approval_decisions_action check (action in ('approve', 'reject', 'revise')),
  constraint approval_decisions_key check (char_length(decision_key) between 16 and 128),
  constraint approval_decisions_comment check (char_length(comment) between 1 and 2000),
  constraint approval_decisions_previous check (jsonb_typeof(previous_state) = 'object'),
  constraint approval_decisions_final check (jsonb_typeof(final_state) = 'object')
);

create index approval_decisions_approval_created_idx
  on public.approval_decisions (approval_id, created_at);

alter table public.approval_requests enable row level security;
alter table public.approval_decisions enable row level security;

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
);

create policy approval_decisions_select_reviewer
on public.approval_decisions for select to authenticated
using (
  (select auth.uid()) is not null
  and exists (
    select 1
    from public.workspace_members member
    where member.workspace_id = approval_decisions.workspace_id
      and member.user_id = (select auth.uid())
      and member.role in ('owner', 'member')
  )
);

revoke all on public.approval_requests from public, anon, authenticated;
revoke all on public.approval_decisions from public, anon, authenticated;
grant select on public.approval_requests, public.approval_decisions to authenticated;
grant all on public.approval_requests, public.approval_decisions to service_role;

create trigger approval_requests_set_updated_at
before update on public.approval_requests
for each row execute function app_private.set_updated_at();

create or replace function app_private.assert_approval_reviewer(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_approval_id uuid default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not exists (
    select 1 from public.workspace_members member
    where member.workspace_id = p_workspace_id
      and member.user_id = p_actor_id
      and member.role in ('owner', 'member')
  ) then
    raise exception 'Reviewer access denied.' using errcode = '42501';
  end if;
  if p_approval_id is not null and not exists (
    select 1 from public.approval_requests approval
    where approval.id = p_approval_id
      and approval.workspace_id = p_workspace_id
      and (
        approval.assigned_to is null
        or approval.assigned_to = p_actor_id
        or exists (
          select 1 from public.workspace_members owner_member
          where owner_member.workspace_id = p_workspace_id
            and owner_member.user_id = p_actor_id
            and owner_member.role = 'owner'
        )
      )
  ) then
    raise exception 'Approval request not found.' using errcode = 'P0002';
  end if;
end;
$$;

create or replace function app_private.expire_approval_requests(p_workspace_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
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

create or replace function public.create_approval_request(
  p_run_id uuid,
  p_workspace_id uuid,
  p_actor_id uuid,
  p_creation_key text,
  p_risk_level text,
  p_reasons jsonb,
  p_proposed_output text,
  p_answer_status text,
  p_confidence numeric,
  p_citations jsonb,
  p_model text,
  p_prompt_version text,
  p_expires_hours integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  run_row public.rag_runs;
  approval_row public.approval_requests;
  reviewer uuid;
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id, null, p_run_id);
  if p_risk_level not in ('low', 'medium', 'high', 'critical')
    or jsonb_typeof(p_reasons) <> 'array'
    or jsonb_array_length(p_reasons) = 0
    or jsonb_typeof(p_citations) <> 'array'
    or p_expires_hours not between 1 and 168
  then
    raise exception 'Invalid approval request.' using errcode = '22023';
  end if;

  select * into run_row from public.rag_runs
  where id = p_run_id and workspace_id = p_workspace_id
  for update;
  select * into approval_row from public.approval_requests
  where workspace_id = p_workspace_id and run_id = p_run_id
    and creation_key = p_creation_key;
  if found then
    return to_jsonb(approval_row);
  end if;
  if run_row.status in ('completed', 'cancelled', 'failed', 'timed_out') then
    raise exception 'Terminal runs cannot request approval.' using errcode = '55000';
  end if;

  select member.user_id into reviewer
  from public.workspace_members member
  where member.workspace_id = p_workspace_id and member.role = 'owner'
  order by member.joined_at, member.user_id
  limit 1;

  insert into public.approval_requests (
    run_id, workspace_id, requested_by, assigned_to, risk_level, reasons,
    creation_key, proposed_output, answer_status, confidence, citations,
    model, prompt_version, expires_at
  ) values (
    p_run_id, p_workspace_id, p_actor_id, reviewer, p_risk_level, p_reasons,
    p_creation_key, p_proposed_output, p_answer_status, p_confidence, p_citations,
    p_model, p_prompt_version, now() + make_interval(hours => p_expires_hours)
  ) returning * into approval_row;

  update public.rag_runs
  set status = 'awaiting_approval', current_node = 'approval',
      approval_id = approval_row.id, accumulated_text = p_proposed_output,
      answer_status = p_answer_status, confidence = p_confidence
  where id = p_run_id and workspace_id = p_workspace_id;

  return to_jsonb(approval_row);
end;
$$;

create or replace function public.list_approval_requests(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_status text default null,
  p_limit integer default 50
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform app_private.assert_approval_reviewer(p_workspace_id, p_actor_id);
  if p_status is not null
    and p_status not in ('pending', 'approved', 'rejected', 'revision_requested', 'expired')
  then
    raise exception 'Invalid approval status.' using errcode = '22023';
  end if;
  perform app_private.expire_approval_requests(p_workspace_id);
  return jsonb_build_object(
    'items',
    coalesce((
      select jsonb_agg(to_jsonb(item) order by item.created_at desc, item.id desc)
      from (
        select * from public.approval_requests approval
        where approval.workspace_id = p_workspace_id
          and (p_status is null or approval.status = p_status)
          and (
            approval.assigned_to is null
            or approval.assigned_to = p_actor_id
            or exists (
              select 1 from public.workspace_members owner_member
              where owner_member.workspace_id = p_workspace_id
                and owner_member.user_id = p_actor_id
                and owner_member.role = 'owner'
            )
          )
        order by approval.created_at desc, approval.id desc
        limit least(greatest(p_limit, 1), 100)
      ) item
    ), '[]'::jsonb),
    'next_cursor', null
  );
end;
$$;

create or replace function public.get_approval_request(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_approval_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  result public.approval_requests;
begin
  perform app_private.assert_approval_reviewer(
    p_workspace_id, p_actor_id, p_approval_id
  );
  perform app_private.expire_approval_requests(p_workspace_id);
  select * into strict result from public.approval_requests
  where id = p_approval_id and workspace_id = p_workspace_id;
  return to_jsonb(result);
end;
$$;

create or replace function public.decide_approval_request(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_approval_id uuid,
  p_decision_key text,
  p_action text,
  p_comment text,
  p_edited_output text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  approval_row public.approval_requests;
  run_row public.rag_runs;
  existing_decision public.approval_decisions;
  output_id uuid;
  final_output text;
  resume_required boolean := false;
  previous_state jsonb;
begin
  perform app_private.assert_approval_reviewer(
    p_workspace_id, p_actor_id, p_approval_id
  );
  if p_action not in ('approve', 'reject', 'revise')
    or char_length(trim(p_comment)) not between 1 and 2000
    or char_length(p_decision_key) not between 16 and 128
  then
    raise exception 'Invalid approval decision.' using errcode = '22023';
  end if;

  select * into existing_decision from public.approval_decisions
  where workspace_id = p_workspace_id
    and reviewer_id = p_actor_id
    and decision_key = p_decision_key;
  if found then
    select * into strict approval_row from public.approval_requests
    where id = existing_decision.approval_id;
    return jsonb_build_object(
      'approval', to_jsonb(approval_row),
      'run_id', approval_row.run_id,
      'resume_required', false,
      'replayed', true
    );
  end if;

  select * into strict approval_row from public.approval_requests
  where id = p_approval_id and workspace_id = p_workspace_id
  for update;
  if approval_row.status <> 'pending' then
    raise exception 'Approval request was already decided.' using errcode = '55000';
  end if;
  if approval_row.expires_at <= now() then
    perform app_private.expire_approval_requests(p_workspace_id);
    raise exception 'Approval request expired.' using errcode = '55000';
  end if;

  select * into strict run_row from public.rag_runs
  where id = approval_row.run_id and workspace_id = p_workspace_id
  for update;
  if run_row.status <> 'awaiting_approval' or run_row.approval_id <> p_approval_id then
    raise exception 'Run is not waiting for this approval.' using errcode = '55000';
  end if;
  previous_state := jsonb_build_object(
    'approval_status', approval_row.status,
    'run_status', run_row.status,
    'current_node', run_row.current_node
  );

  if p_action = 'approve' then
    final_output := coalesce(nullif(trim(p_edited_output), ''), approval_row.proposed_output);
    if final_output is null or char_length(final_output) > 30000 then
      raise exception 'Approved output is invalid.' using errcode = '22023';
    end if;
    insert into public.messages (
      workspace_id, conversation_id, role, content, answer_status,
      confidence, citations, model, prompt_version
    ) values (
      p_workspace_id, run_row.conversation_id, 'assistant', final_output,
      approval_row.answer_status, approval_row.confidence, approval_row.citations,
      run_row.model, approval_row.prompt_version
    ) returning id into output_id;
    update public.rag_runs
    set status = 'completed', current_node = 'complete',
        output_message_id = output_id, accumulated_text = final_output,
        completed_at = now(), error = null
    where id = run_row.id and workspace_id = p_workspace_id;
    update public.conversations set updated_at = now()
    where id = run_row.conversation_id and workspace_id = p_workspace_id;
    update public.approval_requests
    set status = 'approved', reviewer_id = p_actor_id,
        reviewer_comment = trim(p_comment), edited_output = p_edited_output,
        decided_at = now()
    where id = p_approval_id returning * into approval_row;
  elsif p_action = 'reject' then
    update public.rag_runs
    set status = 'cancelled', current_node = 'approval',
        error = jsonb_build_object(
          'code', 'HUMAN_REJECTED',
          'detail', trim(p_comment),
          'retryable', false
        ),
        completed_at = now()
    where id = run_row.id and workspace_id = p_workspace_id;
    update public.approval_requests
    set status = 'rejected', reviewer_id = p_actor_id,
        reviewer_comment = trim(p_comment), decided_at = now()
    where id = p_approval_id returning * into approval_row;
  else
    update public.workflow_checkpoints
    set state = jsonb_set(
          jsonb_set(state, '{resume_node}', '"writer"'::jsonb, true),
          '{reviewer_feedback}', to_jsonb(trim(p_comment)), true
        ),
        next_node = 'writer',
        checkpoint_version = checkpoint_version + 1,
        updated_at = now()
    where run_id = run_row.id and workspace_id = p_workspace_id;
    if not found then
      raise exception 'Workflow checkpoint not found.' using errcode = 'P0002';
    end if;
    update public.rag_runs
    set status = 'accepted', current_node = 'writer', approval_id = null,
        completed_at = null, error = null
    where id = run_row.id and workspace_id = p_workspace_id;
    update public.approval_requests
    set status = 'revision_requested', reviewer_id = p_actor_id,
        reviewer_comment = trim(p_comment), decided_at = now()
    where id = p_approval_id returning * into approval_row;
    resume_required := true;
  end if;

  insert into public.approval_decisions (
    approval_id, workspace_id, reviewer_id, decision_key, action, comment,
    previous_state, final_state
  ) values (
    p_approval_id, p_workspace_id, p_actor_id, p_decision_key, p_action,
    trim(p_comment), previous_state,
    jsonb_build_object(
      'approval_status', approval_row.status,
      'run_status', case
        when p_action = 'approve' then 'completed'
        when p_action = 'reject' then 'cancelled'
        else 'accepted'
      end,
      'edited', p_edited_output is not null
    )
  );

  return jsonb_build_object(
    'approval', to_jsonb(approval_row),
    'run_id', approval_row.run_id,
    'resume_required', resume_required,
    'replayed', false
  );
end;
$$;

revoke execute on function app_private.assert_approval_reviewer(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function app_private.expire_approval_requests(uuid)
  from public, anon, authenticated;
revoke execute on function public.create_approval_request(
  uuid, uuid, uuid, text, text, jsonb, text, text, numeric, jsonb, text, text, integer
) from public, anon, authenticated;
revoke execute on function public.list_approval_requests(uuid, uuid, text, integer)
  from public, anon, authenticated;
revoke execute on function public.get_approval_request(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.decide_approval_request(
  uuid, uuid, uuid, text, text, text, text
) from public, anon, authenticated;

grant execute on function public.create_approval_request(
  uuid, uuid, uuid, text, text, jsonb, text, text, numeric, jsonb, text, text, integer
) to service_role;
grant execute on function public.list_approval_requests(uuid, uuid, text, integer)
  to service_role;
grant execute on function public.get_approval_request(uuid, uuid, uuid)
  to service_role;
grant execute on function public.decide_approval_request(
  uuid, uuid, uuid, text, text, text, text
) to service_role;
