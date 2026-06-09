# RAG 评测引擎链路说明

## 1. 这份文档解决什么问题

`docs/rag-eval-architecture.md` 主要回答“为什么这样分层、模块边界是什么”。  
这份文档回答的是另一件事：**一次评测在代码里到底是怎么跑起来的**。

如果你现在对下面这些问题还有点混淆，这份文档就是给你的：

- `rag_eval/` 到底是评测什么的
- `apps/` 在整个架构里扮演什么角色
- `offline` 和 `online` 模式的区别是什么
- dataset、adapter、metrics、reporting 是怎么串起来的

---

## 2. 一句话理解整个引擎

这套系统本质上是一条标准化评测流水线：

```text
scenario -> dataset -> normalize -> app adapter -> metrics -> reporting -> run artifacts
```

也可以拆成更容易理解的话：

1. 先读取一份评测场景配置
2. 再读取待评测数据
3. 把原始数据标准化成统一样本结构
4. 如果需要，调用你的 RAG 应用补齐 `answer` 和 `contexts`
5. 用 `ragas` 指标计算分数
6. 把结果写到本地 run 目录

---

## 3. 目录职责

### `rag_eval/`

这是**评测引擎本体**。它负责：

- 加载 scenario
- 加载 dataset
- 调用 app adapter
- 执行指标评分
- 写出结果资产

### `apps/`

这是**被评测应用的接入层**，不是评测框架本身。

这里放的是“你的 RAG 应用如何被框架调用”的示例或适配代码。例如：

```text
apps/
└── sample_python/
    ├── adapter.py
    └── README.md
```

`apps/sample_python/` 的意义不是提供评测逻辑，而是演示：

- 如果你的应用是本地 Python 函数
- 它应该暴露什么接口
- 返回值要长什么样

### `scenarios/`

这是评测配置层，用 YAML 声明：

- 评测模式
- 数据集路径
- judge / embedding 模型
- 要跑哪些 metrics
- 输出目录
- 是否要调用 `http` 或 `python` adapter

### `datasets/`

这里存放评测输入数据。通常分为：

- `raw/`：原始输入
- `normalized/`：整理后的标准评测样本

### `outputs/` 或 `runs/`

这里存放每次评测生成的结果资产，比如：

- `scores.csv`
- `invalid.csv`
- `summary.md`
- `metadata.json`

---

## 4. 主入口链路

统一主链路最终都会走到：

- [rag_eval/execution/runner.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/execution/runner.py:1)

核心入口函数是 `run_scenario()`，它负责把所有子模块串起来。

简化后的执行顺序是：

```text
run_scenario()
  -> load_scenario()
  -> build_adapter()
  -> build_metric_pipeline()
  -> Evaluator.evaluate()
  -> write_run_artifacts()
```

你可以把它理解成整套系统的 orchestration 层。

---

## 5. Scenario 链路

scenario 是一次评测任务的“总配置”。

相关代码：

- [rag_eval/config/loader.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/config/loader.py:1)
- [rag_eval/config/schema.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/config/schema.py:1)
- [rag_eval/config/validators.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/config/validators.py:1)

它定义的内容包括：

- `mode`: `offline` 或 `online`
- `dataset`
- `judge_model`
- `embedding_model`
- `metrics`
- `output_dir`
- `runtime`
- `app_adapter`

作用可以概括为一句话：  
**scenario 决定“这次评测要怎么跑”。**

---

## 6. Dataset 链路

数据进入评测引擎后，不会直接拿原始 CSV 去打分，而是要先标准化。

相关代码：

- [rag_eval/datasets/loader.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/datasets/loader.py:1)
- [rag_eval/datasets/validators.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/datasets/validators.py:1)
- [rag_eval/datasets/normalizers.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/datasets/normalizers.py:1)

它做三件事：

1. 读取 CSV / Excel / JSONL
2. 校验必要字段
3. 转成统一内部对象 `NormalizedSample`

统一样本结构定义在：

- [rag_eval/shared/models.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/shared/models.py:1)

最关键字段是：

- `question`
- `contexts`
- `answer`
- `ground_truth`

这个统一结构是后续 metrics 和 reporting 能共用一条链路的前提。

---

## 7. Offline 和 Online 的真正区别

这是整个系统最关键的分叉点。

### Offline 模式

离线模式下，dataset 里已经有完整评测字段：

- `question`
- `contexts`
- `answer`
- `ground_truth`

所以链路是：

```text
load dataset -> normalize -> score metrics -> write artifacts
```

这个模式不需要调用你的应用。

### Online 模式

在线模式下，dataset 往往只有：

- `question`
- 一些 metadata

`answer` 和 `contexts` 需要评测时实时调用你的 RAG 应用拿回来。

所以链路会变成：

```text
load dataset -> normalize -> call app adapter -> enrich samples -> score metrics -> write artifacts
```

在线模式比离线模式多出来的核心环节，就是 **adapter 调用**。

---

## 8. `apps/sample_python/` 到底是干什么的

这个目录是一个 **Python adapter 示例**。

相关文件：

- [apps/sample_python/adapter.py](/C:/Users/A200477427/Learnings/ragas-template/apps/sample_python/adapter.py:1)
- [apps/sample_python/README.md](/C:/Users/A200477427/Learnings/ragas-template/apps/sample_python/README.md:1)

它演示了：如果你的 RAG 应用是本地 Python 代码，那么框架期望你提供一个这样的函数：

```python
def run(question: str, **kwargs) -> dict:
    return {
        "answer": "...",
        "contexts": ["...", "..."],
        "raw_response": {...},
    }
```

也就是说，`apps/sample_python/` 不是评测引擎的一部分，而是“被评测应用”的一个参考接入模板。

它的作用是：

- 告诉你 Python 类型应用如何接入
- 给 `python` adapter 一个最小可运行示例
- 让你后续把真实 RAG 逻辑替换进去

---

## 9. Adapter 链路

adapter 层的目标是：**把不同类型的目标应用，统一成同一套输入输出协议。**

相关代码：

- [rag_eval/adapters/base.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/adapters/base.py:1)
- [rag_eval/adapters/http.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/adapters/http.py:1)
- [rag_eval/adapters/python.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/adapters/python.py:1)

当前支持两类 adapter：

### `python`

适用于本地 Python 应用。  
框架会根据 scenario 里的 `module:function` 动态加载函数，然后调用它。

### `http`

适用于独立 HTTP 服务。  
框架会构造请求、解析响应，并映射到统一结构。

无论哪种 adapter，最后都要返回统一结果：

- `answer`
- `contexts`
- `raw_response`（可选）

这一步很关键，因为 metrics 层不应该关心底层到底是 HTTP 服务还是 Python 函数。

---

## 10. Evaluator 链路

评测执行核心在：

- [rag_eval/execution/evaluator.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/execution/evaluator.py:1)

`Evaluator.evaluate()` 大致会做这些事：

1. 记录开始时间
2. 加载 dataset
3. 标准化样本
4. 如果是 `online`，先调用 adapter 补齐样本
5. 调用 metric pipeline 打分
6. 合并样本字段和评分结果
7. 返回 `EvaluationResult`

这里可以把 `Evaluator` 理解成：

**一次评测运行的总执行器**

---

## 11. Metric Pipeline 链路

相关代码：

- [rag_eval/metrics/factory.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/metrics/factory.py:1)
- [rag_eval/metrics/pipeline.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/metrics/pipeline.py:1)
- [rag_eval/metrics/registry.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/metrics/registry.py:1)

这里的职责不是“决定评什么”，而是“把要评的指标真正跑起来”。

具体包括：

- 初始化 OpenAI client
- 创建 judge model / embedding model
- 根据 scenario 装配对应的 ragas metrics
- 并发执行单样本或批量评分

当前支持的指标包括：

- `faithfulness`
- `answer_relevancy`
- `context_recall`
- `context_precision`

所以 metric pipeline 的职责可以总结为：

**把标准样本转换成结构化评分结果。**

---

## 12. Reporting 链路

相关代码：

- [rag_eval/reporting/artifacts.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/reporting/artifacts.py:1)
- [rag_eval/reporting/summary.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/reporting/summary.py:1)
- [rag_eval/reporting/writers.py](/C:/Users/A200477427/Learnings/ragas-template/rag_eval/reporting/writers.py:1)

当评测完成后，结果不会只打印在终端，而是会沉淀成标准资产。

标准输出一般包括：

- `scenario.snapshot.yaml`
- `scores.csv`
- `invalid.csv`
- `summary.md`
- `metadata.json`

这是整套架构很重要的价值点，因为它让每次 run 都具备：

- 可复现性
- 可审计性
- 可对比性

---

## 13. 两条完整链路示意

### Offline 完整链路

```text
main.py
  -> run_scenario()
  -> load_scenario()
  -> load_dataset_records()
  -> normalize_records()
  -> build_metric_pipeline()
  -> score_samples()
  -> write_run_artifacts()
```

特点：

- 不调用被评测应用
- 直接对现成样本评分

### Online 完整链路

```text
main.py
  -> run_scenario()
  -> load_scenario()
  -> build_adapter()
  -> load_dataset_records()
  -> normalize_records()
  -> adapter.enrich_sample()
  -> build_metric_pipeline()
  -> score_samples()
  -> write_run_artifacts()
```

特点：

- 会先调用目标应用
- 再对实时生成的 `answer / contexts` 评分

---

## 14. 你应该怎么理解这套架构

如果只记一条心智模型，可以记这个：

- `rag_eval/` 负责“怎么评”
- `apps/` 负责“被评的应用怎么接进来”
- `datasets/` 负责“评测输入是什么”
- `scenarios/` 负责“这次评测要怎么配置”
- `reporting/` 负责“结果怎么沉淀”

从工程拆分上看，这个架构的核心价值不是“能跑一次评测”，而是：

- 可以反复跑
- 可以换应用跑
- 可以换数据跑
- 可以换模型跑
- 可以把每次实验的资产稳定留住

这也是它和一次性离线脚本的根本区别。
