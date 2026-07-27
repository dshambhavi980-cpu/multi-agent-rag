begin;

insert into auth.users (id, aud, role, email, raw_app_meta_data, raw_user_meta_data)
values
  (
    '10000000-0000-4000-8000-000000000001',
    'authenticated',
    'authenticated',
    'owner-a@example.test',
    '{"provider":"email","providers":["email"]}'::jsonb,
    '{"full_name":"Owner A"}'::jsonb
  ),
  (
    '20000000-0000-4000-8000-000000000002',
    'authenticated',
    'authenticated',
    'owner-b@example.test',
    '{"provider":"email","providers":["email"]}'::jsonb,
    '{"full_name":"Owner B"}'::jsonb
  );

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-4000-8000-000000000001","role":"authenticated","aud":"authenticated"}',
  true
);

insert into public.workspaces (id, name, created_by)
values (
  'a0000000-0000-4000-8000-000000000001',
  'Workspace A',
  '10000000-0000-4000-8000-000000000001'
);

reset role;
set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"20000000-0000-4000-8000-000000000002","role":"authenticated","aud":"authenticated"}',
  true
);

insert into public.workspaces (id, name, created_by)
values (
  'b0000000-0000-4000-8000-000000000002',
  'Workspace B',
  '20000000-0000-4000-8000-000000000002'
);

reset role;
insert into storage.objects (bucket_id, name, owner_id)
values
  (
    'workspace-documents',
    'a0000000-0000-4000-8000-000000000001/10000000-0000-4000-8000-000000000001/a.txt',
    '10000000-0000-4000-8000-000000000001'
  ),
  (
    'workspace-documents',
    'b0000000-0000-4000-8000-000000000002/20000000-0000-4000-8000-000000000002/b.txt',
    '20000000-0000-4000-8000-000000000002'
  ),
  (
    'workspace-documents',
    'a0000000-0000-4000-8000-000000000001/20000000-0000-4000-8000-000000000002/owned-by-member.txt',
    '20000000-0000-4000-8000-000000000002'
  );

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-4000-8000-000000000001","role":"authenticated","aud":"authenticated"}',
  true
);

do $$
declare
  visible_workspaces integer;
  visible_objects integer;
  changed_rows integer;
  foreign_audit_events integer;
begin
  select count(*) into visible_workspaces from public.workspaces;
  if visible_workspaces <> 1 then
    raise exception 'Expected one visible workspace, got %', visible_workspaces;
  end if;

  select count(*) into visible_objects
  from storage.objects
  where bucket_id = 'workspace-documents';
  if visible_objects <> 2 then
    raise exception 'Expected two visible objects, got %', visible_objects;
  end if;

  update storage.objects
  set metadata = '{"reviewed":true}'::jsonb
  where name =
    'a0000000-0000-4000-8000-000000000001/20000000-0000-4000-8000-000000000002/owned-by-member.txt';
  get diagnostics changed_rows = row_count;
  if changed_rows <> 1 then
    raise exception 'Workspace owner could not update a member object';
  end if;

  update public.workspaces
  set name = 'Cross-tenant write'
  where id = 'b0000000-0000-4000-8000-000000000002';
  get diagnostics changed_rows = row_count;
  if changed_rows <> 0 then
    raise exception 'Cross-workspace update unexpectedly changed % row(s)', changed_rows;
  end if;

  select count(*) into foreign_audit_events
  from public.application_events
  where target_id = 'b0000000-0000-4000-8000-000000000002';
  if foreign_audit_events <> 0 then
    raise exception 'Cross-workspace audit metadata was visible';
  end if;

  begin
    delete from public.workspace_members
    where workspace_id = 'a0000000-0000-4000-8000-000000000001'
      and user_id = '10000000-0000-4000-8000-000000000001';
    raise exception 'Deleting the final owner unexpectedly succeeded';
  exception
    when check_violation then
      null;
  end;

  delete from public.workspaces
  where id = 'a0000000-0000-4000-8000-000000000001';
  get diagnostics changed_rows = row_count;
  if changed_rows <> 1 then
    raise exception 'Workspace owner could not delete their workspace';
  end if;

  select count(*) into changed_rows
  from public.workspace_members
  where workspace_id = 'a0000000-0000-4000-8000-000000000001';
  if changed_rows <> 0 then
    raise exception 'Workspace deletion did not cascade memberships';
  end if;
end;
$$;

rollback;
