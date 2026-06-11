"""Gateway abstraction for Alibaba Cloud document parsing workflows."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

try:
    from alibabacloud_docmind_api20220711 import models as docmind_models
    from alibabacloud_docmind_api20220711.client import Client as DocmindClient
    from alibabacloud_tea_openapi import models as openapi_models
    from alibabacloud_tea_util import models as runtime_models
except ImportError:
    # Keep Alibaba SDK optional so offline flows and tests can import this module.
    DocmindClient = None
    docmind_models = None
    openapi_models = None
    runtime_models = None

try:
    from alibabacloud_credentials.client import Client as CredentialClient
except ImportError:
    CredentialClient = None

from rag_eval.settings import EvaluationSettings


class AliyunDocmindGateway:
    """Thin gateway interface around the external Alibaba document parser service."""

    def __init__(self, settings: EvaluationSettings):
        """Store parser-related settings needed by the gateway implementation."""
        self.settings = settings
        self._client = None
        self._models = None
        self._runtime_models = None

    def _load_sdk(self) -> tuple[Any, Any, Any, Any]:
        """Load Alibaba SDK modules lazily so tests and offline flows do not require them."""
        if (
            DocmindClient is None
            or openapi_models is None
            or docmind_models is None
            or runtime_models is None
        ):
            raise ImportError(
                "Alibaba Cloud Docmind SDK is not installed. "
                "Install alibabacloud-docmind-api20220711, "
                "alibabacloud-tea-openapi, alibabacloud-tea-util, and "
                "alibabacloud-credentials."
            )
        return DocmindClient, openapi_models, docmind_models, runtime_models

    def _resolve_credentials(self) -> tuple[str, str]:
        """Resolve AccessKey credentials from settings or the Alibaba credentials client."""
        if self.settings.alibaba_access_key_id and self.settings.alibaba_access_key_secret:
            return self.settings.alibaba_access_key_id, self.settings.alibaba_access_key_secret

        if CredentialClient is None:
            raise ImportError(
                "Alibaba Cloud credentials SDK is not installed and no explicit "
                "ALIBABA_ACCESS_KEY_ID / ALIBABA_ACCESS_KEY_SECRET were provided."
            )

        credential_client = CredentialClient()
        credential = credential_client.get_credential()
        return credential.get_access_key_id(), credential.get_access_key_secret()

    def _init_client(self) -> Any:
        """Create and cache the underlying Alibaba SDK client."""
        if self._client is not None:
            return self._client

        client_class, openapi_models, docmind_models, runtime_models = self._load_sdk()
        access_key_id, access_key_secret = self._resolve_credentials()
        endpoint = (self.settings.alibaba_endpoint or "docmind-api.cn-hangzhou.aliyuncs.com").strip()
        config = openapi_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
        )
        config.endpoint = endpoint
        config.region_id = "cn-hangzhou"
        config.type = "access_key"

        self._client = client_class(config)
        self._models = docmind_models
        self._runtime_models = runtime_models
        return self._client

    @staticmethod
    def _to_plain_dict(value: Any) -> dict[str, Any]:
        """Convert SDK response objects into ordinary dictionaries."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_map"):
            return value.to_map()
        if hasattr(value, "__dict__"):
            return {
                key: getattr(value, key)
                for key in vars(value)
                if not key.startswith("_")
            }
        return {}

    @staticmethod
    def _extract_layouts(payload: Any) -> list[dict[str, Any]]:
        """Convert layout collections from SDK payloads into plain dictionaries."""
        if payload is None:
            return []
        if isinstance(payload, dict):
            layouts = payload.get("layouts") or payload.get("Layouts") or []
        else:
            layouts = getattr(payload, "layouts", None) or getattr(payload, "Layouts", None) or []
        normalized: list[dict[str, Any]] = []
        for item in layouts:
            normalized.append(AliyunDocmindGateway._to_plain_dict(item))
        return normalized

    def submit_parse_task(self, pdf_path: Path) -> str:
        """Submit one PDF parse task and return the remote task identifier."""
        client = self._init_client()
        runtime = self._runtime_models.RuntimeOptions()
        file_name = pdf_path.name
        with pdf_path.open("rb") as handle:
            request = self._models.SubmitDocParserJobAdvanceRequest(
                file_url_object=handle,
                file_name=file_name,
                file_name_extension=pdf_path.suffix.lstrip(".").lower() or "pdf",
                llm_enhancement=self.settings.aliyun_llm_enhancement,
                enhancement_mode=self.settings.aliyun_enhancement_mode,
            )
            response = client.submit_doc_parser_job_advance(request, runtime)

        payload = self._to_plain_dict(getattr(getattr(response, "body", None), "data", None))
        task_id = payload.get("id") or payload.get("Id")
        if not task_id:
            raise RuntimeError(f"Aliyun submit_doc_parser_job_advance returned no task id for {pdf_path.name}")
        return str(task_id)

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Fetch the current parse task status from the remote service."""
        client = self._init_client()
        request = self._models.QueryDocParserStatusRequest(id=task_id)
        response = client.query_doc_parser_status(request)
        payload = self._to_plain_dict(getattr(getattr(response, "body", None), "data", None))
        status = payload.get("status") or payload.get("Status")
        if status is not None and "status" not in payload:
            payload["status"] = status
        return payload

    def fetch_layouts(self, task_id: str) -> list[dict[str, Any]]:
        """Fetch normalized layout pages for a completed parse task."""
        client = self._init_client()
        layout_num = 0
        layout_step_size = min(max(1, self.settings.aliyun_parse_layout_step_size), 3000)
        collected: list[dict[str, Any]] = []

        while True:
            request = self._models.GetDocParserResultRequest(
                id=task_id,
                layout_step_size=layout_step_size,
                layout_num=layout_num,
            )
            response = client.get_doc_parser_result(request)
            payload = getattr(getattr(response, "body", None), "data", None)
            layouts = self._extract_layouts(payload)
            if not layouts:
                break
            collected.extend(layouts)
            layout_num += len(layouts)
            if len(layouts) < layout_step_size:
                break
        return collected

    def parse_document(self, pdf_path: Path) -> dict[str, Any]:
        """Run the submit/poll/fetch cycle and return a raw parse payload."""
        task_id = self.submit_parse_task(pdf_path)
        started_at = time.monotonic()
        poll_interval = max(1, self.settings.aliyun_parse_poll_interval_seconds)
        timeout_seconds = max(1, self.settings.aliyun_parse_timeout_seconds)

        while True:
            status = self.get_task_status(task_id)
            state = str(status.get("status", "")).lower()
            if state in {"succeeded", "success", "finished"}:
                layouts = self.fetch_layouts(task_id)
                return {
                    "task_id": task_id,
                    "status": state,
                    "doc_id": status.get("doc_id") or pdf_path.stem,
                    "doc_name": status.get("doc_name") or pdf_path.name,
                    "layouts": layouts,
                    "metadata": status,
                }
            if state in {"failed", "error"}:
                raise RuntimeError(f"Aliyun parse task failed for {pdf_path.name}: {status}")
            if time.monotonic() - started_at > timeout_seconds:
                raise TimeoutError(f"Aliyun parse task timed out for {pdf_path.name}")
            time.sleep(poll_interval)
