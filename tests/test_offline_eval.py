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
from rag_eval.reporting.writers import write_run_artifacts
from rag_eval.settings import EvaluationSettings


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


class OpenAIConfigTests(unittest.TestCase):
    def test_openai_client_kwargs_without_base_url(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            settings = EnvOnlySettings()
            self.assertEqual(settings.openai_client_kwargs, {"api_key": "test-key"})

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
                {"api_key": "test-key", "base_url": "https://proxy.example/v1"},
            )

    def test_settings_defaults(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = EnvOnlySettings()
            self.assertEqual(settings.ragas_judge_model, "gpt-4o-mini")
            self.assertEqual(settings.ragas_embedding_model, "text-embedding-3-large")
            self.assertEqual(settings.batch_size, 8)


class ScenarioAndDatasetTests(unittest.TestCase):
    def test_load_scenario_resolves_relative_paths(self) -> None:
        scenario = load_scenario("scenarios/offline/sample-offline.yaml")
        self.assertEqual(scenario.mode, "offline")
        self.assertTrue(scenario.dataset.path.name.endswith(".csv"))
        self.assertTrue(scenario.output_dir.name == "sample-offline-baseline")

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


if __name__ == "__main__":
    unittest.main()
