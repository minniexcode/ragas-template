import os
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from pydantic_settings import SettingsConfigDict

from rag_eval.config.loader import load_scenario
from rag_eval.datasets.normalizers import normalize_records
from rag_eval.execution.evaluator import Evaluator
from rag_eval.metrics.pipeline import MetricPipeline
from rag_eval.reporting.summary import build_summary_markdown
from rag_eval.reporting.writers import write_run_artifacts
from rag_eval.settings import EvaluationSettings
from rag_eval.shared.models import EvaluationResult


class EnvOnlySettings(EvaluationSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")


class FakeMetric:
    def __init__(self, value: float):
        self.value = value

    async def ascore(self, **kwargs):
        class Result:
            def __init__(self, value: float):
                self.value = value

        return Result(self.value)


class SlowMetric:
    async def ascore(self, **kwargs):
        await __import__("asyncio").sleep(0.05)
        return type("Result", (), {"value": 1.0})()


class OpenAIConfigTests(unittest.TestCase):
    def test_openai_client_kwargs_without_base_url(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            settings = EnvOnlySettings()
            self.assertEqual(
                settings.openai_client_kwargs,
                {"api_key": "test-key", "base_url": "http://6.86.80.4:30080/v1", "timeout": 30.0},
            )

    def test_openai_client_kwargs_with_base_url(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_BASE_URL": "https://proxy.example/v1",
            },
            clear=True,
        ):
            settings = EnvOnlySettings()
            self.assertEqual(
                settings.openai_client_kwargs,
                {"api_key": "test-key", "base_url": "https://proxy.example/v1", "timeout": 30.0},
            )

    def test_settings_defaults(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = EnvOnlySettings()
            self.assertEqual(settings.openai_base_url, "http://6.86.80.4:30080/v1")
            self.assertEqual(settings.ragas_judge_model, "deepseek-v4-flash")
            self.assertEqual(settings.ragas_embedding_model, "text-embedding-v3")
            self.assertEqual(settings.openai_timeout_seconds, 30.0)
            self.assertEqual(settings.ragas_metric_timeout_seconds, 45.0)
            self.assertEqual(settings.batch_size, 8)


class ScenarioAndDatasetTests(unittest.TestCase):
    def test_load_scenario_resolves_relative_paths(self) -> None:
        scenario = load_scenario("scenarios/offline/sample-offline.yaml")
        self.assertEqual(scenario.mode, "offline")
        self.assertTrue(scenario.dataset.path.name.endswith(".csv"))
        self.assertTrue(scenario.output_dir.name == "sample-offline-baseline")

    def test_scenario_snapshot_serializes_path_static_kwargs(self) -> None:
        scenario = load_scenario("scenarios/online/sample-pdf-question-bank-online.yaml")
        snapshot = scenario.snapshot()
        self.assertIsInstance(snapshot["app_adapter"]["static_kwargs"]["source_chunks_path"], str)
        self.assertTrue(
            snapshot["app_adapter"]["static_kwargs"]["source_chunks_path"].endswith("source_chunks.jsonl")
        )

    def test_load_sample_pdf_offline_smoke_scenario(self) -> None:
        scenario = load_scenario("scenarios/offline/sample-pdf-offline-smoke.yaml")
        self.assertEqual(scenario.mode, "offline")
        self.assertEqual(scenario.dataset.path.name, "sample_pdf_offline_smoke.csv")
        self.assertEqual(scenario.output_dir.name, "sample-pdf-offline-smoke")

    def test_normalize_records_splits_valid_and_invalid(self) -> None:
        records = [
            {
                "question": "Q1",
                "contexts": '["C1"]',
                "answer": "A1",
                "ground_truth": "G1",
            },
            {
                "question": "",
                "contexts": "",
                "answer": "",
                "ground_truth": "",
            },
        ]
        valid, invalid = normalize_records(records)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 1)
        self.assertEqual(valid[0].contexts, ["C1"])

    def test_normalize_sample_pdf_offline_smoke_row(self) -> None:
        frame = pd.read_csv("datasets/normalized/sample_pdf_offline_smoke.csv")
        valid, invalid = normalize_records(frame.to_dict(orient="records"))
        self.assertEqual(len(invalid), 0)
        self.assertEqual(len(valid), 3)
        self.assertTrue(valid[0].answer)
        self.assertTrue(valid[0].ground_truth)
        self.assertTrue(valid[0].contexts)


class EvaluatorAndReportingTests(unittest.TestCase):
    def test_metric_pipeline_scores_sample(self) -> None:
        pipeline = MetricPipeline(
            metrics={
                "faithfulness": FakeMetric(0.1),
                "answer_relevancy": FakeMetric(0.2),
                "context_recall": FakeMetric(0.3),
                "context_precision": FakeMetric(0.4),
            }
        )
        valid, _ = normalize_records(
            [
                {
                    "question": "What is RAG?",
                    "contexts": ["RAG combines retrieval and generation."],
                    "answer": "RAG combines retrieval and generation.",
                    "ground_truth": "RAG combines retrieval and generation.",
                }
            ]
        )
        score = __import__("asyncio").run(pipeline.score_sample(valid[0]))
        self.assertEqual(score.metrics["faithfulness"], 0.1)
        self.assertEqual(score.metrics["context_precision"], 0.4)

    def test_metric_pipeline_captures_metric_timeout_without_aborting(self) -> None:
        pipeline = MetricPipeline(
            metrics={
                "faithfulness": SlowMetric(),
                "answer_relevancy": FakeMetric(0.2),
            },
            metric_timeout_seconds=0.01,
        )
        valid, _ = normalize_records(
            [
                {
                    "question": "What is RAG?",
                    "contexts": ["RAG combines retrieval and generation."],
                    "answer": "RAG combines retrieval and generation.",
                    "ground_truth": "RAG combines retrieval and generation.",
                }
            ]
        )
        score = __import__("asyncio").run(pipeline.score_sample(valid[0]))
        self.assertEqual(score.metrics["faithfulness"], 1.0)
        self.assertEqual(score.metrics["answer_relevancy"], 0.2)
        self.assertEqual(score.error, "")

    def test_evaluator_and_reporting_write_run_assets(self) -> None:
        temp_root = Path("tests/.tmp/run-assets")
        temp_root.mkdir(parents=True, exist_ok=True)
        for child in temp_root.iterdir():
            if child.is_dir():
                import shutil

                shutil.rmtree(child)
            else:
                child.unlink()
        output_root = temp_root
        try:
            scenario = load_scenario("scenarios/offline/sample-offline.yaml")
            scenario.output_dir = output_root

            pipeline = MetricPipeline(
                metrics={
                    "faithfulness": FakeMetric(0.1),
                    "answer_relevancy": FakeMetric(0.2),
                    "context_recall": FakeMetric(0.3),
                    "context_precision": FakeMetric(0.4),
                }
            )
            evaluator = Evaluator(scenario=scenario, metric_pipeline=pipeline)
            result = evaluator.evaluate()
            write_run_artifacts(result)

            run_dir = output_root / result.run_id
            self.assertTrue((run_dir / "scenario.snapshot.yaml").exists())
            self.assertTrue((run_dir / "scores.csv").exists())
            self.assertTrue((run_dir / "invalid.csv").exists())
            self.assertTrue((run_dir / "summary.md").exists())
            self.assertTrue((run_dir / "metadata.json").exists())

            scores = pd.read_csv(run_dir / "scores.csv")
            self.assertEqual(len(scores), 3)
            self.assertIn("faithfulness", scores.columns)
        finally:
            import shutil

            shutil.rmtree(temp_root, ignore_errors=True)

    def test_summary_markdown_lists_all_scored_samples_and_errors(self) -> None:
        scenario = load_scenario("scenarios/offline/sample-offline.yaml")
        valid, invalid = normalize_records(
            [
                {
                    "sample_id": "sample-1",
                    "question": "Q1",
                    "contexts": ["C1"],
                    "answer": "A1",
                    "ground_truth": "G1",
                },
                {
                    "sample_id": "sample-2",
                    "question": "Q2",
                    "contexts": ["C2"],
                    "answer": "A2",
                    "ground_truth": "G2",
                },
                {
                    "sample_id": "sample-3",
                    "question": "Q3",
                    "contexts": ["C3"],
                    "answer": "A3",
                    "ground_truth": "G3",
                },
                {
                    "sample_id": "sample-4",
                    "question": "Q4",
                    "contexts": ["C4"],
                    "answer": "A4",
                    "ground_truth": "G4",
                },
            ]
        )
        summary = build_summary_markdown(
            EvaluationResult(
                scenario=scenario,
                run_id="test-run",
                started_at="2026-06-10T00:00:00+00:00",
                finished_at="2026-06-10T00:01:00+00:00",
                valid_samples=valid,
                invalid_samples=invalid,
                score_rows=[
                    {
                        "sample_id": "sample-1",
                        "faithfulness": 1.0,
                        "answer_relevancy": 0.9,
                        "context_recall": 1.0,
                        "context_precision": 0.8,
                        "error": "",
                    },
                    {
                        "sample_id": "sample-2",
                        "faithfulness": 0.8,
                        "answer_relevancy": 0.7,
                        "context_recall": 0.9,
                        "context_precision": 0.6,
                        "error": "faithfulness: timeout",
                    },
                    {
                        "sample_id": "sample-3",
                        "faithfulness": 0.7,
                        "answer_relevancy": 0.6,
                        "context_recall": 0.8,
                        "context_precision": 0.5,
                        "error": "",
                    },
                    {
                        "sample_id": "sample-4",
                        "faithfulness": 0.6,
                        "answer_relevancy": 0.5,
                        "context_recall": 0.7,
                        "context_precision": 0.4,
                        "error": "context_precision: failed",
                    },
                ],
            )
        )

        self.assertIn("## Per-sample Scores", summary)
        self.assertIn("sample-1", summary)
        self.assertIn("sample-2", summary)
        self.assertIn("sample-3", summary)
        self.assertIn("sample-4", summary)
        self.assertIn("faithfulness", summary)
        self.assertIn("answer_relevancy", summary)
        self.assertIn("context_recall", summary)
        self.assertIn("context_precision", summary)
        self.assertIn("error", summary)
        self.assertIn("faithfulness: timeout", summary)
        self.assertIn("context_precision: failed", summary)


if __name__ == "__main__":
    unittest.main()
