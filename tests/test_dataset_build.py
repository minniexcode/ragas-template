import csv
import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from pydantic import ValidationError

from rag_eval.dataset_builder.generator.question_generator import OpenAIQuestionGenerator
from rag_eval.dataset_builder.generator.validators import dedupe_samples, validate_draft_sample
from rag_eval.dataset_builder.models import DraftQuestionSample, ParsedDocument, SourceChunk
from rag_eval.dataset_builder.parser.aliyun_document_parser import AliyunDocumentParser
from rag_eval.dataset_builder.parser.aliyun_docmind_gateway import AliyunDocmindGateway
from rag_eval.dataset_builder.parser.aliyun_layout_normalizer import normalize_layouts
from rag_eval.dataset_builder.runner import load_dataset_build_job, run_dataset_build
from rag_eval.dataset_builder.schema import DatasetBuildConfigModel
from rag_eval.dataset_builder.sources import discover_pdf_files
from rag_eval.settings import EvaluationSettings


class FakeParser:
    def __init__(self, documents_by_name, failures=None):
        self.documents_by_name = documents_by_name
        self.failures = failures or set()

    def parse(self, pdf_path: Path):
        if pdf_path.name in self.failures:
            raise RuntimeError(f"parse failed for {pdf_path.name}")
        return self.documents_by_name[pdf_path.name]


class FakeGenerator:
    def __init__(self, outputs_by_doc_id):
        self.outputs_by_doc_id = outputs_by_doc_id

    def generate(self, document, *, max_questions, max_chunks_per_question, job_name):
        return list(self.outputs_by_doc_id.get(document.doc_id, []))


class FakeGateway(AliyunDocmindGateway):
    def __init__(self, settings, *, statuses=None, layouts=None):
        super().__init__(settings)
        self.statuses = list(statuses or [])
        self.layouts = list(layouts or [])

    def submit_parse_task(self, pdf_path: Path) -> str:
        return "task-1"

    def get_task_status(self, task_id: str):
        if self.statuses:
            return self.statuses.pop(0)
        return {"status": "succeeded", "doc_id": "doc-1", "doc_name": "doc1.pdf"}

    def fetch_layouts(self, task_id: str):
        return list(self.layouts)


class DatasetBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path("tests/.tmp").resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = root / self._testMethodName
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.input_dir = self.temp_dir / "pdfs"
        self.input_dir.mkdir(parents=True, exist_ok=True)
        (self.input_dir / "doc1.pdf").write_bytes(b"%PDF-1.4 doc1")
        (self.input_dir / "doc2.pdf").write_bytes(b"%PDF-1.4 doc2")

        self.config_path = self.temp_dir / "dataset-build.yaml"
        self.config_path.write_text(
            "\n".join(
                [
                    "job_name: sample-build",
                    "input:",
                    f"  path: {self.input_dir.as_posix()}",
                    "  glob: '*.pdf'",
                    "parser:",
                    "  provider: aliyun_docmind",
                    "  failure_mode: skip",
                    "generation:",
                    "  output_type: online_question_bank",
                    "  review_mode: draft_with_manual_review",
                    "  max_questions_per_document: 3",
                    "  max_source_chunks_per_question: 2",
                    "output:",
                    f"  dataset_path: {(self.temp_dir / 'generated' / 'draft.csv').as_posix()}",
                    f"  artifact_dir: {(self.temp_dir / 'outputs').as_posix()}",
                    "runtime:",
                    "  max_documents: 2",
                ]
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_document(self, doc_id: str, doc_name: str) -> ParsedDocument:
        chunk = SourceChunk(
            chunk_id=f"{doc_id}-chunk-1",
            doc_id=doc_id,
            doc_name=doc_name,
            text="Section content for review.",
            page_start=1,
            page_end=2,
            section_path="Chapter 1 > Scope",
            section_title="Scope",
            source_layout_ids=["layout-1"],
        )
        return ParsedDocument(
            doc_id=doc_id,
            doc_name=doc_name,
            raw_text=chunk.text,
            structure_nodes=[],
            semantic_blocks=[],
            source_chunks=[chunk],
            metadata={},
        )

    def test_load_dataset_build_job_resolves_paths_and_defaults(self) -> None:
        settings = EvaluationSettings.model_construct(dataset_generator_model="env-model")
        job = load_dataset_build_job(self.config_path, settings=settings)
        self.assertEqual(job.job_name, "sample-build")
        self.assertEqual(job.generation_model, "env-model")
        self.assertTrue(job.dataset_path.is_absolute())
        self.assertEqual(job.failure_mode, "skip")

    def test_load_dataset_build_job_prefers_yaml_generation_model(self) -> None:
        config_path = self.temp_dir / "dataset-build-with-model.yaml"
        config_path.write_text(
            self.config_path.read_text(encoding="utf-8").replace(
                "generation:\n",
                "generation:\n  model: yaml-model\n",
            ),
            encoding="utf-8",
        )
        settings = EvaluationSettings.model_construct(dataset_generator_model="env-model")
        job = load_dataset_build_job(config_path, settings=settings)
        self.assertEqual(job.generation_model, "yaml-model")

    def test_load_dataset_build_job_uses_env_default_failure_mode(self) -> None:
        config_path = self.temp_dir / "dataset-build-without-failure-mode.yaml"
        config_path.write_text(
            self.config_path.read_text(encoding="utf-8").replace("  failure_mode: skip\n", ""),
            encoding="utf-8",
        )
        settings = EvaluationSettings.model_construct(
            dataset_generator_model="env-model",
            parser_failure_mode="skip",
        )
        job = load_dataset_build_job(config_path, settings=settings)
        self.assertEqual(job.failure_mode, "skip")

    def test_discover_pdf_files_rejects_missing_or_empty_input(self) -> None:
        with self.assertRaises(FileNotFoundError):
            discover_pdf_files(self.temp_dir / "missing")

        empty_dir = self.temp_dir / "empty"
        empty_dir.mkdir()
        with self.assertRaises(ValueError):
            discover_pdf_files(empty_dir)

    def test_discover_pdf_files_accepts_single_pdf_file(self) -> None:
        pdf_path = self.input_dir / "doc1.pdf"
        files = discover_pdf_files(pdf_path)
        self.assertEqual(files, [pdf_path])

    def test_dataset_build_schema_rejects_missing_required_fields(self) -> None:
        with self.assertRaises(ValidationError):
            DatasetBuildConfigModel.model_validate(
                {
                    "job_name": "sample-build",
                    "parser": {"provider": "aliyun_docmind"},
                    "generation": {
                        "output_type": "online_question_bank",
                        "review_mode": "draft_with_manual_review",
                    },
                    "output": {
                        "dataset_path": "draft.csv",
                        "artifact_dir": "outputs",
                    },
                }
            )

    def test_dataset_build_schema_rejects_invalid_enums(self) -> None:
        with self.assertRaises(ValidationError):
            DatasetBuildConfigModel.model_validate(
                {
                    "job_name": "sample-build",
                    "input": {"path": self.input_dir.as_posix()},
                    "parser": {"provider": "other-provider", "failure_mode": "ignore"},
                    "generation": {
                        "output_type": "other-output",
                        "review_mode": "auto_publish",
                    },
                    "output": {
                        "dataset_path": "draft.csv",
                        "artifact_dir": "outputs",
                    },
                }
            )

    def test_normalize_layouts_applies_core_rules(self) -> None:
        layouts = [
            {"type": "toc", "text": "目录", "page": 1, "layout_id": "toc-1"},
            {"type": "heading", "text": "第一章 总则", "page": 2, "layout_id": "h1", "level": 1},
            {"type": "paragraph", "text": "第一段。", "page": 2, "layout_id": "p1"},
            {"type": "caption", "text": "系统示意图", "page": 2, "layout_id": "c1"},
            {
                "type": "table",
                "rows": [["字段", "说明"], ["名称", "项目名称"]],
                "page": 3,
                "layout_id": "t1",
            },
        ]
        document = normalize_layouts(doc_id="doc-1", doc_name="sample.pdf", layouts=layouts, max_chunk_chars=80, overlap_chars=10)
        self.assertEqual(len(document.structure_nodes), 1)
        self.assertEqual(document.structure_nodes[0].section_path, "第一章 总则")
        self.assertEqual(len(document.semantic_blocks), 1)
        self.assertIn("图注:", document.semantic_blocks[0].text)
        self.assertIn("字段 | 说明", document.semantic_blocks[0].text)
        self.assertEqual(document.source_chunks[0].page_start, 2)
        self.assertEqual(document.source_chunks[0].page_end, 3)

    def test_normalize_layouts_splits_long_text_into_multiple_chunks(self) -> None:
        long_text = "A" * 220
        layouts = [
            {"type": "heading", "text": "Chapter 1", "page": 1, "layout_id": "h1", "level": 1},
            {"type": "paragraph", "text": long_text, "page": 1, "layout_id": "p1"},
        ]
        document = normalize_layouts(
            doc_id="doc-1",
            doc_name="sample.pdf",
            layouts=layouts,
            max_chunk_chars=100,
            overlap_chars=20,
        )
        self.assertGreaterEqual(len(document.source_chunks), 3)
        self.assertTrue(all(chunk.section_title == "Chapter 1" for chunk in document.source_chunks))

    def test_validate_and_dedupe_generated_samples(self) -> None:
        document = self._make_document("doc-1", "doc1.pdf")
        valid = DraftQuestionSample(
            sample_id="doc-1-q1",
            question="这份文档的范围是什么？",
            ground_truth="文档说明了适用范围。",
            scenario="sample-build",
            language="zh",
            doc_id="doc-1",
            doc_name="doc1.pdf",
            section_path="Chapter 1 > Scope",
            page_start=1,
            page_end=2,
            source_chunk_ids=["doc-1-chunk-1"],
            question_type="summary",
            difficulty="easy",
        )
        invalid = DraftQuestionSample(
            sample_id="doc-1-q2",
            question="",
            ground_truth="",
            scenario="sample-build",
            language="zh",
            doc_id="doc-2",
            doc_name="doc1.pdf",
            section_path="",
            page_start=0,
            page_end=0,
            source_chunk_ids=["missing-chunk"],
            question_type="invalid",
            difficulty="invalid",
        )
        duplicate = DraftQuestionSample(
            sample_id="doc-1-q3",
            question="  这份文档的范围是什么？ ",
            ground_truth="文档说明了适用范围",
            scenario="sample-build",
            language="zh",
            doc_id="doc-1",
            doc_name="doc1.pdf",
            section_path="Chapter 1 > Scope",
            page_start=1,
            page_end=2,
            source_chunk_ids=["doc-1-chunk-1"],
            question_type="summary",
            difficulty="easy",
        )
        self.assertEqual(validate_draft_sample(valid, document=document), [])
        self.assertTrue(validate_draft_sample(invalid, document=document))
        self.assertEqual(len(dedupe_samples([valid, duplicate])), 1)

    def test_validate_rejects_too_many_source_chunks(self) -> None:
        document = self._make_document("doc-1", "doc1.pdf")
        document.source_chunks.append(
            SourceChunk(
                chunk_id="doc-1-chunk-2",
                doc_id="doc-1",
                doc_name="doc1.pdf",
                text="More content",
                page_start=2,
                page_end=3,
                section_path="Chapter 1 > Scope",
                section_title="Scope",
                source_layout_ids=["layout-2"],
            )
        )
        sample = DraftQuestionSample(
            sample_id="doc-1-q1",
            question="What is the scope?",
            ground_truth="It defines scope.",
            scenario="sample-build",
            language="en",
            doc_id="doc-1",
            doc_name="doc1.pdf",
            section_path="Chapter 1 > Scope",
            page_start=1,
            page_end=3,
            source_chunk_ids=["doc-1-chunk-1", "doc-1-chunk-2"],
            question_type="fact",
            difficulty="easy",
        )
        errors = validate_draft_sample(
            sample,
            document=document,
            max_source_chunks_per_question=1,
        )
        self.assertTrue(any("exceeds limit" in error for error in errors))

    def test_dedupe_keeps_only_one_question_per_chunk_group(self) -> None:
        sample_a = DraftQuestionSample(
            sample_id="doc-1-q1",
            question="What is the scope?",
            ground_truth="It defines the scope.",
            scenario="sample-build",
            language="en",
            doc_id="doc-1",
            doc_name="doc1.pdf",
            section_path="Chapter 1 > Scope",
            page_start=1,
            page_end=2,
            source_chunk_ids=["doc-1-chunk-1"],
            question_type="fact",
            difficulty="easy",
        )
        sample_b = DraftQuestionSample(
            sample_id="doc-1-q2",
            question="How is the scope described?",
            ground_truth="The scope is described in the first section.",
            scenario="sample-build",
            language="en",
            doc_id="doc-1",
            doc_name="doc1.pdf",
            section_path="Chapter 1 > Scope",
            page_start=1,
            page_end=2,
            source_chunk_ids=["doc-1-chunk-1"],
            question_type="summary",
            difficulty="medium",
        )
        self.assertEqual(len(dedupe_samples([sample_a, sample_b])), 1)

    def test_aliyun_gateway_parse_success_failure_and_timeout(self) -> None:
        settings = EvaluationSettings.model_construct(
            aliyun_parse_poll_interval_seconds=1,
            aliyun_parse_timeout_seconds=1,
        )
        pdf_path = self.input_dir / "doc1.pdf"

        success_gateway = FakeGateway(
            settings,
            statuses=[{"status": "running"}, {"status": "succeeded", "doc_id": "doc-1", "doc_name": "doc1.pdf"}],
            layouts=[{"type": "paragraph", "text": "hello", "page": 1, "layout_id": "p1"}],
        )
        with mock.patch("rag_eval.dataset_builder.parser.aliyun_docmind_gateway.time.sleep", return_value=None), mock.patch(
            "rag_eval.dataset_builder.parser.aliyun_docmind_gateway.time.monotonic",
            side_effect=[0.0, 0.1, 0.2],
        ):
            payload = success_gateway.parse_document(pdf_path)
        self.assertEqual(payload["doc_id"], "doc-1")
        self.assertEqual(len(payload["layouts"]), 1)

        failure_gateway = FakeGateway(settings, statuses=[{"status": "failed", "message": "bad file"}])
        with self.assertRaises(RuntimeError):
            failure_gateway.parse_document(pdf_path)

        timeout_gateway = FakeGateway(settings, statuses=[{"status": "running"}, {"status": "running"}])
        with mock.patch("rag_eval.dataset_builder.parser.aliyun_docmind_gateway.time.sleep", return_value=None), mock.patch(
            "rag_eval.dataset_builder.parser.aliyun_docmind_gateway.time.monotonic",
            side_effect=[0.0, 2.0],
        ):
            with self.assertRaises(TimeoutError):
                timeout_gateway.parse_document(pdf_path)

    def test_aliyun_gateway_reports_missing_sdk(self) -> None:
        settings = EvaluationSettings.model_construct(
            aliyun_parse_poll_interval_seconds=1,
            aliyun_parse_timeout_seconds=1,
        )
        gateway = AliyunDocmindGateway(settings)

        with mock.patch("rag_eval.dataset_builder.parser.aliyun_docmind_gateway.DocmindClient", None), mock.patch(
            "rag_eval.dataset_builder.parser.aliyun_docmind_gateway.docmind_models", None
        ), mock.patch("rag_eval.dataset_builder.parser.aliyun_docmind_gateway.openapi_models", None), mock.patch(
            "rag_eval.dataset_builder.parser.aliyun_docmind_gateway.runtime_models", None
        ):
            with self.assertRaises(ImportError):
                gateway._load_sdk()

    def test_document_parser_rejects_empty_layouts(self) -> None:
        settings = EvaluationSettings.model_construct(
            aliyun_parse_poll_interval_seconds=1,
            aliyun_parse_timeout_seconds=1,
        )
        gateway = FakeGateway(
            settings,
            statuses=[{"status": "succeeded", "doc_id": "doc-1", "doc_name": "doc1.pdf"}],
            layouts=[],
        )
        parser = AliyunDocumentParser(gateway)
        with self.assertRaises(ValueError):
            parser.parse(self.input_dir / "doc1.pdf")

    def test_run_dataset_build_skip_mode_writes_all_artifacts(self) -> None:
        doc1 = self._make_document("doc-1", "doc1.pdf")
        parser = FakeParser(
            {"doc1.pdf": doc1},
            failures={"doc2.pdf"},
        )
        generator = FakeGenerator(
            {
                "doc-1": [
                    DraftQuestionSample(
                        sample_id="doc-1-q1",
                        question="What is the scope?",
                        ground_truth="It defines the scope.",
                        scenario="sample-build",
                        language="en",
                        doc_id="doc-1",
                        doc_name="doc1.pdf",
                        section_path="Chapter 1 > Scope",
                        page_start=1,
                        page_end=2,
                        source_chunk_ids=["doc-1-chunk-1"],
                        question_type="fact",
                        difficulty="easy",
                    )
                ]
            }
        )

        result = run_dataset_build(
            self.config_path,
            settings=EvaluationSettings.model_construct(dataset_generator_model="stub-model"),
            parser=parser,
            generator=generator,
        )

        self.assertEqual(len(result.documents), 1)
        self.assertEqual(len(result.parse_failures), 1)
        self.assertEqual(len(result.draft_samples), 1)
        self.assertTrue(result.artifact_paths.documents_jsonl.exists())
        self.assertTrue(result.artifact_paths.semantic_blocks_jsonl.exists())
        self.assertTrue(result.artifact_paths.source_chunks_jsonl.exists())
        self.assertTrue(result.artifact_paths.dataset_draft_csv.exists())
        self.assertTrue(result.artifact_paths.parse_failures_csv.exists())
        self.assertTrue(result.artifact_paths.metadata_json.exists())
        self.assertTrue(result.job.dataset_path.exists())
        latest_dir = result.job.artifact_dir / "latest"
        self.assertTrue((latest_dir / "source_chunks.jsonl").exists())
        self.assertTrue((latest_dir / "dataset_draft.csv").exists())
        self.assertTrue((latest_dir / "metadata.json").exists())

        with result.artifact_paths.parse_failures_csv.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertIn("doc2.pdf", rows[0]["file_path"])

        metadata = json.loads(result.artifact_paths.metadata_json.read_text(encoding="utf-8"))
        self.assertEqual(metadata["stats"]["documents_processed"], 1)
        self.assertEqual(metadata["stats"]["parse_failures"], 1)
        latest_metadata = json.loads((latest_dir / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(latest_metadata["run_id"], result.run_id)

        with result.artifact_paths.source_chunks_jsonl.open(encoding="utf-8") as handle:
            run_chunks = handle.read()
        with (latest_dir / "source_chunks.jsonl").open(encoding="utf-8") as handle:
            latest_chunks = handle.read()
        self.assertEqual(latest_chunks, run_chunks)

    def test_run_dataset_build_single_pdf_input(self) -> None:
        single_pdf_config = self.temp_dir / "single-pdf-build.yaml"
        single_pdf_config.write_text(
            self.config_path.read_text(encoding="utf-8").replace(
                f"  path: {self.input_dir.as_posix()}",
                f"  path: {(self.input_dir / 'doc1.pdf').as_posix()}",
            ),
            encoding="utf-8",
        )
        parser = FakeParser({"doc1.pdf": self._make_document("doc-1", "doc1.pdf")})
        generator = FakeGenerator(
            {
                "doc-1": [
                    DraftQuestionSample(
                        sample_id="doc-1-q1",
                        question="What is the scope?",
                        ground_truth="It defines the scope.",
                        scenario="sample-build",
                        language="en",
                        doc_id="doc-1",
                        doc_name="doc1.pdf",
                        section_path="Chapter 1 > Scope",
                        page_start=1,
                        page_end=2,
                        source_chunk_ids=["doc-1-chunk-1"],
                        question_type="fact",
                        difficulty="easy",
                    )
                ]
            }
        )
        result = run_dataset_build(
            single_pdf_config,
            settings=EvaluationSettings.model_construct(dataset_generator_model="stub-model"),
            parser=parser,
            generator=generator,
        )
        self.assertEqual(len(result.documents), 1)
        self.assertEqual(result.documents[0].doc_name, "doc1.pdf")
        self.assertEqual(len(result.draft_samples), 1)

    def test_run_dataset_build_caps_questions_per_document(self) -> None:
        doc1 = self._make_document("doc-1", "doc1.pdf")
        parser = FakeParser({"doc1.pdf": doc1, "doc2.pdf": self._make_document("doc-2", "doc2.pdf")})
        generator = FakeGenerator(
            {
                "doc-1": [
                    DraftQuestionSample(
                        sample_id=f"doc-1-q{index}",
                        question=f"Question {index}?",
                        ground_truth=f"Answer {index}.",
                        scenario="sample-build",
                        language="en",
                        doc_id="doc-1",
                        doc_name="doc1.pdf",
                        section_path="Chapter 1 > Scope",
                        page_start=1,
                        page_end=2,
                        source_chunk_ids=[f"doc-1-chunk-{index}"],
                        question_type="fact",
                        difficulty="easy",
                    )
                    for index in range(1, 5)
                ]
            }
        )
        # Rebuild the doc with enough chunk ids for validation to pass.
        doc1.source_chunks = [
            SourceChunk(
                chunk_id=f"doc-1-chunk-{index}",
                doc_id="doc-1",
                doc_name="doc1.pdf",
                text=f"Chunk {index}",
                page_start=index,
                page_end=index,
                section_path="Chapter 1 > Scope",
                section_title="Scope",
                source_layout_ids=[f"layout-{index}"],
            )
            for index in range(1, 5)
        ]

        result = run_dataset_build(
            self.config_path,
            settings=EvaluationSettings.model_construct(dataset_generator_model="stub-model"),
            parser=parser,
            generator=generator,
        )
        self.assertLessEqual(len([item for item in result.draft_samples if item.doc_id == "doc-1"]), 3)

    def test_run_dataset_build_filters_questions_exceeding_chunk_limit(self) -> None:
        doc1 = self._make_document("doc-1", "doc1.pdf")
        doc1.source_chunks.append(
            SourceChunk(
                chunk_id="doc-1-chunk-2",
                doc_id="doc-1",
                doc_name="doc1.pdf",
                text="Chunk 2",
                page_start=2,
                page_end=2,
                section_path="Chapter 1 > Scope",
                section_title="Scope",
                source_layout_ids=["layout-2"],
            )
        )
        parser = FakeParser({"doc1.pdf": doc1}, failures={"doc2.pdf"})
        generator = FakeGenerator(
            {
                "doc-1": [
                    DraftQuestionSample(
                        sample_id="doc-1-q1",
                        question="Too many chunks?",
                        ground_truth="This cites two chunks.",
                        scenario="sample-build",
                        language="en",
                        doc_id="doc-1",
                        doc_name="doc1.pdf",
                        section_path="Chapter 1 > Scope",
                        page_start=1,
                        page_end=2,
                        source_chunk_ids=["doc-1-chunk-1", "doc-1-chunk-2"],
                        question_type="fact",
                        difficulty="easy",
                    )
                ]
            }
        )

        strict_config = self.temp_dir / "dataset-build-strict.yaml"
        strict_config.write_text(
            self.config_path.read_text(encoding="utf-8").replace(
                "  max_source_chunks_per_question: 2",
                "  max_source_chunks_per_question: 1",
            ),
            encoding="utf-8",
        )
        result = run_dataset_build(
            strict_config,
            settings=EvaluationSettings.model_construct(dataset_generator_model="stub-model"),
            parser=parser,
            generator=generator,
        )
        self.assertEqual(len(result.draft_samples), 0)

    def test_run_dataset_build_fail_mode_raises(self) -> None:
        fail_config = self.temp_dir / "dataset-build-fail.yaml"
        fail_config.write_text(self.config_path.read_text(encoding="utf-8").replace("failure_mode: skip", "failure_mode: fail"), encoding="utf-8")
        parser = FakeParser({}, failures={"doc1.pdf"})
        generator = FakeGenerator({})

        with self.assertRaises(RuntimeError):
            run_dataset_build(
                fail_config,
                settings=EvaluationSettings.model_construct(dataset_generator_model="stub-model"),
                parser=parser,
                generator=generator,
            )


class QuestionGeneratorTests(unittest.TestCase):
    def _make_document(self) -> ParsedDocument:
        return ParsedDocument(
            doc_id="doc-1",
            doc_name="doc1.pdf",
            raw_text="source text",
            structure_nodes=[],
            semantic_blocks=[],
            source_chunks=[
                SourceChunk(
                    chunk_id="doc-1-chunk-1",
                    doc_id="doc-1",
                    doc_name="doc1.pdf",
                    text="Scope content",
                    page_start=1,
                    page_end=1,
                    section_path="Chapter 1 > Scope",
                    section_title="Scope",
                    source_layout_ids=["layout-1"],
                ),
                SourceChunk(
                    chunk_id="doc-1-chunk-2",
                    doc_id="doc-1",
                    doc_name="doc1.pdf",
                    text="Procedure content",
                    page_start=2,
                    page_end=2,
                    section_path="Chapter 2 > Process",
                    section_title="Process",
                    source_layout_ids=["layout-2"],
                ),
            ],
            metadata={},
        )

    def _make_fake_client(self, content: str):
        class FakeResponse:
            def __init__(self, payload: str):
                self.choices = [type("Choice", (), {"message": type("Message", (), {"content": payload})()})()]

        class FakeCompletions:
            def __init__(self, payload: str):
                self.payload = payload

            def create(self, **kwargs):
                return FakeResponse(self.payload)

        return type(
            "FakeClient",
            (),
            {"chat": type("Chat", (), {"completions": FakeCompletions(content)})()},
        )()

    def test_question_generator_builds_samples_from_json_response(self) -> None:
        settings = EvaluationSettings.model_construct(openai_api_key="test-key")
        content = json.dumps(
            {
                "samples": [
                    {
                        "question": "What is the scope?",
                        "ground_truth": "It defines the scope.",
                        "source_chunk_ids": ["doc-1-chunk-1"],
                        "question_type": "fact",
                        "difficulty": "easy",
                    },
                    {
                        "question": "Summarize the process.",
                        "ground_truth": "It explains the process.",
                        "source_chunk_ids": ["doc-1-chunk-2"],
                        "question_type": "summary",
                        "difficulty": "medium",
                    },
                ]
            }
        )
        generator = OpenAIQuestionGenerator(
            settings=settings,
            model="stub-model",
            client=self._make_fake_client(content),
        )
        samples = generator.generate(
            self._make_document(),
            max_questions=1,
            max_chunks_per_question=2,
            job_name="sample-build",
        )
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0].sample_id, "doc-1-q1")
        self.assertEqual(samples[0].section_path, "Chapter 1 > Scope")

    def test_question_generator_rejects_invalid_json(self) -> None:
        settings = EvaluationSettings.model_construct(openai_api_key="test-key")
        generator = OpenAIQuestionGenerator(
            settings=settings,
            model="stub-model",
            client=self._make_fake_client("not-json"),
        )
        with self.assertRaises(ValueError):
            generator.generate(
                self._make_document(),
                max_questions=1,
                max_chunks_per_question=2,
                job_name="sample-build",
            )

    def test_question_generator_rejects_non_list_samples(self) -> None:
        settings = EvaluationSettings.model_construct(openai_api_key="test-key")
        content = json.dumps({"samples": {"question": "bad-shape"}})
        generator = OpenAIQuestionGenerator(
            settings=settings,
            model="stub-model",
            client=self._make_fake_client(content),
        )
        with self.assertRaises(ValueError):
            generator.generate(
                self._make_document(),
                max_questions=1,
                max_chunks_per_question=2,
                job_name="sample-build",
            )


class MainCliParseTests(unittest.TestCase):
    def test_cli_options_are_mutually_exclusive(self) -> None:
        import main

        with mock.patch("sys.argv", ["main.py", "--scenario", "a.yaml", "--dataset-build-config", "b.yaml"]):
            with self.assertRaises(SystemExit):
                main.parse_args()
