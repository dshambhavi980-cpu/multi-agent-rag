import asyncio
from datetime import datetime, timezone
import httpx
from app.core.config import get_settings
from app.infrastructure.supabase.storage import SupabaseStorageClient
from app.services.document_parser import parse_document
from app.infrastructure.cloudflare import CloudflareEmbeddingClient, CloudflareEmbeddingConfig

async def backfill():
    settings = get_settings()
    storage = SupabaseStorageClient(
        supabase_url=str(settings.supabase_url),
        publishable_key=settings.supabase_publishable_key.get_secret_value(),
        service_key=settings.supabase_service_role_key.get_secret_value(),
        timeout_seconds=60,
    )
    url = str(settings.supabase_url).rstrip("/")
    key = settings.supabase_service_role_key.get_secret_value()

    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.get(
            f"{url}/rest/v1/documents?select=*&limit=5",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
        docs = res.json()
        print(f"Found {len(docs)} documents in db.", flush=True)

        embed_client = CloudflareEmbeddingClient(
            account_id=settings.cloudflare_account_id,
            api_token=settings.cloudflare_api_token.get_secret_value(),
            config=CloudflareEmbeddingConfig(
                model="@cf/baai/bge-base-en-v1.5",
                dimensions=768,
                timeout_seconds=30.0,
                max_retries=3,
                retry_base_seconds=1.0,
            ),
        )

        for doc in docs:
            doc_id = doc["id"]
            ws_id = doc["workspace_id"]
            obj_path = doc["object_path"]
            filename = doc["filename"]
            print(f"\n--- Processing document: {filename} ({doc_id}) ---", flush=True)

            # Check if any diagram chunk already exists
            existing_fig_res = await client.get(
                f"{url}/rest/v1/document_chunks?document_id=eq.{doc_id}&content=like.*Diagram:*&select=id&limit=1",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
            )
            if existing_fig_res.json():
                print(f"Diagrams already indexed for {filename}, skipping.", flush=True)
                continue

            data = await storage.download(obj_path)
            parsed = parse_document(data, "application/pdf")
            print(f"Parsed {len(parsed.pages)} pages, found {len(parsed.figures)} figures.", flush=True)

            # Fetch current chunk max index
            chunk_res = await client.get(
                f"{url}/rest/v1/document_chunks?document_id=eq.{doc_id}&select=chunk_index&order=chunk_index.desc&limit=1",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
            )
            existing_chunks = chunk_res.json()
            max_idx = (existing_chunks[0]["chunk_index"] + 1) if existing_chunks else 0
            print(f"Starting figure chunk index at {max_idx}.", flush=True)

            # Upload figures and prepare chunk contents
            fig_items = []
            for idx, fig in enumerate(parsed.figures):
                asset_path = f"{ws_id}/{doc_id}/{fig.figure_id}.{fig.image_ext}"
                content_type = f"image/{fig.image_ext}" if fig.image_ext in {"png", "jpeg", "webp"} else "image/png"
                public_url = await storage.upload_public(asset_path, fig.image_bytes, content_type)
                content = (
                    f"### Diagram: {fig.caption}\n\n"
                    f"![{fig.caption}]({public_url})\n\n"
                    f"**Figure Context**: {fig.caption}. {fig.context_snippet}"
                )
                fig_items.append({
                    "fig": fig,
                    "content": content,
                    "chunk_index": max_idx + idx,
                })

            print(f"Uploaded {len(fig_items)} figures to document-assets bucket. Generating embeddings...", flush=True)

            # Embed and insert in batches of 20
            now_iso = datetime.now(timezone.utc).isoformat()
            doc_title = doc.get("title") or filename
            total_inserted = 0

            for b_idx in range(0, len(fig_items), 20):
                batch = fig_items[b_idx : b_idx + 20]
                texts = [item["content"] for item in batch]
                vectors = await embed_client.embed_documents(texts, title=doc_title)

                chunk_rows = [
                    {
                        "workspace_id": ws_id,
                        "document_id": doc_id,
                        "chunk_index": item["chunk_index"],
                        "processing_version": 1,
                        "strategy": "heading_recursive",
                        "content": item["content"],
                        "page_start": item["fig"].page_number,
                        "page_end": item["fig"].page_number,
                        "section_heading": item["fig"].caption,
                        "char_start": 0,
                        "char_end": len(item["content"]),
                        "token_count": max(1, len(item["content"].split())),
                        "embedding": vectors[i],
                        "embedding_model": "@cf/baai/bge-base-en-v1.5",
                        "embedded_at": now_iso,
                    }
                    for i, item in enumerate(batch)
                ]

                ins_res = await client.post(
                    f"{url}/rest/v1/document_chunks",
                    headers={"apikey": key, "Authorization": f"Bearer {key}"},
                    json=chunk_rows,
                )
                if ins_res.status_code in (200, 201):
                    total_inserted += len(chunk_rows)
                    print(f"Inserted batch {b_idx//20 + 1}/{(len(fig_items)+19)//20} ({total_inserted}/{len(fig_items)} chunks)", flush=True)
                else:
                    print(f"Chunk insert error: {ins_res.status_code} {ins_res.text}", flush=True)

            # Update document chunk_count
            await client.patch(
                f"{url}/rest/v1/documents?id=eq.{doc_id}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                json={"chunk_count": max_idx + total_inserted},
            )
            print(f"Successfully indexed all {total_inserted} diagrams for {filename}!", flush=True)

        await embed_client.aclose()
    await storage.aclose()

if __name__ == "__main__":
    asyncio.run(backfill())
