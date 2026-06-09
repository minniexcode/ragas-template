# RAG 评测平台架构设计

## 1. 背景与问题

当前仓库已经有一个可运行的离线评测原型，其能力已经收敛到统一的 `main.py --scenario ...` 入口与 `rag_eval/` 分层模块中。这个原型适合验证以下问题：

- 离线导出的 RAG 样本能否被标准化
- `ragas` 指标能否稳定跑通
- 基础评分结果能否写出为 CSV

但当评测对象从“一个数据文件、一次评测”演进为“多个 RAG 应用、多个数据集、多轮实验、多种配置对比”时，单脚本结构会迅速暴露问题：

- **职责耦合过高**：参数解析、数据加载、样本标准化、模型创建、指标执行、结果持久化全部混在一个脚本里
- **难以扩展在线模式**：当前实现默认输入已经包含 `answer` 与 `contexts`，不适合直接接入运行中的 RAG 应用
- **难以复现实验**：输出主要是单个 CSV，缺少运行快照、元数据和标准汇总
- **难以对比不同方案**：没有统一场景配置，不便系统化比较应用版本、模型和指标组合
- **难以承载多应用接入**：缺少稳定的应用适配层，无法把 HTTP 服务型应用和本地 Python 应用纳入统一流程

因此，本仓库需要从“离线评测脚本”演进为“RAG 评测平台骨架”。

## 2. 设计目标

目标架构需要满足以下设计目标：

- **平台化**：从一次性脚本升级为长期可演进的工程结构
- **可扩展**：新增应用接入方式、数据集格式和指标时，不需要重写主流程
- **可复现**：每次运行都能保留完整配置快照和结果资产
- **可对比**：不同应用、模型、检索策略和提示词方案可以稳定横向比较
- **统一双模式**：离线评测与在线评测共享同一条核心数据流
- **多对象接入**：支持多应用、多数据集、多模型和多场景组合
- **本地优先**：第一阶段以本地文件资产为中心，不引入数据库依赖

## 3. 非目标

本轮架构设计明确不覆盖以下方向：

- 不建设数据库中心化评测平台
- 不建设前端控制台或 Web UI
- 不建设远程任务调度与分布式执行系统
- 不引入服务端依赖作为评测执行前提
- 不在本轮实现完整目录骨架和模块代码，只固定设计边界

换句话说，当前阶段的目标是 **先把本地文件驱动的平台骨架设计定案**，而不是一步做成完整产品。

## 4. 目标架构总览

目标平台按照职责分为六层：

### 4.1 配置层

负责读取、校验和标准化 YAML 场景配置，产出统一的 `Scenario` 对象。

职责包括：

- 解析场景配置文件
- 应用默认值
- 校验模式、模型、指标和运行参数
- 生成运行快照

### 4.2 应用接入层

负责连接外部 RAG 应用或本地 Python RAG 函数，把调用结果统一转换为标准输出结构。

职责包括：

- 定义统一请求输入
- 屏蔽不同应用协议差异
- 返回可映射为 `answer` 和 `contexts` 的标准响应

### 4.3 数据集层

负责加载原始样本、标准化样本和在线问题集，并统一转换为平台的标准评测样本结构。

职责包括：

- 读取 CSV、Excel、JSONL 等数据源
- 规范化字段
- 校验必填字段
- 输出可进入评测核心层的标准样本集合

### 4.4 指标层

负责按场景配置装配评测指标，形成可执行的指标流水线。

职责包括：

- 构建 judge model 与 embedding model
- 根据场景启用指定指标
- 屏蔽底层评测库差异

### 4.5 执行层

负责把配置、数据、应用和指标串成一次完整运行。

职责包括：

- 数据准备
- 在线应用调用或离线结果加载
- 样本标准化
- 并发执行评分
- 错误捕获与降级
- 结果合并

### 4.6 结果层

负责把一次运行的所有结果沉淀为本地文件资产。

职责包括：

- 写出评分明细
- 写出无效样本
- 写出场景快照
- 写出汇总报告
- 写出元数据

## 5. 领域模型

为了让后续实现边界清晰，平台核心对象固定为以下六类。

### 5.1 `AppAdapter`

表示一个可被评测框架调用的 RAG 应用适配器。

职责：

- 接收标准问题输入
- 调用实际 RAG 应用
- 返回标准化响应结果

最小抽象能力：

- 输入：`question` 与可选上下文参数
- 输出：必须能映射为 `answer` 和 `contexts`

### 5.2 `Dataset`

表示一次评测所使用的数据集定义。

职责：

- 描述数据来源
- 加载原始样本
- 输出标准评测样本

需要同时兼容：

- 离线导入样本
- 在线问题样本
- 后续可能的多文件数据集或分片数据集

### 5.3 `Scenario`

表示一次完整实验的配置定义，是平台的统一实验入口。

职责：

- 声明评测模式
- 绑定应用、数据集、模型和指标
- 定义输出目录与运行参数

`Scenario` 必须由 YAML 场景配置生成，而不是在代码里零散拼装。

### 5.4 `Evaluator`

表示一次评测执行器。

职责：

- 根据场景驱动一次完整运行
- 调用数据集、应用适配器和指标流水线
- 产出运行结果与错误信息

### 5.5 `MetricPipeline`

表示一组按场景组合好的指标执行单元。

职责：

- 初始化 judge model 与 embedding model
- 按统一接口执行多个指标
- 输出结构化评分结果

### 5.6 `RunArtifact`

表示一次运行沉淀的结果资产集合。

职责：

- 固定结果文件布局
- 保存配置快照、评分结果、异常样本、汇总报告和元数据
- 作为后续复现、审计和对比的最小单元

## 6. 应用接入层设计

应用接入层把“如何调用 RAG 应用”从“如何做评测”中解耦。后续只保留两类一等公民适配器：`HTTP Adapter` 和 `Python Function Adapter`。

### 6.1 HTTP Adapter

适用于外部部署的 RAG 服务。

输入约束：

- 标准问题 `question`
- 可选上下文参数，例如租户、知识库、会话配置、检索参数

输出约束：

- 必须能够映射出 `answer`
- 必须能够映射出 `contexts`

推荐统一响应语义：

```json
{
  "answer": "string",
  "contexts": ["context 1", "context 2"],
  "raw_response": {}
}
```

说明：

- 真实 HTTP 响应可以与此不同
- 但 Adapter 层必须把实际响应转换成上述平台内部语义
- `raw_response` 可选保留，用于调试和审计，但不作为核心评测字段依赖

### 6.2 Python Function Adapter

适用于本地 Python 形式的 RAG 应用，例如本地函数、SDK 包装器或 Notebook 中已封装的检索问答逻辑。

输入输出约束与 HTTP Adapter 保持同构：

- 输入：`question` 与可选上下文参数
- 输出：必须能映射为 `answer` 和 `contexts`

推荐函数语义：

```python
def run(question: str, **kwargs) -> dict:
    return {
        "answer": "...",
        "contexts": ["...", "..."],
        "raw_response": {...},
    }
```

设计原则：

- 上层评测执行器不应该关心底层是 HTTP 调用还是 Python 函数调用
- 只要符合统一输入输出契约，就可以接入同一条评测管线

## 7. 数据集层设计

数据集层的目标是把不同来源的样本统一为同一标准格式。

### 7.1 原始样本

原始样本是未经平台标准化的输入，可能来自：

- 业务系统导出的 CSV 或 Excel
- 在线评测时的问题集
- 后续数据清洗脚本生成的中间文件

原始样本允许存在额外字段，但不应该直接进入评测核心层。

### 7.2 标准化评测样本

无论数据来源如何，进入评测核心层前都必须变成同一标准样本结构。最小核心字段固定为：

- `question`
- `contexts`
- `answer`
- `ground_truth`

可选元数据字段可包括：

- `sample_id`
- `scenario`
- `language`
- `retrieval_config`

约束如下：

- `question`：字符串
- `contexts`：有序文本列表
- `answer`：字符串
- `ground_truth`：字符串

### 7.3 在线生成样本与离线导入样本的统一格式

双模式统一约束如下：

- **离线模式**：输入文件本身已包含 `question / contexts / answer / ground_truth`
- **在线模式**：问题集先提供 `question` 与必要元信息，应用调用后补齐 `answer / contexts`，再与参考答案或标注结果结合形成标准样本

统一要求：

- 不允许在线模式绕过标准样本结构直接进入指标执行层
- 不允许离线模式在结果写出前使用独立的资产格式

这保证了后续的指标层、执行层和结果层可以完全共享。

## 8. 场景配置设计

YAML 是未来统一实验入口。README 只给最小示例，详细字段定义在本节固定。

### 8.1 最小骨架字段

```yaml
scenario_name: legal-assistant-offline-baseline
mode: offline
app_adapter: null
dataset: datasets/normalized/legal_assistant_baseline.csv
judge_model: deepseek-v4-flash
embedding_model: text-embedding-v3
metrics:
  - faithfulness
  - answer_relevancy
  - context_recall
  - context_precision
output_dir: runs/legal-assistant-offline-baseline
runtime:
  batch_size: 4
```

### 8.2 字段说明

- `scenario_name`
  - 场景名称，用于标识一次实验
- `mode: offline | online`
  - 评测模式
- `app_adapter`
  - 应用适配器定义；离线模式可为 `null`，在线模式必须提供
- `dataset`
  - 数据集路径或数据集定义引用
- `judge_model`
  - 负责评分类指标推理的模型
- `embedding_model`
  - 负责向量相关指标的模型
- `metrics`
  - 本次启用的指标列表
- `output_dir`
  - 本次运行结果输出目录
- `runtime.batch_size`
  - 并发批次大小

### 8.3 在线模式的 `app_adapter` 形态

后续建议支持如下两种声明方式：

```yaml
app_adapter:
  type: http
  endpoint: https://example-rag/api/ask
  method: POST
  timeout_seconds: 30
```

```yaml
app_adapter:
  type: python
  callable: apps.legal_assistant.adapter:run
```

说明：

- 这是配置接口约束，不代表当前仓库已经具备解析实现
- 字段可以后续扩充，但类型边界本轮即固定为 `http` 与 `python`

## 9. 评测执行层设计

评测执行层负责把一次实验变成稳定、可审计的运行流程。执行顺序固定如下。

### 9.1 数据准备

根据 `Scenario` 加载数据集定义，并读取原始样本。

### 9.2 应用调用或离线加载

- `offline` 模式：直接读取包含评测核心字段的离线样本
- `online` 模式：读取问题集，调用 `AppAdapter` 获取 `answer` 与 `contexts`

### 9.3 样本标准化

所有样本统一映射为标准结构：

- `question`
- `contexts`
- `answer`
- `ground_truth`

不合法样本在此阶段被分流为无效样本，而不是在指标执行阶段失败后再回溯处理。

### 9.4 指标编排

根据 `Scenario.metrics` 创建 `MetricPipeline`，并装配：

- judge model
- embedding model
- 指标实例

### 9.5 并发控制

执行层负责并发上限，不把并发策略散落到各指标实现中。

最低要求：

- 允许通过 `runtime.batch_size` 控制最大并发
- 在线调用和指标评分后续可以拥有独立并发策略
- 并发策略由执行层统一调度

### 9.6 错误捕获

错误需要按层次捕获：

- 数据加载错误
- 应用调用错误
- 指标执行错误
- 结果写出错误

原则：

- 单条样本失败不应默认导致整批运行失败
- 失败信息要体现在结果资产中
- 不应只把错误打印到控制台后丢失

### 9.7 结果合并

最终输出应包含：

- 原始样本字段
- 标准化样本字段
- 指标分数
- 错误字段
- 运行元信息

## 10. 结果资产设计

平台统一采用“run 目录”模式，不引入数据库前置依赖。每次运行输出固定如下：

```text
runs/<run_id>/
├── scenario.snapshot.yaml
├── scores.csv
├── invalid.csv
├── summary.md
└── metadata.json
```

各文件职责固定如下。

### 10.1 `runs/<run_id>/scenario.snapshot.yaml`

保存本次评测实际使用的场景快照，确保即使原始场景文件后续变化，也能复现本次运行。

### 10.2 `runs/<run_id>/scores.csv`

保存逐样本评测结果，至少包括：

- 标准样本字段
- 指标分数
- 错误信息
- 模型与运行时间等元信息字段

### 10.3 `runs/<run_id>/invalid.csv`

保存标准化失败、关键字段缺失或格式不合法的样本，用于追踪数据质量问题。

### 10.4 `runs/<run_id>/summary.md`

保存面向人阅读的汇总结论，例如：

- 总样本数、有效样本数、无效样本数
- 各指标均值
- 分组统计
- 低分样本观察

### 10.5 `runs/<run_id>/metadata.json`

保存机器可读元数据，例如：

- `run_id`
- `scenario_name`
- `mode`
- `judge_model`
- `embedding_model`
- `started_at`
- `finished_at`
- 代码版本或 Git commit（后续可选）

统一约束：

- 无论数据来自在线还是离线模式，结果都统一写入本地文件资产
- 在引入数据库前，不允许出现只写数据库不落本地文件的实现分支

## 11. 推荐代码目录结构

后续推荐代码骨架如下。该结构作为实现边界约束，供后续重构与新增模块直接遵循。

```text
.
├── apps/
│   ├── <app_name>/
│   │   ├── adapter.py
│   │   └── README.md
├── datasets/
│   ├── raw/
│   ├── normalized/
│   └── samples/
├── scenarios/
│   ├── offline/
│   └── online/
├── rag_eval/
│   ├── config/
│   │   ├── loader.py
│   │   ├── schema.py
│   │   └── validators.py
│   ├── adapters/
│   │   ├── base.py
│   │   ├── http.py
│   │   └── python.py
│   ├── datasets/
│   │   ├── loader.py
│   │   ├── normalizers.py
│   │   └── validators.py
│   ├── metrics/
│   │   ├── factory.py
│   │   ├── pipeline.py
│   │   └── registry.py
│   ├── execution/
│   │   ├── evaluator.py
│   │   ├── runner.py
│   │   ├── concurrency.py
│   │   └── errors.py
│   ├── reporting/
│   │   ├── artifacts.py
│   │   ├── summary.py
│   │   └── writers.py
│   ├── shared/
│   │   ├── types.py
│   │   ├── models.py
│   │   └── utils.py
│   ├── compat.py
│   └── settings.py
├── runs/
├── docs/
├── tests/
├── main.py
└── README.md
```

模块分层约束固定如下：

- `rag_eval/config/`：配置加载与校验
- `rag_eval/adapters/`：HTTP / Python 应用接入
- `rag_eval/datasets/`：加载、标准化、校验
- `rag_eval/metrics/`：指标装配与扩展
- `rag_eval/execution/`：运行编排、并发、错误处理
- `rag_eval/reporting/`：结果写出、汇总、报告
- `rag_eval/shared/`：通用类型与工具

后续实现不应再把这些职责重新合并回单个入口脚本。

## 12. 演进路线

当前仓库已经完成从单脚本离线评测到统一 CLI 的第一轮收敛，后续重点不再是移除旧入口，而是继续完善场景、接入、结果治理与测试能力。

推荐拆分路径如下：

### 12.1 第一阶段：抽离离线模式公共能力（已完成）

当前已完成以下能力下沉：

- 输入文件加载
- 样本标准化
- 指标装配
- 结果写出

结果是离线模式已经摆脱“单文件全包”的结构，进入统一模块分层。

### 12.2 第二阶段：引入 `Scenario` 与 YAML 配置（已完成）

当前主入口已经改为读取 YAML 场景配置。

### 12.3 第三阶段：引入应用适配器（已完成第一版）

当前已具备在线模式的一等公民适配器：

- HTTP Adapter
- Python Function Adapter

在线和离线模式已经共享同一条标准化与评分流程。

### 12.4 第四阶段：统一 CLI 入口（已完成）

当前统一 CLI 入口如下：

```powershell
python main.py --scenario scenarios/offline/sample.yaml
```

旧的兼容入口已经移除，仓库统一以 scenario 驱动的入口为准。

### 12.5 第五阶段：完善结果治理与测试

补齐：

- `runs/` 目录规范落地
- 汇总报告生成
- 在线/离线统一回归测试
- 多应用与多场景对比样例

## 结论

本设计文档的核心决策已经固定：

- 统一采用 YAML 作为实验入口
- 统一支持在线与离线双模式
- 统一以标准样本结构进入评测核心层
- 统一把结果写入本地 `run` 目录资产
- 统一按照配置层、接入层、数据层、指标层、执行层、结果层拆分代码

后续工程实现应直接遵循这些边界推进，而不再重新讨论整体骨架。
