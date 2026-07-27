drop policy workspace_documents_update_uploader_or_owner on storage.objects;

create policy workspace_documents_update_uploader_or_owner
on storage.objects
for update
to authenticated
using (
  bucket_id = 'workspace-documents'
  and (
    owner_id = (select auth.uid())::text
    or (select app_private.has_workspace_role(
      app_private.storage_workspace_id(name),
      array['owner']::public.workspace_role[]
    ))
  )
)
with check (
  bucket_id = 'workspace-documents'
  and (select app_private.is_workspace_member(
    app_private.storage_workspace_id(name)
  ))
  and (
    split_part(name, '/', 2) = (select auth.uid())::text
    or (select app_private.has_workspace_role(
      app_private.storage_workspace_id(name),
      array['owner']::public.workspace_role[]
    ))
  )
);
