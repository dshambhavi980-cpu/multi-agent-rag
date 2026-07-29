insert into auth.users (
  id, aud, role, email, raw_app_meta_data, raw_user_meta_data
) values (
  '14000000-0000-4000-8000-000000000001',
  'authenticated',
  'authenticated',
  'demo@docpilot.local',
  '{"provider":"email","providers":["email"]}'::jsonb,
  '{"full_name":"DocPilot Demo"}'::jsonb
) on conflict (id) do nothing;

insert into public.workspaces (id, name, created_by)
values (
  '14000000-0000-4000-8000-000000000014',
  'DocPilot Demo Workspace',
  '14000000-0000-4000-8000-000000000001'
) on conflict (id) do nothing;
