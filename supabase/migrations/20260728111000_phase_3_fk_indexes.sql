create index document_pages_document_workspace_idx
  on public.document_pages (document_id, workspace_id);

create index document_chunks_document_workspace_idx
  on public.document_chunks (document_id, workspace_id);

create index ingestion_jobs_document_workspace_idx
  on public.ingestion_jobs (document_id, workspace_id);
