import shutil
import unittest
from pathlib import Path

import pandas as pd

from rag_eval.adapters.base import AppAdapter
from rag_eval.datasets.normalizers import normalize_records
from rag_eval.execution.evaluator import Evaluator
from rag_eval.metrics.pipeline import MetricPipeline
from rag_eval.shared.models import AppAdapterConfig, DatasetConfig, RuntimeConfig, Scenario


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
            }
        ]
        valid, invalid = normalize_records(records, mode="online")
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 0)
        self.assertEqual(valid[0].answer, "")
        self.assertEqual(valid[0].contexts, [])

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
