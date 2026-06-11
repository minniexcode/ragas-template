import shutil
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from rag_eval.adapters.base import AppAdapter
from rag_eval.config.loader import load_scenario
from rag_eval.datasets.normalizers import normalize_records
from rag_eval.execution.evaluator import Evaluator
from rag_eval.metrics.pipeline import MetricPipeline
from rag_eval.shared.models import AppAdapterConfig, DatasetConfig, RuntimeConfig, Scenario
from apps.pdf_question_bank import adapter as pdf_question_bank_adapter


class FakeMetric:
    def __init__(self, value: float):
        self.value = value

    async def ascore(self, **kwargs):
        class Result:
            def __init__(self, value: float):
                self.value = value

        return Result(self.value)


class FakeOnlineAdapter(AppAdapter):
    async def run(self, question: str, **kwargs):
        return {
            "answer": f"answer for {question}",
            "contexts": [f"context for {question}"],
            "raw_response": {"question": question, "metadata": kwargs},
        }


class ExplodingOnlineAdapter(AppAdapter):
    async def run(self, question: str, **kwargs):
        raise RuntimeError("boom")


class OnlineDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path("tests/.tmp").resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = root / self._testMethodName
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_online_records_allow_missing_answer_and_contexts_before_adapter(self) -> None:
        records = [
            {
                "sample_id": "sample-1",
                "question": "What is the policy scope?",
                "ground_truth": "It covers all employees.",
                "doc_id": "doc-1",
                "source_chunk_ids": '["doc-1-chunk-1"]',
            }
        ]
        valid, invalid = normalize_records(records, mode="online")
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 0)
        self.assertEqual(valid[0].answer, "")
        self.assertEqual(valid[0].contexts, [])
        self.assertEqual(valid[0].metadata["source_chunk_ids"], '["doc-1-chunk-1"]')

    def test_online_evaluator_enriches_dataset_and_scores(self) -> None:
        dataset_path = self.temp_dir / "online.csv"
        pd.DataFrame(
            [
                {
                    "sample_id": "sample-1",
                    "question": "What is the policy scope?",
                    "ground_truth": "It covers all employees.",
                    "doc_id": "doc-1",
                    "section_path": "Policy > Scope",
                    "source_chunk_ids": '["doc-1-chunk-1"]',
                }
            ]
        ).to_csv(dataset_path, index=False)

        scenario = Scenario(
            scenario_name="online-test",
            mode="online",
            dataset=DatasetConfig(path=dataset_path),
            judge_model="judge-model",
            embedding_model="embedding-model",
            metrics=["faithfulness"],
            output_dir=self.temp_dir / "outputs",
            runtime=RuntimeConfig(batch_size=1),
            app_adapter=AppAdapterConfig(type="python", callable="tests.fake:run"),
        )
        pipeline = MetricPipeline(metrics={"faithfulness": FakeMetric(0.8)})
        evaluator = Evaluator(scenario=scenario, metric_pipeline=pipeline, app_adapter=FakeOnlineAdapter())

        result = evaluator.evaluate()
        self.assertEqual(len(result.valid_samples), 1)
        self.assertEqual(len(result.invalid_samples), 0)
        self.assertEqual(result.valid_samples[0].answer, "answer for What is the policy scope?")
        self.assertEqual(result.valid_samples[0].contexts, ["context for What is the policy scope?"])
        self.assertEqual(result.score_rows[0]["faithfulness"], 0.8)

    def test_online_evaluator_captures_adapter_exception_type_in_invalid_rows(self) -> None:
        dataset_path = self.temp_dir / "online.csv"
        pd.DataFrame(
            [
                {
                    "sample_id": "sample-1",
                    "question": "What is the policy scope?",
                    "ground_truth": "It covers all employees.",
                    "doc_id": "doc-1",
                    "source_chunk_ids": '["doc-1-chunk-1"]',
                }
            ]
        ).to_csv(dataset_path, index=False)

        scenario = Scenario(
            scenario_name="online-test",
            mode="online",
            dataset=DatasetConfig(path=dataset_path),
            judge_model="judge-model",
            embedding_model="embedding-model",
            metrics=["faithfulness"],
            output_dir=self.temp_dir / "outputs",
            runtime=RuntimeConfig(batch_size=1),
            app_adapter=AppAdapterConfig(type="python", callable="tests.fake:run"),
        )
        pipeline = MetricPipeline(metrics={"faithfulness": FakeMetric(0.8)})
        evaluator = Evaluator(scenario=scenario, metric_pipeline=pipeline, app_adapter=ExplodingOnlineAdapter())

        result = evaluator.evaluate()
        self.assertEqual(len(result.valid_samples), 0)
        self.assertEqual(len(result.invalid_samples), 1)
        self.assertEqual(result.invalid_samples[0].error, "adapter failed [RuntimeError]: boom")


class FakeCompletionResponse:
    def __init__(self, content: str):
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


class FakeCompletions:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeCompletionResponse(self.content)


class PdfQuestionBankAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path("tests/.tmp").resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = root / self._testMethodName
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.source_chunks_path = self.temp_dir / "source_chunks.jsonl"
        self.source_chunks_path.write_text(
            "\n".join(
                [
                    '{"chunk_id":"doc-1-chunk-1","doc_id":"doc-1","doc_name":"doc1.pdf","text":"Scope covers all employees.","page_start":1,"page_end":1,"section_path":"Policy > Scope","section_title":"Scope","source_layout_ids":["layout-1"]}',
                    '{"chunk_id":"doc-1-chunk-2","doc_id":"doc-1","doc_name":"doc1.pdf","text":"Managers approve exceptions.","page_start":2,"page_end":2,"section_path":"Policy > Exceptions","section_title":"Exceptions","source_layout_ids":["layout-2"]}',
                ]
            ),
            encoding="utf-8",
        )
        pdf_question_bank_adapter._CHUNK_CACHE.clear()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        pdf_question_bank_adapter._CHUNK_CACHE.clear()

    def test_adapter_loads_chunks_and_returns_resolved_contexts(self) -> None:
        completions = FakeCompletions("It covers all employees.")
        client = type(
            "FakeClient",
            (),
            {"chat": type("Chat", (), {"completions": completions})()},
        )()

        result = pdf_question_bank_adapter.run(
            question="What is the policy scope?",
            source_chunks_path=str(self.source_chunks_path),
            model="stub-model",
            client=client,
            source_chunk_ids='["doc-1-chunk-1"]',
            doc_id="doc-1",
            doc_name="doc1.pdf",
            section_path="Policy > Scope",
        )

        self.assertEqual(result["answer"], "It covers all employees.")
        self.assertEqual(result["contexts"], ["Scope covers all employees."])
        self.assertEqual(result["raw_response"]["resolved_chunk_ids"], ["doc-1-chunk-1"])
        self.assertEqual(result["raw_response"]["model"], "stub-model")
        self.assertEqual(len(completions.calls), 1)
        self.assertEqual(completions.calls[0]["model"], "stub-model")
        self.assertEqual(completions.calls[0]["temperature"], 0)
        self.assertIn("Evidence chunks:", completions.calls[0]["messages"][1]["content"])

    def test_adapter_supports_multiple_chunk_ids(self) -> None:
        completions = FakeCompletions("Combined answer.")
        client = type(
            "FakeClient",
            (),
            {"chat": type("Chat", (), {"completions": completions})()},
        )()

        result = pdf_question_bank_adapter.run(
            question="What does the policy say?",
            source_chunks_path=str(self.source_chunks_path),
            model="stub-model",
            client=client,
            source_chunk_ids='["doc-1-chunk-1", "doc-1-chunk-2"]',
            doc_id="doc-1",
            doc_name="doc1.pdf",
        )

        self.assertEqual(
            result["contexts"],
            ["Scope covers all employees.", "Managers approve exceptions."],
        )
        self.assertEqual(
            result["raw_response"]["resolved_chunk_ids"],
            ["doc-1-chunk-1", "doc-1-chunk-2"],
        )

    def test_adapter_rejects_missing_source_chunk_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_chunk_ids is required"):
            pdf_question_bank_adapter.run(
                question="What is the policy scope?",
                source_chunks_path=str(self.source_chunks_path),
                model="stub-model",
                client=mock.Mock(),
            )

    def test_adapter_rejects_unknown_chunk_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_chunk_ids not found"):
            pdf_question_bank_adapter.run(
                question="What is the policy scope?",
                source_chunks_path=str(self.source_chunks_path),
                model="stub-model",
                client=mock.Mock(),
                source_chunk_ids='["missing-chunk"]',
            )

    def test_adapter_falls_back_to_latest_run_directory_when_latest_alias_is_missing(self) -> None:
        artifact_root = self.temp_dir / "sample-pdf-question-bank"
        run_dir = artifact_root / "2026-06-10T02-01-32.508056+00-00"
        run_dir.mkdir(parents=True, exist_ok=True)
        latest_path = artifact_root / "latest" / "source_chunks.jsonl"
        run_chunks_path = run_dir / "source_chunks.jsonl"
        run_chunks_path.write_text(self.source_chunks_path.read_text(encoding="utf-8"), encoding="utf-8")

        completions = FakeCompletions("It covers all employees.")
        client = type(
            "FakeClient",
            (),
            {"chat": type("Chat", (), {"completions": completions})()},
        )()

        result = pdf_question_bank_adapter.run(
            question="What is the policy scope?",
            source_chunks_path=str(latest_path),
            model="stub-model",
            client=client,
            source_chunk_ids='["doc-1-chunk-1"]',
            doc_id="doc-1",
        )

        self.assertEqual(result["contexts"], ["Scope covers all employees."])
        self.assertEqual(result["raw_response"]["resolved_chunk_ids"], ["doc-1-chunk-1"])

    def test_online_evaluator_handles_dataset_build_rows_with_python_adapter(self) -> None:
        dataset_path = self.temp_dir / "question_bank.csv"
        pd.DataFrame(
            [
                {
                    "sample_id": "sample-1",
                    "question": "What is the policy scope?",
                    "ground_truth": "It covers all employees.",
                    "doc_id": "doc-1",
                    "doc_name": "doc1.pdf",
                    "section_path": "Policy > Scope",
                    "source_chunk_ids": '["doc-1-chunk-1"]',
                }
            ]
        ).to_csv(dataset_path, index=False)

        completions = FakeCompletions("It covers all employees.")
        client = type(
            "FakeClient",
            (),
            {"chat": type("Chat", (), {"completions": completions})()},
        )()

        scenario = Scenario(
            scenario_name="online-question-bank-test",
            mode="online",
            dataset=DatasetConfig(path=dataset_path),
            judge_model="judge-model",
            embedding_model="embedding-model",
            metrics=["faithfulness"],
            output_dir=self.temp_dir / "outputs",
            runtime=RuntimeConfig(batch_size=1),
            app_adapter=AppAdapterConfig(
                type="python",
                callable="apps.pdf_question_bank.adapter:run",
                static_kwargs={
                    "source_chunks_path": str(self.source_chunks_path),
                    "model": "stub-model",
                    "client": client,
                },
            ),
        )
        pipeline = MetricPipeline(metrics={"faithfulness": FakeMetric(0.8)})
        from rag_eval.adapters.python import PythonFunctionAdapter

        evaluator = Evaluator(
            scenario=scenario,
            metric_pipeline=pipeline,
            app_adapter=PythonFunctionAdapter(scenario.app_adapter),
        )

        result = evaluator.evaluate()
        self.assertEqual(len(result.valid_samples), 1)
        self.assertEqual(len(result.invalid_samples), 0)
        self.assertEqual(result.valid_samples[0].answer, "It covers all employees.")
        self.assertEqual(result.valid_samples[0].contexts, ["Scope covers all employees."])
        self.assertEqual(result.score_rows[0]["faithfulness"], 0.8)
        self.assertEqual(
            result.valid_samples[0].metadata["raw_response"]["resolved_chunk_ids"],
            ["doc-1-chunk-1"],
        )

    def test_load_sample_pdf_online_scenario(self) -> None:
        scenario = load_scenario("scenarios/online/sample-pdf-question-bank-online.yaml")
        self.assertEqual(scenario.mode, "online")
        self.assertEqual(scenario.dataset.path.name, "sample-pdf-question-bank.csv")
        self.assertEqual(scenario.output_dir.name, "sample-pdf-question-bank")
        self.assertEqual(scenario.runtime.max_samples, 45)
        self.assertEqual(scenario.app_adapter.callable, "apps.pdf_question_bank.adapter:run")
        self.assertTrue(
            str(scenario.app_adapter.static_kwargs["source_chunks_path"]).endswith("source_chunks.jsonl")
        )
