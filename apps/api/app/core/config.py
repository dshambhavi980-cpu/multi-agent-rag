from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Multi-Agent Hybrid RAG API"
    app_version: str = "0.1.0"
    environment: Literal["local", "test", "preview", "production"] = "local"
    git_sha: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    docs_enabled: bool = True
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [AnyHttpUrl("http://localhost:5173")]
    )
    cold_start_window_seconds: int = Field(default=60, ge=0, le=600)
    supabase_url: AnyHttpUrl | None = None
    supabase_publishable_key: SecretStr | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_jwks_cache_seconds: int = Field(default=600, ge=60, le=3600)
    supabase_http_timeout_seconds: float = Field(default=3.0, gt=0, le=15)
    ingestion_worker_enabled: bool = True
    ingestion_poll_seconds: float = Field(default=1.0, ge=0.1, le=30)
    ingestion_visibility_seconds: int = Field(default=120, ge=30, le=900)
    ingestion_batch_size: int = Field(default=2, ge=1, le=10)
    ingestion_parse_timeout_seconds: float = Field(default=45, gt=0, le=300)
    index_strategy: Literal["fixed", "recursive", "heading_recursive"] = "heading_recursive"
    index_target_chars: int = Field(default=1800, ge=256, le=4000)
    index_overlap_chars: int = Field(default=0, ge=0, le=1000)
    index_version: int = Field(default=1, ge=1)
    embedding_batch_size: int = Field(default=16, ge=1, le=100)
    embedding_dimensions: Literal[768] = 768
    embedding_timeout_seconds: float = Field(default=30, gt=0, le=120)
    embedding_max_retries: int = Field(default=2, ge=0, le=5)
    embedding_retry_base_seconds: float = Field(default=1, gt=0, le=30)
    query_embedding_cache_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    retrieval_cache_ttl_seconds: int = Field(default=900, ge=0, le=3600)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=1000)
    retrieval_dense_weight: float = Field(default=1, ge=0, le=10)
    retrieval_sparse_weight: float = Field(default=1, ge=0, le=10)
    retrieval_duplicate_threshold: float = Field(default=0.92, ge=0.8, le=1)
    rag_evidence_limit: int = Field(default=6, ge=1, le=10)
    rag_candidate_count: int = Field(default=30, ge=10, le=100)
    rag_timeout_seconds: float = Field(default=45, gt=1, le=120)
    rag_insufficient_semantic_threshold: float = Field(default=0.25, ge=0, le=1)
    rag_event_poll_seconds: float = Field(default=0.1, ge=0.05, le=2)
    rag_heartbeat_seconds: float = Field(default=15, ge=5, le=60)
    agent_max_steps: int = Field(default=8, ge=4, le=8)
    agent_max_subtasks: int = Field(default=3, ge=1, le=5)
    agent_max_concurrent_retrievals: int = Field(default=3, ge=1, le=5)
    agent_timeout_seconds: float = Field(default=60, gt=5, le=120)
    agent_context_char_budget: int = Field(default=18000, ge=2000, le=40000)
    agent_output_char_budget: int = Field(default=12000, ge=1000, le=30000)
    approval_confidence_threshold: float = Field(default=0.72, ge=0, le=1)
    approval_citation_coverage_threshold: float = Field(default=0.5, ge=0, le=1)
    approval_expires_hours: int = Field(default=24, ge=1, le=168)
    memory_prompt_char_budget: int = Field(default=6000, ge=1000, le=12000)
    memory_summary_char_budget: int = Field(default=2200, ge=500, le=4000)
    memory_item_char_budget: int = Field(default=1800, ge=500, le=4000)
    memory_recent_message_limit: int = Field(default=8, ge=2, le=20)
    memory_retrieval_limit: int = Field(default=8, ge=1, le=20)
    memory_cleanup_interval_seconds: int = Field(default=21600, ge=300, le=86400)
    generation_timeout_seconds: float = Field(default=30, gt=1, le=120)
    generation_max_retries: int = Field(default=1, ge=0, le=3)
    generation_retry_base_seconds: float = Field(default=0.5, gt=0, le=10)
    generation_max_output_tokens: int = Field(default=1024, ge=64, le=4096)
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_chat_model: str = Field(
        default="gemini-3.1-flash-lite",
        min_length=1,
        validation_alias="GEMINI_CHAT_MODEL",
    )
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001",
        validation_alias="GEMINI_EMBEDDING_MODEL",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
