alter table public.document_chunks
  add constraint document_chunks_id_workspace_unique unique (id, workspace_id);

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  title text,
  summary text,
  create_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, workspace_id),
  unique nulls not distinct (workspace_id, owner_id, create_key),
  constraint conversations_title_length
    check (title is null or char_length(title) between 1 and 200),
  constraint conversations_summary_length
    check (summary is null or char_length(summary) <= 4000),
  constraint conversations_create_key_length
    check (create_key is null or char_length(create_key) between 8 and 200)
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  conversation_id uuid not null,
  role text not null,
  content text not null,
  answer_status text,
  confidence numeric(5, 4),
  citations jsonb not null default '[]'::jsonb,
  model text,
  prompt_version text,
  input_tokens integer,
  output_tokens integer,
  created_at timestamptz not null default now(),
  unique (id, workspace_id),
  foreign key (conversation_id, workspace_id)
    references public.conversations (id, workspace_id) on delete cascade,
  constraint messages_role check (role in ('user', 'assistant', 'system')),
  constraint messages_content_length check (char_length(content) between 1 and 50000),
  constraint messages_answer_status
    check (
      answer_status is null
      or answer_status in ('grounded', 'insufficient_evidence', 'failed')
    ),
  constraint messages_confidence
    check (confidence is null or confidence between 0 and 1),
  constraint messages_citations_array check (jsonb_typeof(citations) = 'array'),
  constraint messages_token_counts
    check (
      (input_tokens is null or input_tokens >= 0)
      and (output_tokens is null or output_tokens >= 0)
    )
);

create table public.rag_runs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  conversation_id uuid not null,
  owner_id uuid not null references auth.users (id) on delete cascade,
  input_message_id uuid not null,
  output_message_id uuid,
  retrieval_trace_id uuid references public.retrieval_traces (id) on delete set null,
  request_key text not null,
  mode text not null default 'simple',
  status text not null default 'accepted',
  current_node text,
  step_count integer not null default 0,
  question text not null,
  document_ids uuid[],
  prompt_version text not null,
  model text not null,
  answer_status text,
  confidence numeric(5, 4),
  evidence_count integer not null default 0,
  accumulated_text text not null default '',
  timings jsonb not null default '{}'::jsonb,
  error jsonb,
  cancel_requested_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, workspace_id),
  unique (workspace_id, owner_id, request_key),
  foreign key (conversation_id, workspace_id)
    references public.conversations (id, workspace_id) on delete cascade,
  foreign key (input_message_id, workspace_id)
    references public.messages (id, workspace_id) on delete restrict,
  foreign key (output_message_id, workspace_id)
    references public.messages (id, workspace_id)
    on delete set null (output_message_id),
  constraint rag_runs_mode check (mode = 'simple'),
  constraint rag_runs_status
    check (
      status in (
        'accepted', 'running', 'cancelling', 'cancelled',
        'completed', 'failed', 'timed_out'
      )
    ),
  constraint rag_runs_steps check (step_count between 0 and 8),
  constraint rag_runs_question_length check (char_length(question) between 1 and 12000),
  constraint rag_runs_request_key_length check (char_length(request_key) between 8 and 200),
  constraint rag_runs_document_count
    check (document_ids is null or cardinality(document_ids) <= 100),
  constraint rag_runs_answer_status
    check (
      answer_status is null
      or answer_status in ('grounded', 'insufficient_evidence', 'failed')
    ),
  constraint rag_runs_confidence
    check (confidence is null or confidence between 0 and 1),
  constraint rag_runs_evidence_count check (evidence_count between 0 and 10),
  constraint rag_runs_timings_object check (jsonb_typeof(timings) = 'object'),
  constraint rag_runs_error_object
    check (error is null or jsonb_typeof(error) = 'object')
);

create table public.rag_evidence (
  run_id uuid not null,
  workspace_id uuid not null,
  citation_id text not null,
  ordinal integer not null,
  document_id uuid not null,
  chunk_id uuid not null,
  label text not null,
  page integer,
  section text,
  quote text not null,
  source_url text not null,
  semantic_rank integer,
  sparse_rank integer,
  semantic_score numeric,
  sparse_score numeric,
  rrf_score numeric not null,
  created_at timestamptz not null default now(),
  primary key (run_id, citation_id),
  unique (run_id, chunk_id),
  foreign key (run_id, workspace_id)
    references public.rag_runs (id, workspace_id) on delete cascade,
  foreign key (document_id, workspace_id)
    references public.documents (id, workspace_id) on delete cascade,
  foreign key (chunk_id, workspace_id)
    references public.document_chunks (id, workspace_id) on delete cascade,
  constraint rag_evidence_citation_id check (citation_id ~ '^C[1-9][0-9]*$'),
  constraint rag_evidence_ordinal check (ordinal between 1 and 10),
  constraint rag_evidence_page check (page is null or page > 0),
  constraint rag_evidence_quote_length check (char_length(quote) between 1 and 1000)
);

create table public.rag_run_events (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null,
  workspace_id uuid not null,
  sequence integer not null,
  event_type text not null,
  payload jsonb not null,
  occurred_at timestamptz not null default now(),
  unique (run_id, sequence),
  foreign key (run_id, workspace_id)
    references public.rag_runs (id, workspace_id) on delete cascade,
  constraint rag_run_events_sequence check (sequence > 0),
  constraint rag_run_events_type_length check (char_length(event_type) between 3 and 80),
  constraint rag_run_events_payload_object check (jsonb_typeof(payload) = 'object')
);

create index conversations_owner_updated_idx
  on public.conversations (workspace_id, owner_id, updated_at desc, id desc);
create index messages_conversation_created_idx
  on public.messages (workspace_id, conversation_id, created_at, id);
create index rag_runs_owner_created_idx
  on public.rag_runs (workspace_id, owner_id, created_at desc);
create index rag_runs_active_idx
  on public.rag_runs (updated_at)
  where status in ('accepted', 'running', 'cancelling');
create index rag_evidence_document_idx
  on public.rag_evidence (workspace_id, document_id, run_id);
create index rag_evidence_chunk_idx
  on public.rag_evidence (chunk_id, workspace_id);
create index rag_run_events_stream_idx
  on public.rag_run_events (workspace_id, run_id, sequence);

create trigger conversations_set_updated_at
before update on public.conversations
for each row execute function app_private.set_updated_at();

create trigger rag_runs_set_updated_at
before update on public.rag_runs
for each row execute function app_private.set_updated_at();

alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.rag_runs enable row level security;
alter table public.rag_evidence enable row level security;
alter table public.rag_run_events enable row level security;

create policy conversations_select_owner
on public.conversations for select to authenticated
using (
  owner_id = (select auth.uid())
  and (select app_private.is_workspace_member(workspace_id))
);

create policy messages_select_conversation_owner
on public.messages for select to authenticated
using (
  exists (
    select 1
    from public.conversations conversation
    where conversation.id = messages.conversation_id
      and conversation.workspace_id = messages.workspace_id
      and conversation.owner_id = (select auth.uid())
  )
);

create policy rag_runs_select_owner
on public.rag_runs for select to authenticated
using (
  owner_id = (select auth.uid())
  and (select app_private.is_workspace_member(workspace_id))
);

create policy rag_evidence_select_run_owner
on public.rag_evidence for select to authenticated
using (
  exists (
    select 1
    from public.rag_runs run
    where run.id = rag_evidence.run_id
      and run.workspace_id = rag_evidence.workspace_id
      and run.owner_id = (select auth.uid())
  )
);

create policy rag_run_events_select_run_owner
on public.rag_run_events for select to authenticated
using (
  exists (
    select 1
    from public.rag_runs run
    where run.id = rag_run_events.run_id
      and run.workspace_id = rag_run_events.workspace_id
      and run.owner_id = (select auth.uid())
  )
);

revoke all on public.conversations from public, anon, authenticated;
revoke all on public.messages from public, anon, authenticated;
revoke all on public.rag_runs from public, anon, authenticated;
revoke all on public.rag_evidence from public, anon, authenticated;
revoke all on public.rag_run_events from public, anon, authenticated;
grant select on public.conversations, public.messages, public.rag_runs,
  public.rag_evidence, public.rag_run_events to authenticated;
grant all on public.conversations, public.messages, public.rag_runs,
  public.rag_evidence, public.rag_run_events to service_role;

create or replace function app_private.assert_rag_actor(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_conversation_id uuid default null,
  p_run_id uuid default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not exists (
    select 1
    from public.workspace_members member
    where member.workspace_id = p_workspace_id
      and member.user_id = p_actor_id
  ) then
    raise exception 'Workspace access denied.' using errcode = '42501';
  end if;
  if p_conversation_id is not null and not exists (
    select 1
    from public.conversations conversation
    where conversation.id = p_conversation_id
      and conversation.workspace_id = p_workspace_id
      and conversation.owner_id = p_actor_id
  ) then
    raise exception 'Conversation not found.' using errcode = 'P0002';
  end if;
  if p_run_id is not null and not exists (
    select 1
    from public.rag_runs run
    where run.id = p_run_id
      and run.workspace_id = p_workspace_id
      and run.owner_id = p_actor_id
  ) then
    raise exception 'Run not found.' using errcode = 'P0002';
  end if;
end;
$$;

create or replace function public.create_conversation(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_title text,
  p_create_key text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  result public.conversations;
begin
  perform app_private.assert_rag_actor(p_workspace_id, p_actor_id);
  insert into public.conversations (workspace_id, owner_id, title, create_key)
  values (p_workspace_id, p_actor_id, nullif(trim(p_title), ''), p_create_key)
  on conflict (workspace_id, owner_id, create_key) do update
  set create_key = excluded.create_key
  returning * into result;
  return to_jsonb(result) - 'create_key';
end;
$$;

create or replace function public.list_conversations(
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
      select jsonb_agg(to_jsonb(item) - 'create_key' order by item.updated_at desc, item.id desc)
      from (
        select *
        from public.conversations conversation
        where conversation.workspace_id = p_workspace_id
          and conversation.owner_id = p_actor_id
        order by conversation.updated_at desc, conversation.id desc
        limit least(greatest(p_limit, 1), 100)
      ) item
    ), '[]'::jsonb),
    'next_cursor', null
  );
end;
$$;

create or replace function public.get_conversation(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_conversation_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  conversation_row public.conversations;
begin
  perform app_private.assert_rag_actor(
    p_workspace_id, p_actor_id, p_conversation_id
  );
  select * into strict conversation_row
  from public.conversations
  where id = p_conversation_id and workspace_id = p_workspace_id;
  return (to_jsonb(conversation_row) - 'create_key') || jsonb_build_object(
    'messages',
    coalesce((
      select jsonb_agg(to_jsonb(message) - 'workspace_id' order by created_at, id)
      from public.messages message
      where message.workspace_id = p_workspace_id
        and message.conversation_id = p_conversation_id
    ), '[]'::jsonb)
  );
end;
$$;

create or replace function public.start_simple_rag_run(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_conversation_id uuid,
  p_content text,
  p_document_ids uuid[],
  p_request_key text,
  p_prompt_version text,
  p_model text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  existing_run public.rag_runs;
  input_id uuid;
  run_row public.rag_runs;
begin
  perform app_private.assert_rag_actor(
    p_workspace_id, p_actor_id, p_conversation_id
  );
  select * into existing_run
  from public.rag_runs
  where workspace_id = p_workspace_id
    and owner_id = p_actor_id
    and request_key = p_request_key;
  if found then
    return jsonb_build_object(
      'run_id', existing_run.id,
      'message_id', existing_run.input_message_id,
      'status', existing_run.status,
      'events_url', '/v1/runs/' || existing_run.id || '/events'
    );
  end if;

  insert into public.messages (
    workspace_id, conversation_id, role, content
  ) values (
    p_workspace_id, p_conversation_id, 'user', trim(p_content)
  ) returning id into input_id;

  insert into public.rag_runs (
    workspace_id, conversation_id, owner_id, input_message_id,
    request_key, question, document_ids, prompt_version, model
  ) values (
    p_workspace_id, p_conversation_id, p_actor_id, input_id,
    p_request_key, trim(p_content), p_document_ids, p_prompt_version, p_model
  ) returning * into run_row;

  update public.conversations
  set updated_at = now(),
      title = coalesce(title, left(trim(p_content), 80))
  where id = p_conversation_id and workspace_id = p_workspace_id;

  return jsonb_build_object(
    'run_id', run_row.id,
    'message_id', input_id,
    'status', run_row.status,
    'events_url', '/v1/runs/' || run_row.id || '/events'
  );
end;
$$;

create or replace function public.get_rag_run(
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
  result public.rag_runs;
begin
  perform app_private.assert_rag_actor(
    p_workspace_id, p_actor_id, null, p_run_id
  );
  select * into strict result
  from public.rag_runs where id = p_run_id and workspace_id = p_workspace_id;
  return to_jsonb(result) - array[
    'workspace_id', 'owner_id', 'input_message_id', 'request_key',
    'question', 'document_ids', 'prompt_version', 'model',
    'evidence_count', 'accumulated_text', 'timings',
    'cancel_requested_at', 'started_at'
  ];
end;
$$;

create or replace function public.append_rag_run_event(
  p_run_id uuid,
  p_workspace_id uuid,
  p_event_type text,
  p_payload jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  next_sequence integer;
  event_row public.rag_run_events;
begin
  perform 1 from public.rag_runs
  where id = p_run_id and workspace_id = p_workspace_id
  for update;
  if not found then
    raise exception 'Run not found.' using errcode = 'P0002';
  end if;
  select coalesce(max(sequence), 0) + 1 into next_sequence
  from public.rag_run_events where run_id = p_run_id;
  insert into public.rag_run_events (
    run_id, workspace_id, sequence, event_type, payload
  ) values (
    p_run_id, p_workspace_id, next_sequence, p_event_type, p_payload
  ) returning * into event_row;
  return to_jsonb(event_row);
end;
$$;

create or replace function public.store_rag_evidence(
  p_run_id uuid,
  p_workspace_id uuid,
  p_retrieval_trace_id uuid,
  p_evidence jsonb
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  item jsonb;
begin
  if jsonb_typeof(p_evidence) <> 'array' or jsonb_array_length(p_evidence) > 10 then
    raise exception 'Invalid evidence payload.' using errcode = '22023';
  end if;
  delete from public.rag_evidence
  where run_id = p_run_id and workspace_id = p_workspace_id;
  for item in select value from jsonb_array_elements(p_evidence)
  loop
    insert into public.rag_evidence (
      run_id, workspace_id, citation_id, ordinal, document_id, chunk_id,
      label, page, section, quote, source_url, semantic_rank, sparse_rank,
      semantic_score, sparse_score, rrf_score
    ) values (
      p_run_id, p_workspace_id, item ->> 'citation_id',
      (item ->> 'ordinal')::integer, (item ->> 'document_id')::uuid,
      (item ->> 'chunk_id')::uuid, item ->> 'label',
      nullif(item ->> 'page', '')::integer, nullif(item ->> 'section', ''),
      item ->> 'quote', item ->> 'source_url',
      nullif(item ->> 'semantic_rank', '')::integer,
      nullif(item ->> 'sparse_rank', '')::integer,
      nullif(item ->> 'semantic_score', '')::numeric,
      nullif(item ->> 'sparse_score', '')::numeric,
      (item ->> 'rrf_score')::numeric
    );
  end loop;
  update public.rag_runs set
    retrieval_trace_id = p_retrieval_trace_id,
    evidence_count = jsonb_array_length(p_evidence)
  where id = p_run_id and workspace_id = p_workspace_id;
  return found;
end;
$$;

create or replace function public.transition_rag_run(
  p_run_id uuid,
  p_workspace_id uuid,
  p_status text,
  p_current_node text default null,
  p_accumulated_text text default null,
  p_answer_status text default null,
  p_confidence numeric default null,
  p_output_message_id uuid default null,
  p_timings jsonb default null,
  p_error jsonb default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  result public.rag_runs;
begin
  update public.rag_runs set
    status = p_status,
    current_node = p_current_node,
    step_count = case
      when p_current_node is distinct from current_node then least(step_count + 1, 8)
      else step_count
    end,
    accumulated_text = coalesce(p_accumulated_text, accumulated_text),
    answer_status = coalesce(p_answer_status, answer_status),
    confidence = coalesce(p_confidence, confidence),
    output_message_id = coalesce(p_output_message_id, output_message_id),
    timings = coalesce(p_timings, timings),
    error = p_error,
    started_at = case when p_status = 'running' then coalesce(started_at, now()) else started_at end,
    completed_at = case
      when p_status in ('completed', 'failed', 'cancelled', 'timed_out') then now()
      else completed_at
    end
  where id = p_run_id
    and workspace_id = p_workspace_id
    and status not in ('completed', 'failed', 'cancelled', 'timed_out')
  returning * into result;
  if not found then
    select * into result from public.rag_runs
    where id = p_run_id and workspace_id = p_workspace_id;
  end if;
  if result.id is null then
    raise exception 'Run not found.' using errcode = 'P0002';
  end if;
  return to_jsonb(result);
end;
$$;

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

create or replace function public.get_rag_run_events(
  p_workspace_id uuid,
  p_actor_id uuid,
  p_run_id uuid,
  p_after_sequence integer default 0
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform app_private.assert_rag_actor(
    p_workspace_id, p_actor_id, null, p_run_id
  );
  return coalesce((
    select jsonb_agg(to_jsonb(event) order by sequence)
    from (
      select id, sequence, event_type, payload, occurred_at
      from public.rag_run_events
      where run_id = p_run_id
        and workspace_id = p_workspace_id
        and sequence > greatest(p_after_sequence, 0)
      order by sequence
      limit 100
    ) event
  ), '[]'::jsonb);
end;
$$;

create or replace function public.request_rag_run_cancel(
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
  result public.rag_runs;
begin
  perform app_private.assert_rag_actor(
    p_workspace_id, p_actor_id, null, p_run_id
  );
  update public.rag_runs set
    status = case when status in ('accepted', 'running') then 'cancelling' else status end,
    cancel_requested_at = case
      when status in ('accepted', 'running') then now()
      else cancel_requested_at
    end
  where id = p_run_id and workspace_id = p_workspace_id
  returning * into result;
  if result.status not in ('cancelling', 'cancelled') then
    raise exception 'Run is already terminal.' using errcode = '55000';
  end if;
  return to_jsonb(result);
end;
$$;

revoke execute on function app_private.assert_rag_actor(uuid, uuid, uuid, uuid)
  from public, anon, authenticated, service_role;
revoke execute on function public.create_conversation(uuid, uuid, text, text)
  from public, anon, authenticated;
revoke execute on function public.list_conversations(uuid, uuid, integer)
  from public, anon, authenticated;
revoke execute on function public.get_conversation(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.start_simple_rag_run(
  uuid, uuid, uuid, text, uuid[], text, text, text
) from public, anon, authenticated;
revoke execute on function public.get_rag_run(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke execute on function public.append_rag_run_event(uuid, uuid, text, jsonb)
  from public, anon, authenticated;
revoke execute on function public.store_rag_evidence(uuid, uuid, uuid, jsonb)
  from public, anon, authenticated;
revoke execute on function public.transition_rag_run(
  uuid, uuid, text, text, text, text, numeric, uuid, jsonb, jsonb
) from public, anon, authenticated;
revoke execute on function public.complete_rag_run(
  uuid, uuid, text, text, numeric, jsonb, text, text, jsonb
) from public, anon, authenticated;
revoke execute on function public.get_rag_run_events(uuid, uuid, uuid, integer)
  from public, anon, authenticated;
revoke execute on function public.request_rag_run_cancel(uuid, uuid, uuid)
  from public, anon, authenticated;

grant execute on function public.create_conversation(uuid, uuid, text, text)
  to service_role;
grant execute on function public.list_conversations(uuid, uuid, integer)
  to service_role;
grant execute on function public.get_conversation(uuid, uuid, uuid)
  to service_role;
grant execute on function public.start_simple_rag_run(
  uuid, uuid, uuid, text, uuid[], text, text, text
) to service_role;
grant execute on function public.get_rag_run(uuid, uuid, uuid)
  to service_role;
grant execute on function public.append_rag_run_event(uuid, uuid, text, jsonb)
  to service_role;
grant execute on function public.store_rag_evidence(uuid, uuid, uuid, jsonb)
  to service_role;
grant execute on function public.transition_rag_run(
  uuid, uuid, text, text, text, text, numeric, uuid, jsonb, jsonb
) to service_role;
grant execute on function public.complete_rag_run(
  uuid, uuid, text, text, numeric, jsonb, text, text, jsonb
) to service_role;
grant execute on function public.get_rag_run_events(uuid, uuid, uuid, integer)
  to service_role;
grant execute on function public.request_rag_run_cancel(uuid, uuid, uuid)
  to service_role;
