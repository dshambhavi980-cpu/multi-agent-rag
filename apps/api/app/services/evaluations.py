import asyncio
import hashlib
import json
import statistics
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from uuid import UUID, uuid4

from app.api.errors import ApplicationError
from app.core.logging import get_logger
from app.infrastructure.supabase.admin import SupabaseAdminClient
from app.models.evaluations import (
    CreateEvaluationRequest,
    EvaluationPage,
    EvaluationRun,
    EvaluationSuiteSummary,
)
from app.models.rag import CreateMessageRequest
from app.models.retrieval import RetrievalRequest
from app.services.evaluation_metrics import answer_metrics, release_gate, retrieval_metrics
from app.services.rag import GroundedRagService
from app.services.retrieval import HybridRetrievalService

SUITE_PATH = Path(__file__).resolve().parents[1] / "evaluation_suites" / "phase12_v1.json"
RETRIEVAL_VARIANTS = {
    "keyword_only": "sparse",
    "dense_only": "dense",
    "hybrid": "hybrid",
}
ANSWER_VARIANTS = {"simple_rag": "simple", "agentic": "agentic"}
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "timed_out", "awaiting_approval"}


class EvaluationService:
    def __init__(
        self,
        *,
        admin: SupabaseAdminClient,
        retrieval: HybridRetrievalService,
        rag: GroundedRagService,
        poll_seconds: float = 0.25,
        answer_timeout_seconds: float = 90,
    ) -> None:
        self.admin = admin
        self.retrieval = retrieval
        self.rag = rag
        self.poll_seconds = poll_seconds
        self.answer_timeout_seconds = answer_timeout_seconds
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._suite = cast(dict[str, Any], json.loads(SUITE_PATH.read_text(encoding="utf-8")))
        self._validate_suite()

    def _validate_suite(self) -> None:
        cases = cast(list[dict[str, Any]], self._suite.get("cases"))
        if len(cases) < 50:
            raise RuntimeError("The production evaluation suite requires at least 50 cases.")
        case_ids = [str(case.get("id")) for case in cases]
        if len(case_ids) != len(set(case_ids)):
            raise RuntimeError("Evaluation case IDs must be unique.")
        required_categories = {
            "lookup",
            "synthesis",
            "conflicting_evidence",
            "missing_evidence",
            "prompt_injection",
        }
        if {str(case.get("category")) for case in cases} != required_categories:
            raise RuntimeError("The evaluation suite does not cover every required category.")

    async def aclose(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def suite_summary(self) -> EvaluationSuiteSummary:
        categories: dict[str, int] = defaultdict(int)
        cases = cast(list[dict[str, Any]], self._suite["cases"])
        for case in cases:
            categories[str(case["category"])] += 1
        return EvaluationSuiteSummary.model_validate(
            {
                "suite": self._suite["suite"],
                "version": self._suite["version"],
                "reviewed_by": self._suite["reviewed_by"],
                "reviewed_at": self._suite["reviewed_at"],
                "case_count": len(cases),
                "categories": dict(categories),
                "thresholds": self._suite["thresholds"],
            }
        )

    async def list_runs(self, *, workspace_id: UUID, actor_id: UUID, limit: int) -> EvaluationPage:
        return EvaluationPage.model_validate(
            await self.admin.rpc(
                "list_evaluation_runs",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_limit": limit,
                },
            )
        )

    async def get(
        self, *, workspace_id: UUID, actor_id: UUID, evaluation_id: UUID
    ) -> EvaluationRun:
        return EvaluationRun.model_validate(
            await self.admin.rpc(
                "get_evaluation_run",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_evaluation_id": str(evaluation_id),
                },
            )
        )

    async def create(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        request_id: UUID,
        idempotency_key: str,
        body: CreateEvaluationRequest,
    ) -> EvaluationRun:
        cases = cast(list[dict[str, Any]], self._suite["cases"])[: body.max_cases]
        try:
            raw_created = await self.admin.rpc(
                "create_evaluation_run",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_actor_id": str(actor_id),
                    "p_suite": body.suite,
                    "p_suite_version": self._suite["version"],
                    "p_variants": body.variants,
                    "p_case_count": len(cases),
                    "p_request_key": idempotency_key,
                },
            )
        except Exception as exc:
            if "already running" in str(exc).lower() and not self._tasks:
                page = await self.list_runs(workspace_id=workspace_id, actor_id=actor_id, limit=10)
                for item in page.items:
                    if item.status in ("queued", "running"):
                        await self.admin.rpc(
                            "complete_evaluation_run",
                            {
                                "p_evaluation_id": str(item.id),
                                "p_workspace_id": str(workspace_id),
                                "p_metrics": {},
                                "p_gate_passed": False,
                                "p_gate_failures": ["process_restarted"],
                                "p_error": {
                                    "code": "PROCESS_RESTARTED",
                                    "detail": "Interrupted evaluation was cleared after server restart.",
                                },
                            },
                        )
                raw_created = await self.admin.rpc(
                    "create_evaluation_run",
                    {
                        "p_workspace_id": str(workspace_id),
                        "p_actor_id": str(actor_id),
                        "p_suite": body.suite,
                        "p_suite_version": self._suite["version"],
                        "p_variants": body.variants,
                        "p_case_count": len(cases),
                        "p_request_key": idempotency_key,
                    },
                )
            else:
                raise
        created = EvaluationRun.model_validate(raw_created)
        if created.status == "queued" and created.id not in self._tasks:
            task = asyncio.create_task(
                self._execute(
                    evaluation_id=created.id,
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    variants=body.variants,
                    cases=cases,
                ),
                name=f"evaluation-{created.id}",
            )
            self._tasks[created.id] = task
            task.add_done_callback(lambda _: self._tasks.pop(created.id, None))
        return created

    async def cancel(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        evaluation_id: UUID,
    ) -> EvaluationRun:
        task = self._tasks.get(evaluation_id)
        if task is not None and not task.done():
            task.cancel()
        await self.admin.rpc(
            "complete_evaluation_run",
            {
                "p_evaluation_id": str(evaluation_id),
                "p_workspace_id": str(workspace_id),
                "p_metrics": {},
                "p_gate_passed": False,
                "p_gate_failures": ["cancelled_by_user"],
                "p_error": {"code": "CANCELLED", "detail": "Evaluation run was cancelled by user."},
            },
        )
        return await self.get(
            workspace_id=workspace_id,
            actor_id=actor_id,
            evaluation_id=evaluation_id,
        )

    async def seed_benchmark_corpus(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        access_token: str,
        app_state: Any,
    ) -> dict[str, Any]:
        corpus_dir = Path(__file__).resolve().parents[4] / "benchmarks" / "retrieval" / "corpus"
        if not corpus_dir.is_dir():
            corpus_dir = Path("benchmarks/retrieval/corpus").resolve()

        corpus_files = ["operations.md", "recovery.md", "security.md"]
        data_client = getattr(app_state, "supabase_data", None)
        storage_client = getattr(app_state, "supabase_storage", None)
        worker = getattr(app_state, "ingestion_worker", None)

        existing_filenames: set[str] = set()
        if data_client is not None:
            try:
                docs = await data_client.list_documents(
                    access_token=access_token, workspace_id=workspace_id, limit=50
                )
                existing_filenames = {doc.filename for doc in docs if doc.status != "failed"}
            except Exception:
                pass

        seeded = []
        already_present = []
        for filename in corpus_files:
            file_path = corpus_dir / filename
            if not file_path.exists():
                continue
            if filename in existing_filenames:
                already_present.append(filename)
                continue

            content = file_path.read_bytes()
            actual_hash = hashlib.sha256(content).hexdigest()
            upload_id = uuid4()
            expires_at = datetime.now(UTC) + timedelta(hours=2)
            object_path = f"{workspace_id}/{actor_id}/{upload_id}/source.md"

            if data_client is not None:
                await data_client.create_upload_session(
                    access_token=access_token,
                    record={
                        "id": str(upload_id),
                        "workspace_id": str(workspace_id),
                        "uploaded_by": str(actor_id),
                        "object_path": object_path,
                        "filename": filename,
                        "expected_content_type": "text/markdown",
                        "expected_size_bytes": len(content),
                        "expected_sha256": actual_hash,
                        "expires_at": expires_at.isoformat(),
                    },
                )
            if storage_client is not None:
                await storage_client.upload(object_path, content, "text/markdown")

            await self.admin.rpc(
                "finalize_document_upload",
                {
                    "p_upload_id": str(upload_id),
                    "p_actor_id": str(actor_id),
                    "p_actual_sha256": actual_hash,
                    "p_actual_size_bytes": len(content),
                    "p_actual_content_type": "text/markdown",
                    "p_request_id": str(uuid4()),
                    "p_title": filename.replace(".md", "").replace("_", " ").title(),
                    "p_tags": ["benchmark", "phase12"],
                },
            )
            if worker is not None:
                if hasattr(worker, "cache_document_content"):
                    worker.cache_document_content(object_path, content)
                if hasattr(worker, "notify"):
                    worker.notify()
            seeded.append(filename)

        return {
            "seeded": seeded,
            "already_present": already_present,
            "total_benchmark_files": len(corpus_files),
            "status": "ready" if not seeded else "indexing",
        }

    async def get_corpus_status(
        self,
        *,
        workspace_id: UUID,
        access_token: str,
        app_state: Any,
    ) -> dict[str, Any]:
        corpus_files = ["operations.md", "recovery.md", "security.md"]
        data_client = getattr(app_state, "supabase_data", None)
        existing: dict[str, str] = {}
        if data_client is not None:
            try:
                docs = await data_client.list_documents(
                    access_token=access_token, workspace_id=workspace_id, limit=50
                )
                for doc in docs:
                    if doc.filename in corpus_files:
                        existing[doc.filename] = doc.status
            except Exception:
                pass

        all_ready = len(existing) == len(corpus_files) and all(
            status == "ready" for status in existing.values()
        )
        return {
            "ready": all_ready,
            "indexed_count": sum(1 for status in existing.values() if status == "ready"),
            "total_count": len(corpus_files),
            "documents": [
                {"filename": fn, "status": existing.get(fn, "missing")}
                for fn in corpus_files
            ],
        }

    async def _execute(  # noqa: PLR0913
        self,
        *,
        evaluation_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        request_id: UUID,
        variants: Sequence[str],
        cases: list[dict[str, Any]],
    ) -> None:
        records: list[dict[str, Any]] = []
        try:
            await self.admin.rpc(
                "start_evaluation_run",
                {
                    "p_evaluation_id": str(evaluation_id),
                    "p_workspace_id": str(workspace_id),
                },
            )
            conversation_id: UUID | None = None
            if any(variant in ANSWER_VARIANTS for variant in variants):
                conversation = await self.rag.create_conversation(
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    title=f"Evaluation {str(evaluation_id)[:8]}",
                    idempotency_key=f"evaluation-conversation-{evaluation_id}",
                )
                conversation_id = conversation.id
            for case in cases:
                for variant in variants:
                    record = (
                        await self._evaluate_retrieval(
                            workspace_id=workspace_id,
                            actor_id=actor_id,
                            request_id=request_id,
                            case=case,
                            variant=variant,
                        )
                        if variant in RETRIEVAL_VARIANTS
                        else await self._evaluate_answer(
                            evaluation_id=evaluation_id,
                            workspace_id=workspace_id,
                            actor_id=actor_id,
                            request_id=request_id,
                            conversation_id=cast(UUID, conversation_id),
                            case=case,
                            variant=variant,
                        )
                    )
                    records.append(record)
                    await self._record(evaluation_id, workspace_id, record)
            metrics = self._aggregate(records)
            thresholds = cast(dict[str, float], self._suite["thresholds"])
            gate = release_gate(
                metrics,
                citation_precision_threshold=thresholds["citation_precision"],
                hybrid_ndcg_gain_threshold=thresholds["hybrid_ndcg_gain_over_dense"],
            )
            await self.admin.rpc(
                "complete_evaluation_run",
                {
                    "p_evaluation_id": str(evaluation_id),
                    "p_workspace_id": str(workspace_id),
                    "p_metrics": metrics,
                    "p_gate_passed": gate.passed,
                    "p_gate_failures": gate.failures,
                    "p_error": None,
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            get_logger().exception(
                "evaluation_failed",
                evaluation_id=str(evaluation_id),
                workspace_id=str(workspace_id),
            )
            await self.admin.rpc(
                "complete_evaluation_run",
                {
                    "p_evaluation_id": str(evaluation_id),
                    "p_workspace_id": str(workspace_id),
                    "p_metrics": self._aggregate(records),
                    "p_gate_passed": False,
                    "p_gate_failures": ["execution_failure"],
                    "p_error": {
                        "code": getattr(exc, "code", "EVALUATION_FAILED"),
                        "detail": "The bounded evaluation run did not complete.",
                    },
                },
            )

    async def _evaluate_retrieval(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        request_id: UUID,
        case: dict[str, Any],
        variant: str,
    ) -> dict[str, Any]:
        started = perf_counter()
        response = await self.retrieval.search(
            workspace_id=workspace_id,
            actor_id=actor_id,
            request_id=request_id,
            request=RetrievalRequest(
                query=str(case["question"]),
                mode=cast(Any, RETRIEVAL_VARIANTS[variant]),
                limit=10,
                candidate_count=30,
            ),
        )
        items = [item.model_dump(mode="json") for item in response.items]
        metrics = retrieval_metrics(
            items,
            expected_filenames=cast(list[str], case["expected_filenames"]),
            expected_source_chunks=cast(list[str], case["expected_source_chunks"]),
        )
        forbidden = set(cast(list[str], case.get("forbidden_filenames", [])))
        tenant_safe = not any(str(item["filename"]) in forbidden for item in items)
        metrics["tenant_isolation_pass"] = float(tenant_safe)
        passed = metrics["recall"] > 0 and tenant_safe
        return {
            "case_id": case["id"],
            "category": case["category"],
            "variant": variant,
            "status": "passed" if passed else "failed",
            "metrics": metrics,
            "latency_ms": round((perf_counter() - started) * 1000, 3),
            "model_calls": 1,
            "prompt_tokens": max(1, len(str(case["question"])) // 4),
            "output_tokens": 0,
            "failure_code": None if passed else "RETRIEVAL_EXPECTATION_MISSED",
            "details": {
                "retrieved_filenames": [item["filename"] for item in items[:10]],
                "critical": bool(case.get("critical")),
            },
        }

    async def _evaluate_answer(  # noqa: PLR0913
        self,
        *,
        evaluation_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        request_id: UUID,
        conversation_id: UUID,
        case: dict[str, Any],
        variant: str,
    ) -> dict[str, Any]:
        started = perf_counter()
        accepted = await self.rag.start_run(
            workspace_id=workspace_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            request_id=request_id,
            idempotency_key=f"eval-{evaluation_id}-{case['id']}-{variant}",
            body=CreateMessageRequest(
                content=str(case["question"]),
                force_mode=cast(Any, ANSWER_VARIANTS[variant]),
            ),
        )
        deadline = asyncio.get_running_loop().time() + self.answer_timeout_seconds
        run = await self.rag.get_run(
            workspace_id=workspace_id, actor_id=actor_id, run_id=accepted.run_id
        )
        while run.status not in TERMINAL_RUN_STATUSES:
            if asyncio.get_running_loop().time() >= deadline:
                raise ApplicationError(
                    "EVALUATION_CASE_TIMEOUT",
                    "Evaluation case timed out",
                    "A generated-answer evaluation exceeded its bounded timeout.",
                    status=504,
                )
            await asyncio.sleep(self.poll_seconds)
            run = await self.rag.get_run(
                workspace_id=workspace_id, actor_id=actor_id, run_id=accepted.run_id
            )
        if run.status != "completed" or run.output_message_id is None:
            return {
                "case_id": case["id"],
                "category": case["category"],
                "variant": variant,
                "status": "error",
                "metrics": {"safety_pass": 0.0},
                "latency_ms": round((perf_counter() - started) * 1000, 3),
                "model_calls": 1,
                "prompt_tokens": 0,
                "output_tokens": 0,
                "failure_code": f"RUN_{run.status.upper()}",
                "details": {"critical": bool(case.get("critical"))},
            }
        conversation = await self.rag.get_conversation(
            workspace_id=workspace_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
        )
        message = next(item for item in conversation.messages if item.id == run.output_message_id)
        citations = [citation.model_dump(mode="json") for citation in message.citations]
        metrics = answer_metrics(
            answer=message.content,
            citations=citations,
            expected_filenames=cast(list[str], case["expected_filenames"]),
            expected_facts=cast(list[str], case["expected_facts"]),
            forbidden_terms=cast(list[str], case["forbidden_answer_terms"]),
            forbidden_filenames=cast(list[str], case.get("forbidden_filenames", [])),
            answer_status=message.answer_status,
        )
        if not case["expected_filenames"] and message.answer_status == "insufficient_evidence":
            metrics["answer_coverage"] = 1.0
        trace = await self.rag.get_observability_trace(
            workspace_id=workspace_id, actor_id=actor_id, run_id=accepted.run_id
        )
        passed = (
            metrics["safety_pass"] == 1
            and metrics["groundedness"] == 1
            and metrics["answer_coverage"] > 0
        )
        return {
            "case_id": case["id"],
            "category": case["category"],
            "variant": variant,
            "status": "passed" if passed else "failed",
            "metrics": metrics,
            "latency_ms": round((perf_counter() - started) * 1000, 3),
            "model_calls": 1,
            "prompt_tokens": trace.input_tokens or 0,
            "output_tokens": trace.output_tokens or 0,
            "failure_code": None if passed else "ANSWER_EXPECTATION_MISSED",
            "details": {"critical": bool(case.get("critical"))},
        }

    async def _record(
        self, evaluation_id: UUID, workspace_id: UUID, record: dict[str, Any]
    ) -> None:
        await self.admin.rpc(
            "record_evaluation_result",
            {
                "p_evaluation_id": str(evaluation_id),
                "p_workspace_id": str(workspace_id),
                **{f"p_{key}": value for key, value in record.items()},
            },
        )

    @staticmethod
    def _aggregate(records: list[dict[str, Any]]) -> dict[str, float]:
        if not records:
            return {}
        grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for record in records:
            for metric, value in cast(dict[str, float], record["metrics"]).items():
                grouped[str(record["variant"])][metric].append(float(value))
        aggregate: dict[str, float] = {}
        for variant, metrics in grouped.items():
            for metric, values in metrics.items():
                aggregate[f"{variant}_{metric}"] = round(statistics.fmean(values), 4)
        answer_records = [record for record in records if record["variant"] in ANSWER_VARIANTS]
        critical = [
            record
            for record in answer_records
            if cast(dict[str, Any], record["details"]).get("critical")
        ]
        tenant = [
            record
            for record in records
            if record["case_id"] in {"adversarial-05", "adversarial-10"}
        ]
        citation_values = [
            float(cast(dict[str, float], record["metrics"])["citation_precision"])
            for record in answer_records
            if "citation_precision" in cast(dict[str, float], record["metrics"])
        ]
        aggregate["citation_precision"] = round(
            statistics.fmean(citation_values) if citation_values else 0, 4
        )
        aggregate["critical_safety_pass_rate"] = round(
            statistics.fmean(
                float(cast(dict[str, float], record["metrics"]).get("safety_pass", 0))
                for record in critical
            )
            if critical
            else 0,
            4,
        )
        aggregate["tenant_isolation_pass_rate"] = round(
            statistics.fmean(
                float(
                    cast(dict[str, float], record["metrics"]).get(
                        "tenant_isolation_pass",
                        cast(dict[str, float], record["metrics"]).get("safety_pass", 0),
                    )
                )
                for record in tenant
            )
            if tenant
            else 0,
            4,
        )
        hybrid = aggregate.get("hybrid_ndcg", 0)
        dense = aggregate.get("dense_only_ndcg", 0)
        aggregate["hybrid_ndcg_gain"] = round(
            (hybrid - dense) / dense if dense else float(hybrid > 0), 4
        )
        latencies = sorted(float(record["latency_ms"]) for record in records)
        aggregate["p95_latency_ms"] = round(latencies[round((len(latencies) - 1) * 0.95)], 3)
        aggregate["model_calls"] = float(sum(int(record["model_calls"]) for record in records))
        aggregate["prompt_tokens"] = float(sum(int(record["prompt_tokens"]) for record in records))
        aggregate["output_tokens"] = float(sum(int(record["output_tokens"]) for record in records))
        aggregate["failure_rate"] = round(
            sum(record["status"] != "passed" for record in records) / len(records), 4
        )
        return aggregate
