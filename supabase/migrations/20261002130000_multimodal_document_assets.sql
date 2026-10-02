-- Phase: Multimodal Document Assets Storage Bucket
-- Description: Creates a public bucket for extracted document diagrams and charts

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'document-assets',
  'document-assets',
  true,
  10485760,
  array[
    'image/png',
    'image/jpeg',
    'image/webp'
  ]
)
on conflict (id) do update
set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- Allow public read access to document assets
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname = 'document_assets_public_read'
  ) then
    create policy document_assets_public_read
      on storage.objects
      for select
      using (bucket_id = 'document-assets');
  end if;
end $$;
