# RAG 评测平台骨架

## 1. 项目定位

这个仓库现在已经从“单脚本离线评测”重构成一个可继续扩展的 **RAG 评测平台骨架**。核心目标不变：统一离线与在线评测入口，沉淀本地 run 资产，并且让多应用、多数据集、多场景对比变成标准流程。

架构边界来自 [docs/rag-eval-architecture.md](/C:/Users/A200477427/Learnings/ragas-template/docs/rag-eval-architecture.md)，当前代码已经按该文档落了第一版工程结构。

如果你想快速理解一次评测在代码里是怎么跑起来的，可以继续看：

- [docs/rag-eval-engine-flow.md](/C:/Users/A200477427/Learnings/ragas-template/docs/rag-eval-engine-flow.md)

## 2. 当前结构

```text
.
├── apps/
│   └── sample_python/
├── datasets/
│   ├── normalized/
│   └── raw/
├── scenarios/
│   └── offline/
├── rag_eval/
│   ├── adapters/
│   ├── config/
│   ├── datasets/
│   ├── execution/
│   ├── metrics/
│   ├── reporting/
│   └── shared/
├── runs/
├── docs/
├── tests/
└── main.py
```

当前已实现的核心能力：

- `YAML` 场景加载与校验
- 离线 dataset 加载、标准化、无效样本分流
- `PDF -> online dataset draft` 的 dataset build 链路
- `ragas` 指标流水线装配
- 统一 `Evaluator` 执行流程
- 标准 `runs/<scenario>/` 本地资产输出

## 3. 简单离线 dataset 案例

仓库里已经放了一个最小离线样例：

- dataset: [datasets/normalized/sample_offline_rag_eval.csv](/C:/Users/A200477427/Learnings/ragas-template/datasets/normalized/sample_offline_rag_eval.csv)
- scenario: [scenarios/offline/sample-offline.yaml](/C:/Users/A200477427/Learnings/ragas-template/scenarios/offline/sample-offline.yaml)

另外还补了一套和 PDF dataset build 配对的离线 smoke 样例：

- dataset: [datasets/normalized/sample_pdf_offline_smoke.csv](/C:/Users/A200477427/Learnings/ragas-template/datasets/normalized/sample_pdf_offline_smoke.csv)
- scenario: [scenarios/offline/sample-pdf-offline-smoke.yaml](/C:/Users/A200477427/Learnings/ragas-template/scenarios/offline/sample-pdf-offline-smoke.yaml)

这个 dataset 是纯本地文件，不依赖任何在线数据源，包含 3 条标准离线样本，字段就是平台统一要求的：

- `question`
- `contexts`
- `answer`
- `ground_truth`
- 以及可选的 `sample_id / scenario / language / retrieval_config`

## 4. 运行方式

先准备环境变量：

```powershell
Copy-Item .env.example .env
```

`.env` 中至少需要设置：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`

如果你现在的 OpenAI 兼容模型都可用，这里直接填你已有的网关和 key 即可。默认模型现在是：

- `OPENAI_BASE_URL=http://6.86.80.4:30080/v1`
- `RAGAS_JUDGE_MODEL=deepseek-v4-flash`
- `RAGAS_EMBEDDING_MODEL=text-embedding-v3`

推荐直接走统一入口：

```powershell
uv run main.py --scenario scenarios/offline/sample-offline.yaml
or
.\.venv\Scripts\python.exe main.py --scenario scenarios/offline/sample-offline.yaml
```

如果你想直接验证 `sample-pdf-build.yaml` 对应的离线 smoke 评测，可以运行：

```powershell
uv run main.py --scenario scenarios/offline/sample-pdf-offline-smoke.yaml
or
.\.venv\Scripts\python.exe main.py --scenario scenarios/offline/sample-pdf-offline-smoke.yaml
```

运行完成后会输出到：

```text
runs/sample-offline-baseline/<run_id>/
├── scenario.snapshot.yaml
├── scores.csv
├── invalid.csv
├── summary.md
└── metadata.json
```

## 5. 在线接入预留

当前骨架已经预留了两类一等公民 adapter：

- `http`
- `python`

本地 Python adapter 示例在 [apps/sample_python/adapter.py](/C:/Users/A200477427/Learnings/ragas-template/apps/sample_python/adapter.py)。你后面要接自己的 RAG 应用时，只需要把真实逻辑适配成：

```python
def run(question: str, **kwargs) -> dict:
    return {
        "answer": "...",
        "contexts": ["...", "..."],
        "raw_response": {...},
    }
```

其中 [apps/sample_python/adapter.py](/C:/Users/A200477427/Learnings/ragas-template/apps/sample_python/adapter.py) 只是最小 contract 示例。
如果你要直接评测 `dataset_build` 产出的 PDF 题库，仓库里现在提供了专用实现：

- adapter: [apps/pdf_question_bank/adapter.py](/C:/Users/A200477427/Learnings/ragas-template/apps/pdf_question_bank/adapter.py)
- online scenario: [scenarios/online/sample-pdf-question-bank-online.yaml](/C:/Users/A200477427/Learnings/ragas-template/scenarios/online/sample-pdf-question-bank-online.yaml)

这个 adapter 会读取题库行中的 `source_chunk_ids`，再从 `source_chunks.jsonl` 里解析出证据块，把这些证据块直接作为 `contexts`，并调用本地 OpenAI 兼容模型生成 `answer`。

## 6. 结果资产

每次运行都会写出标准本地资产：

- `scenario.snapshot.yaml`：本次运行的实际配置快照
- `scores.csv`：逐样本评分结果
- `invalid.csv`：无效样本
- `summary.md`：汇总报告
- `metadata.json`：机器可读元数据

这意味着后续你比较不同模型、不同 prompt、不同检索策略时，不需要再靠手工记参数。

## 7. PDF 题库构建

仓库现在额外支持把 PDF 文档解析成可人工复核的在线题库草稿。最推荐的阅读顺序是：

- 快速入口看本节
- 端到端案例看 [docs/sample-pdf-question-bank-workflow.md](/C:/Users/A200477427/Learnings/ragas-template/docs/sample-pdf-question-bank-workflow.md)

样例配置在：

- [scenarios/dataset_build/sample-pdf-build.yaml](/C:/Users/A200477427/Learnings/ragas-template/scenarios/dataset_build/sample-pdf-build.yaml)

运行方式：

```powershell
uv run main.py --dataset-build-config scenarios/dataset_build/sample-pdf-build.yaml
or
.\.venv\Scripts\python.exe main.py --dataset-build-config scenarios/dataset_build/sample-pdf-build.yaml
```

这条链路会：

- 扫描单个 PDF 或 PDF 目录
- 调用阿里云解析能力并归一化成 `source chunks`
- 调用 LLM 生成在线评测题库草稿
- 输出带时间戳的 run 资产，以及稳定入口 `latest/source_chunks.jsonl`、`latest/dataset_draft.csv`、`latest/metadata.json`

生成后的草稿 dataset 默认只要求 `question` 和 `ground_truth`，后续进入 `online` 评测时再由 adapter 补齐 `answer` 和 `contexts`。

现在这条在线链路已经有一个真实样例：

```powershell
uv run main.py --scenario scenarios/online/sample-pdf-question-bank-online.yaml
or
.\.venv\Scripts\python.exe main.py --scenario scenarios/online/sample-pdf-question-bank-online.yaml
```

这个 scenario 会：

- 读取 [datasets/raw/generated/sample-pdf-question-bank.csv](/C:/Users/A200477427/Learnings/ragas-template/datasets/raw/generated/sample-pdf-question-bank.csv)
- 使用 `apps/pdf_question_bank/adapter.py`
- 显式绑定到 sample build 的稳定入口 `outputs/dataset-builds/sample-pdf-question-bank/latest/source_chunks.jsonl`
- 在线生成 `answer`
- 再用 `ground_truth` 对生成结果打分

如果你想按完整顺序跑一遍 sample，从环境变量、dataset build、online eval 到结果查看，直接看：

- [docs/sample-pdf-question-bank-workflow.md](/C:/Users/A200477427/Learnings/ragas-template/docs/sample-pdf-question-bank-workflow.md)

如果你只想先快速跑通离线评测，不想先重新生成题库，可以直接用上面的 [scenarios/offline/sample-pdf-offline-smoke.yaml](/C:/Users/A200477427/Learnings/ragas-template/scenarios/offline/sample-pdf-offline-smoke.yaml)。它是从 sample PDF build 产物固化出来的 smoke dataset，使用 `source chunks` 作为 `contexts`，并用 `ground_truth` 复用为 `answer`。
