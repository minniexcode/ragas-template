# RAG 评测平台骨架

## 1. 项目定位

这个仓库现在已经从“单脚本离线评测”重构成一个可继续扩展的 **RAG 评测平台骨架**。核心目标不变：统一离线与在线评测入口，沉淀本地 run 资产，并且让多应用、多数据集、多场景对比变成标准流程。

架构边界来自 [docs/rag-eval-architecture.md](/C:/Users/A200477427/Learnings/ragas-template/docs/rag-eval-architecture.md)，当前代码已经按该文档落了第一版工程结构。

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
- `ragas` 指标流水线装配
- 统一 `Evaluator` 执行流程
- 标准 `runs/<scenario>/` 本地资产输出
- 兼容旧用法的 `rag_eval/offline_eval.py` 薄入口

## 3. 简单离线 dataset 案例

仓库里已经放了一个最小离线样例：

- dataset: [datasets/normalized/sample_offline_rag_eval.csv](/C:/Users/A200477427/Learnings/ragas-template/datasets/normalized/sample_offline_rag_eval.csv)
- scenario: [scenarios/offline/sample-offline.yaml](/C:/Users/A200477427/Learnings/ragas-template/scenarios/offline/sample-offline.yaml)

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

- `RAGAS_JUDGE_MODEL=gpt-4o-mini`
- `RAGAS_EMBEDDING_MODEL=text-embedding-3-large`

推荐直接走统一入口：

```powershell
.\.venv\Scripts\python.exe main.py --scenario scenarios/offline/sample-offline.yaml
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

如果你还想沿用旧命令，也可以：

```powershell
.\.venv\Scripts\python.exe rag_eval/offline_eval.py `
  --input datasets/normalized/sample_offline_rag_eval.csv `
  --output runs/offline-compat
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

## 6. 结果资产

每次运行都会写出标准本地资产：

- `scenario.snapshot.yaml`：本次运行的实际配置快照
- `scores.csv`：逐样本评分结果
- `invalid.csv`：无效样本
- `summary.md`：汇总报告
- `metadata.json`：机器可读元数据

这意味着后续你比较不同模型、不同 prompt、不同检索策略时，不需要再靠手工记参数。
