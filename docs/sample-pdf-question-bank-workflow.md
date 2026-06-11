# `sample-pdf-question-bank` 端到端使用说明

这篇文档对应仓库里的真实案例：先把 PDF 解析成 question bank，再用 online evaluator 基于证据 chunk 生成答案并打分。

完整链路是：

```text
PDFs
-> dataset_build
-> sample-pdf-question-bank.csv + latest/source_chunks.jsonl
-> online adapter
-> answer + contexts
-> ragas metrics
```

## 1. 先准备环境

先复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

这条案例链路依赖两类能力：

- OpenAI 兼容模型
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
- 阿里云文档解析
  - `ALIBABA_ACCESS_KEY_ID`
  - `ALIBABA_ACCESS_KEY_SECRET`
  - `ALIBABA_ENDPOINT`

默认还会用到这些模型配置：

- `DATASET_GENERATOR_MODEL=qwen3.6-plus`
- `RAGAS_JUDGE_MODEL=deepseek-v4-flash`
- `RAGAS_EMBEDDING_MODEL=text-embedding-v3`

如果少了 `OPENAI_API_KEY`，dataset build 里的题库生成和 online eval 都无法运行。
如果少了阿里云凭据，PDF 解析阶段无法运行。

## 2. 跑 dataset build

使用 sample 配置：

- config: [scenarios/dataset_build/sample-pdf-build.yaml](/C:/Users/A200477427/Learnings/ragas-template/scenarios/dataset_build/sample-pdf-build.yaml)

执行命令：

```powershell
uv run main.py --dataset-build-config scenarios/dataset_build/sample-pdf-build.yaml
or
.\.venv\Scripts\python.exe main.py --dataset-build-config scenarios/dataset_build/sample-pdf-build.yaml
```

这一步会做四件事：

1. 扫描 `datasets/raw/pdfs` 下的 PDF
2. 调用阿里云解析生成结构化 `source chunks`
3. 调用 LLM 生成 question bank 草稿
4. 写出稳定 dataset 和详细 run 资产

## 3. 看 build 产物

跑完以后，你会看到两类输出。

第一类是稳定入口，给后续 online eval 和教程使用：

- question bank CSV:
  [datasets/raw/generated/sample-pdf-question-bank.csv](/C:/Users/A200477427/Learnings/ragas-template/datasets/raw/generated/sample-pdf-question-bank.csv)
- latest source chunks:
  [source_chunks.jsonl](/C:/Users/A200477427/Learnings/ragas-template/outputs/dataset-builds/sample-pdf-question-bank/latest/source_chunks.jsonl)
- latest dataset draft:
  [dataset_draft.csv](/C:/Users/A200477427/Learnings/ragas-template/outputs/dataset-builds/sample-pdf-question-bank/latest/dataset_draft.csv)
- latest metadata:
  [metadata.json](/C:/Users/A200477427/Learnings/ragas-template/outputs/dataset-builds/sample-pdf-question-bank/latest/metadata.json)

第二类是带时间戳的 run 级资产，用来审计和排查：

- 目录模式：
  `outputs/dataset-builds/sample-pdf-question-bank/<run_id>/`

其中常见文件有：

- `documents.jsonl`
- `semantic_blocks.jsonl`
- `source_chunks.jsonl`
- `dataset_draft.csv`
- `parse_failures.csv`
- `metadata.json`

理解这个区别很重要：

- 稳定入口用于“继续往下跑”
- 时间戳目录用于“回看某次具体构建”

## 4. question bank CSV 里是什么

sample build 输出的是 online-ready question bank，不是离线评测格式。

核心字段包括：

- `question`
- `ground_truth`
- `source_chunk_ids`
- `doc_id`
- `doc_name`

它故意不预写 `answer`。
原因是这条链路的目标是在线评测：由 adapter 在评测时，根据 `source_chunk_ids` 去 `source_chunks.jsonl` 里取证据，再调用模型生成 `answer`。

## 5. 跑 online eval

使用 sample online scenario：

- scenario: [scenarios/online/sample-pdf-question-bank-online.yaml](/C:/Users/A200477427/Learnings/ragas-template/scenarios/online/sample-pdf-question-bank-online.yaml)
- adapter: [apps/pdf_question_bank/adapter.py](/C:/Users/A200477427/Learnings/ragas-template/apps/pdf_question_bank/adapter.py)

执行命令：

```powershell
uv run main.py --scenario scenarios/online/sample-pdf-question-bank-online.yaml
or
.\.venv\Scripts\python.exe main.py --scenario scenarios/online/sample-pdf-question-bank-online.yaml
```

这个 scenario 的关键点有两个：

1. dataset 指向稳定 question bank CSV
2. `app_adapter.static_kwargs.source_chunks_path` 指向稳定的 `latest/source_chunks.jsonl`

因此，只要你重新跑过 sample dataset build，online scenario 就不需要再手改时间戳路径。

## 6. online adapter 在做什么

`apps/pdf_question_bank/adapter.py` 的处理方式是固定的：

1. 从题库行里读取 `source_chunk_ids`
2. 打开 `source_chunks.jsonl`
3. 只解析被引用的 chunk
4. 把这些 chunk 文本原样作为 `contexts`
5. 用这些证据 prompt 模型生成 `answer`
6. 把 `resolved_chunk_ids` 和模型响应写进 `raw_response`

所以评测关系是：

- `ground_truth` 是参考答案
- `answer` 是运行时生成答案
- `contexts` 是题目显式引用的证据块

这条链路没有单独做 retrieval。
它评测的是“给定明确证据后，应用/模型能否稳定生成正确答案”。

## 7. 结果在哪里看

online eval 完成后，结果会写到：

- `outputs/online/sample-pdf-question-bank/<run_id>/`

常见文件包括：

- `scores.csv`
- `invalid.csv`
- `summary.md`
- `metadata.json`

优先看这几个点：

- `scores.csv`：逐题指标分数
- `invalid.csv`：哪些样本因为 adapter 失败或空结果被剔除了
- `summary.md`：汇总视图

## 8. 常见问题

### `source_chunk_ids` 找不到

这通常表示 question bank CSV 和 `source_chunks.jsonl` 不是同一次 build 的产物。

正确做法：

1. 重新跑一次 `sample-pdf-build.yaml`
2. 确认 `outputs/dataset-builds/sample-pdf-question-bank/latest/source_chunks.jsonl` 已更新
3. 再运行 online scenario

### dataset build 成功，但 online eval 结果是 invalid

先看 `invalid.csv`。
当前实现里，以下情况会进入 invalid：

- adapter 生成 `answer` 为空
- adapter 返回 `contexts` 为空
- adapter 在解析 chunk 或调模型时抛异常

### 只想快速看离线 smoke，不想重建题库

直接运行：

- [scenarios/offline/sample-pdf-offline-smoke.yaml](/C:/Users/A200477427/Learnings/ragas-template/scenarios/offline/sample-pdf-offline-smoke.yaml)

这个案例是固化好的离线 smoke dataset，不依赖 online adapter。

## 9. 换成你自己的 PDF 时改哪里

如果你要复用这条模式处理自己的 PDF，最少只改这几个点：

1. 复制一份 dataset build YAML
2. 修改 `input.path` 指向你的 PDF 或 PDF 目录
3. 修改 `output.dataset_path` 为你的 question bank CSV
4. 修改 `output.artifact_dir` 为你的 build 资产根目录
5. 复制一份 online scenario
6. 修改 `dataset` 指向你的 question bank CSV
7. 修改 `app_adapter.static_kwargs.source_chunks_path` 指向你的 `artifact_dir/latest/source_chunks.jsonl`

不需要改 question bank CSV 的字段结构。
也不需要把 `answer` 预先写进 CSV。

如果你的 online answer 逻辑仍然是“根据显式证据块生成答案”，就可以继续复用：

- [apps/pdf_question_bank/adapter.py](/C:/Users/A200477427/Learnings/ragas-template/apps/pdf_question_bank/adapter.py)

如果你的应用是 HTTP 服务或有自己独立的 RAG 流程，再换成对应 adapter 即可。
