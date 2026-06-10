# PDF 文档转在线评测题库需求设计

## 1. 背景与问题

当前仓库已经具备一条完整的评测主链路：

- `main.py --scenario ...`
- 加载 dataset
- 标准化样本
- 调用 adapter
- 使用 `ragas` 评分
- 写出本地运行资产

但这条链路默认前提是“评测数据已经存在”。现实里，RAG 项目的评测样本往往首先来自大量原始文档，例如 PDF 规范、制度、手册、法规或技术说明。没有一条稳定的“文档 -> 题库 dataset”生成链路，平台就仍然停留在手工准备数据的阶段。

你给出的外部示例项目已经验证了两件关键能力：

- 可以用阿里云文档解析服务对 PDF 做异步解析
- 可以把解析结果归一成结构节点、语义块和可追溯切片

因此，本轮需求设计的目标不是建设一个完整知识库系统，而是在当前评测平台里补上一条最小可用的数据生产链路，让原始 PDF 可以生成可复核的在线评测题库。

## 2. 目标

本需求设计的 V1 目标如下：

- 支持从单个 PDF 或一个 PDF 目录批量生成在线评测题库
- 解析能力基于阿里云文档解析服务
- 题目生成以单文档为边界，不跨文档混合
- 输出结果是可直接接入当前 `online` 评测模式的 dataset 草稿
- 输出结果保留页码、章节、来源 chunk 等证据链，便于人工复核
- 复用当前仓库的本地文件优先原则，不引入数据库依赖

## 3. 非目标

V1 明确不覆盖以下范围：

- 不建设向量库入库能力
- 不建设文档上传 Web UI
- 不建设多租户文档中心
- 不支持跨文档综合题
- 不支持 Office 文档、图片包、网页抓取等多格式输入
- 不自动生成最终 gold dataset
- 不在 V1 中产出离线评测必需的 `answer / contexts`
- 不复用外部项目中与向量化落库、知识库写入直接耦合的域模型

换句话说，V1 的目标是 **先把 PDF 文档转成“可人工复核的在线评测题库草稿”**，而不是一步演进成完整 RAG 数据工厂。

## 4. 用户价值

引入这条链路后，平台可以覆盖以下工作方式：

1. 用户准备一批 PDF 文档
2. 系统调用阿里云文档解析服务获取结构化版面结果
3. 系统把版面结果归一成可追溯的 chunk
4. 系统用 LLM 基于 chunk 生成问题与参考答案草稿
5. 用户在导出的 dataset 上做人工复核
6. 用户把复核后的 dataset 直接接入现有 `online` 评测场景

这样平台就同时具备：

- 数据生产能力
- 数据复核能力
- 在线评测接入能力
- 结果资产沉淀能力

## 5. V1 核心决策

本轮设计固定以下产品决策：

- 输入文档范围：仅 `PDF`
- 题目生成范围：仅 `单文档题`
- dataset 目标类型：`在线题库`
- 发布方式：`先生成草稿，再人工复核`
- 解析服务：阿里云文档解析
- 解析失败默认策略：`fail`

这些决策不再留给后续实现阶段临时判断。

## 6. 目标架构总览

在现有评测架构之外，新增一条“dataset build”链路：

```text
PDF files
  -> dataset build config
  -> aliyun parser gateway
  -> layout normalization
  -> source chunks
  -> LLM question generation
  -> draft online dataset
  -> review
  -> existing online evaluation flow
```

该链路与现有评测链路的关系如下：

- `dataset build` 负责“评测输入怎么生产”
- 现有 `rag_eval/execution/` 负责“生产好的评测输入怎么跑分”

二者职责分离，不相互污染。

## 7. 模块边界设计

### 7.1 CLI 入口

保留现有评测入口不变：

```powershell
python main.py --scenario scenarios/offline/sample-offline.yaml
```

新增一个用于构建 dataset 的入口：

```powershell
python main.py --dataset-build-config scenarios/dataset_build/sample-pdf-build.yaml
```

两个入口互斥，避免一次命令同时承担“建题库”和“跑评测”两个职责。

### 7.2 新增模块目录

新增主包：

```text
rag_eval/
  dataset_builder/
    __init__.py
    models.py
    schema.py
    runner.py
    writers.py
    sources.py
    parser/
      __init__.py
      aliyun_docmind_gateway.py
      aliyun_document_parser.py
      aliyun_layout_normalizer.py
    generator/
      __init__.py
      question_generator.py
      validators.py
```

职责划分如下：

- `schema.py`：校验 dataset build YAML
- `models.py`：定义 job、解析结果、source chunk、生成样本等内部模型
- `runner.py`：串联一次完整 build job
- `writers.py`：写出 dataset 和本地资产
- `sources.py`：发现输入 PDF 文件
- `parser/`：适配阿里云文档解析能力
- `generator/`：调用 LLM 生成题目草稿并做输出校验

### 7.3 外部示例代码复用策略

允许从外部项目参考并迁移以下能力：

- `aliyun_docmind_gateway.py`
- `aliyun_document_parser.py`
- `aliyun_layout_normalizer.py`

但复用范围只限于：

- 异步解析任务提交与轮询
- layout 拉取
- 结构节点提取
- 语义块合并
- 可追溯切片构建

不迁移以下职责：

- 向量库入库
- embedding 持久化
- 外部知识库 chunk 域模型
- 知识库索引流程

## 8. 配置设计

### 8.1 新增 YAML 类型

新增一类配置文件，例如：

```text
scenarios/
  dataset_build/
    sample-pdf-build.yaml
```

### 8.2 配置字段

V1 的 dataset build YAML 结构固定如下：

```yaml
job_name: legal-pdf-question-bank
input:
  path: ../../datasets/raw/pdfs
  glob: "*.pdf"
parser:
  provider: aliyun_docmind
  failure_mode: fail
generation:
  model: qwen-long
  output_type: online_question_bank
  review_mode: draft_with_manual_review
  max_questions_per_document: 10
  max_source_chunks_per_question: 3
output:
  dataset_path: ../../datasets/raw/generated/legal_question_bank.csv
  artifact_dir: ../../outputs/dataset-builds/legal-pdf-question-bank
runtime:
  max_documents: 20
```

### 8.3 字段约束

- `job_name`：必填，作为本次构建任务名称
- `input.path`：必填，支持单文件或目录
- `input.glob`：可选，默认 `*.pdf`
- `parser.provider`：V1 固定为 `aliyun_docmind`
- `parser.failure_mode`：`fail | skip`，默认 `fail`
- `generation.model`：可选，允许覆盖默认生成模型
- `generation.output_type`：V1 固定为 `online_question_bank`
- `generation.review_mode`：V1 固定为 `draft_with_manual_review`
- `generation.max_questions_per_document`：正整数，默认 `10`
- `generation.max_source_chunks_per_question`：正整数，默认 `3`
- `output.dataset_path`：必填，最终 dataset 输出路径
- `output.artifact_dir`：必填，运行资产根目录
- `runtime.max_documents`：可选，用于限制一次处理文档数

## 9. 环境变量设计

### 9.1 阿里云解析配置

在 `rag_eval/settings.py` 中新增以下环境变量读取：

- `ALIBABA_ACCESS_KEY_ID`
- `ALIBABA_ACCESS_KEY_SECRET`
- `ALIBABA_ENDPOINT`
- `ALIYUN_PARSE_POLL_INTERVAL_SECONDS`
- `ALIYUN_PARSE_TIMEOUT_SECONDS`
- `ALIYUN_PARSE_LAYOUT_STEP_SIZE`
- `ALIYUN_LLM_ENHANCEMENT`
- `ALIYUN_ENHANCEMENT_MODE`
- `DOCUMENT_PARSE_ARTIFACT_PREFIX`
- `PARSER_FAILURE_MODE`

### 9.2 题库生成模型配置

新增环境变量：

- `DATASET_GENERATOR_MODEL`

默认优先级如下：

1. dataset build YAML 中的 `generation.model`
2. `.env` 中的 `DATASET_GENERATOR_MODEL`
3. 代码默认值

### 9.3 密钥管理要求

设计文档只引用环境变量名，不在仓库文档中记录任何明文 AK/SK。当前已经暴露在会话里的密钥需要单独轮换，这属于实现前置的安全动作。

## 10. 核心数据模型设计

### 10.1 `DatasetBuildJob`

表示一次 PDF -> dataset 生成任务。

核心字段：

- `job_name`
- `input_path`
- `input_glob`
- `parser_provider`
- `failure_mode`
- `generation_model`
- `output_type`
- `review_mode`
- `dataset_path`
- `artifact_dir`
- `runtime`

### 10.2 `ParsedDocument`

表示一个 PDF 经解析和归一化后的文档。

核心字段：

- `doc_id`
- `doc_name`
- `raw_text`
- `structure_nodes`
- `semantic_blocks`
- `source_chunks`
- `metadata`

### 10.3 `SourceChunk`

`SourceChunk` 是 V1 最关键的证据单元，用于生成题目和支持人工复核。

字段固定为：

- `chunk_id`
- `doc_id`
- `doc_name`
- `text`
- `page_start`
- `page_end`
- `section_path`
- `section_title`
- `source_layout_ids`

设计原则：

- 每个 chunk 必须能反查来源页码
- 每个 chunk 必须能反查章节路径
- 每个 chunk 必须能反查原始 layout id
- 每个 chunk 只服务题库生成和证据追溯，不承担向量化职责

### 10.4 `DraftQuestionSample`

表示一条待复核的在线评测样本草稿。

字段固定为：

- `sample_id`
- `question`
- `ground_truth`
- `scenario`
- `language`
- `doc_id`
- `doc_name`
- `section_path`
- `page_start`
- `page_end`
- `source_chunk_ids`
- `question_type`
- `difficulty`
- `review_status`
- `review_notes`

### 10.5 枚举约束

- `review_status`: `draft | approved | rejected | needs_edit`
- `question_type`: `fact | summary | procedure | comparison`
- `difficulty`: `easy | medium | hard`

## 11. 文档解析设计

### 11.1 解析输入范围

V1 仅接受：

- 单个 `.pdf` 文件
- 或一个包含多个 `.pdf` 的目录

目录模式下默认按 `input.glob` 扫描，默认值为 `*.pdf`。

### 11.2 解析流程

每个 PDF 的处理过程固定为：

1. 发现文件
2. 创建阿里云 Docmind client
3. 提交异步解析任务
4. 轮询直到成功、失败或超时
5. 分页拉取全量 layout
6. 归一成结构节点、语义块和 source chunk
7. 写出中间资产

### 11.3 版面归一化规则

从外部示例代码中沿用以下核心规则：

- 识别标题层级
- 跳过目录页内容
- 合并连续段落文本
- 抽取表格为可检索纯文本
- 保留图注类文本
- 按固定窗口做长文本切块
- 为每个 chunk 注入章节头信息和页码追溯信息

### 11.4 错误处理

支持两种失败模式：

- `fail`：任一文档解析失败则整个 job 失败
- `skip`：记录失败文档，继续处理其余文档

V1 默认策略为 `fail`。

## 12. 题库生成设计

### 12.1 生成单元

题目生成单元固定为“单文档内的一组 section-aware source chunks”。

约束如下：

- 一条题目只能引用同一个 `doc_id`
- 一条题目最多引用 `3` 个 chunk
- 不允许跨文档混合证据

### 12.2 生成输出

每个候选题必须产出：

- `question`
- `ground_truth`
- `source_chunk_ids`
- `question_type`
- `difficulty`

### 12.3 数量控制

V1 默认：

- 每个文档最多生成 `10` 条题
- 每组 chunk 最多生成 `1` 条题

实现时必须做覆盖率与多样性平衡，避免所有问题只集中在文档开头章节。

### 12.4 复核模式

V1 不自动发布最终 dataset，只输出草稿。

草稿规则：

- `review_status` 初始一律写为 `draft`
- `review_notes` 初始为空
- 人工可在 CSV 中修订问题、答案与审核状态

### 12.5 自动校验

候选题进入最终 dataset 前必须通过以下校验：

- `question` 非空
- `ground_truth` 非空
- `source_chunk_ids` 非空
- 引用的 chunk 必须真实存在
- 所有引用 chunk 必须来自同一文档
- `question_type` 和 `difficulty` 必须落在允许枚举内

自动校验失败的候选题不进入最终 draft CSV。

### 12.6 去重规则

同一文档内执行如下去重：

- 问题文本归一化后完全相同则去重
- 引用 chunk 完全相同且参考答案语义近似的候选题只保留一条

V1 去重目标是控制明显重复，不追求复杂聚类算法。

## 13. 输出资产设计

### 13.1 Dataset 输出

最终 dataset 默认输出到：

```text
datasets/raw/generated/<job_name>.csv
```

允许由 YAML 的 `output.dataset_path` 覆盖。

### 13.2 运行资产目录

每次构建任务的运行资产输出到：

```text
outputs/dataset-builds/<job_name>/<run_id>/
```

### 13.3 必须输出的资产

每次运行至少写出以下文件：

- `documents.jsonl`
- `semantic_blocks.jsonl`
- `source_chunks.jsonl`
- `dataset_draft.csv`
- `parse_failures.csv`
- `metadata.json`

含义如下：

- `documents.jsonl`：逐文档解析摘要
- `semantic_blocks.jsonl`：逐语义块中间结果
- `source_chunks.jsonl`：逐切片证据结果
- `dataset_draft.csv`：生成后的题库草稿
- `parse_failures.csv`：失败文档清单
- `metadata.json`：运行元数据、配置快照、统计结果

## 14. 与现有评测链路的兼容性修正

### 14.1 当前问题

当前仓库的文档设计已经说明 `online` 模式往往只需要：

- `question`
- `ground_truth`

然后由 adapter 在评测时补齐：

- `answer`
- `contexts`

但当前 `rag_eval/datasets/normalizers.py` 仍然把 `contexts / answer / ground_truth` 统一视作必填。这与文档目标架构不一致，也会直接阻塞本需求设计生成的在线题库接入。

### 14.2 修正原则

后续实现必须把 dataset 校验改成按 mode 分流：

- `offline` 模式必须具备 `question / contexts / answer / ground_truth`
- `online` 模式必须具备 `question / ground_truth`
- `online` 模式允许 `contexts / answer` 在初始数据集中为空

### 14.3 设计影响

这个修正不是附属优化，而是本需求能够成立的前置条件。否则生成出来的在线题库无法进入当前评测主流程。

## 15. 流程设计

一次完整的 dataset build job 执行流程如下：

1. 读取 `--dataset-build-config`
2. 校验 YAML 并生成 `DatasetBuildJob`
3. 扫描输入 PDF
4. 按顺序或受控并发处理每个文档
5. 调用阿里云文档解析
6. 归一化 layout，生成 `ParsedDocument`
7. 萃取 `SourceChunk`
8. 基于 `SourceChunk` 调用 LLM 生成题库草稿
9. 对候选题做结构校验与去重
10. 写出 `dataset_draft.csv`
11. 写出中间 artifacts 和失败清单
12. 人工复核后，将复核版本作为 `online` 评测输入

## 16. 测试设计

### 16.1 配置测试

需要覆盖：

- `--scenario` 与 `--dataset-build-config` 互斥
- 缺失必填字段
- 非法枚举值
- 输入路径不存在
- 输入目录中没有 PDF

### 16.2 解析测试

使用 mocked 阿里云响应覆盖：

- 提交成功
- 状态轮询成功
- 状态轮询超时
- 任务失败
- 返回空 layouts

同时要覆盖版面归一化规则：

- 目录页跳过
- 标题层级继承
- 表格扁平化
- 图注抽取
- 长文本切块

### 16.3 题库生成测试

使用 mocked LLM 输出覆盖：

- 正常结构化生成
- 空题目
- 缺失 ground truth
- 引用不存在 chunk
- 跨文档引用
- 重复问题去重

### 16.4 端到端测试

需要至少有一组 mocked parser + mocked generator 的端到端流程测试，验证：

- 单 PDF 输入
- 多 PDF 输入
- `fail` 模式
- `skip` 模式
- 所有 artifact 均成功写出

### 16.5 评测回归测试

需要新增测试确保：

- 只包含 `question / ground_truth / metadata` 的在线题库能被加载
- adapter 补齐 `answer / contexts` 后，现有 evaluator 能继续跑完指标

## 17. 实施顺序建议

为了降低风险，后续实现建议按以下顺序推进：

1. 先扩展 `main.py` 和配置层，增加 dataset build 命令入口
2. 再扩展 `settings.py` 与依赖，接入阿里云解析配置
3. 迁移 parser gateway 与 layout normalizer
4. 落地 `dataset_builder` 的 models、runner、writers
5. 实现 LLM 题库生成与输出校验
6. 修正现有 online dataset 校验逻辑
7. 补测试、样例 YAML 和文档

## 18. 最终结论

本需求设计固定了一个清晰、可落地的 V1 范围：

- 用阿里云解析 PDF
- 把解析结果转成可追溯 source chunks
- 用 LLM 基于单文档内容生成在线评测题库草稿
- 用人工复核保证最终质量
- 复核后的题库直接接入现有 online 评测流程

这个设计刻意收窄了输入格式、题型边界和自动化深度，目的不是保守，而是先确保整条链路能够在当前仓库架构中闭环，并且不给后续实现留下需要临场决策的空白。
