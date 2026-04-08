## 学生子系统（student/）

面向“学生端”学习流程的核心模块集合，包含知识图谱、认知感知、题目生成与评测、异步执行与提示工程等功能。支持从题库/日志导入证据、动态更新掌握度，并输出学习结果与可视化数据。

### 目录结构
- `knowledge_graph.py`: 概念图与掌握度管理（概念、先修、练习映射、掌握度更新）
- `perceive.py`: 学生状态感知与个性化画像（认知风格、偏好、情绪等）
- `exercise.py`: 题目生成/筛选与评测的基础实现
- `new_exercise.py`: 增强版题目生成与流程控制（更复杂的策略/约束）
- `evaluate.py`: 评估流程与指标计算
- `global_methods.py`: 通用工具函数
- `main.py`: 学习与评测的本地入口（同步）
- `prompt/`: 提示工程相关（检索、执行、异步）
  - `retrieve.py`, `execute.py`, `async_exercise.py`
- `cognitive_module/`: 学生记忆与推理相关模块
  - `analyze.py`, `exercise_modifiers.py`
- `students/`: 学生嵌入、节点与草稿（运行时数据）
- `saving/`: 每次运行的快照/中间产物
- `evaluation/`, `test_StudentA|B|C/`: 评测与测试数据
- `questions/`: 题库与知识点映射（如 `knowledge_points.json`）
- 数据文件：
  - `数学知识点.json`: 大规模知识点与依赖数据
  - `大五人格量表.json`, `认知风格量表.json`: 学生画像问卷

### 快速开始
#### 1. 环境依赖
- Python 3.10+
- 在项目根目录执行依赖安装：
```bash
pip install -r requirements.txt
```

#### 2. 最小可运行示例
- 同步执行学生流程：
```bash
python -m student.main
```
- 使用异步题目执行（位于 `student/prompt/`）：
```bash
python -m student.prompt.async_exercise
```

运行后会在 `student/saving/` 与 `student/students/` 写入运行数据，在项目根目录的 `results/` 下生成结果文件（若由上层 orchestrator 触发）。

### 核心概念
- 概念（Concept）：最小可学习知识点（如“加减消元法”），带有元数据（年级/章节/标签/难度等）。
- 先修关系（PREREQ）：概念间依赖图，用于路径规划与掌握度传播。
- 掌握度（Mastery）：学生对概念的当前掌握水平与稳定度，可随作答在线更新与遗忘衰减。
- 证据（Evidence）：一次作答或行为数据（正确性、耗时、提示、步骤等），用于更新掌握度与诊断。

### 数据流与产物
1. 载入知识点与先修：`数学知识点.json`、`questions/knowledge_points.json`
2. 学生画像/初始化：`大五人格量表.json`、`认知风格量表.json`
3. 检索与生成题目：`prompt/retrieve.py` + `exercise.py|new_exercise.py`
4. 作答与证据：写入 `saving/` 与 `students/`（以及项目根 `results/`）
5. 更新掌握度：`knowledge_graph.py` 接收 Evidence，更新 `MASTERY`（含稳定度/暴露次数/时间戳）
6. 输出：评测报告、进度曲线、可视化所需 JSON

### 知识图谱与掌握度（简要）
- 节点：Concept、Exercise、Student、Evidence（可选 Misconception/Strategy）
- 关系：
  - `Concept-[:PREREQ]->Concept` 先修
  - `Exercise-[:ASSESS {weight}]->Concept` 题目测哪些概念
  - `Student-[:MASTERY {p, theta, stability, exposures, last_update}]->Concept`
  - `Evidence-[:PRODUCED_BY]->Student`，`Evidence-[:EVALUATES]->Exercise`，`Evidence-[:INDICATES]->Concept`
- 在线更新（示例策略）：
  - 预测正确率 `p_hat = sigmoid(theta_student - b_item)`
  - 学生能力更新 `theta' = theta + η * w * (y - p_hat)`
  - 稳定度随答对上升、答错下降；查询时可做时间衰减

> 具体实现位于 `knowledge_graph.py`，可切换或组合 Elo/IRT/BKT/DKT 等。

### 运行与配置要点
- 默认配置与常量集中在各模块顶部或 `global_methods.py`
- 可通过环境变量或命令行参数控制：模型调用、并发、日志级别、随机种子等
- 大型文件（题库/日志）按需懒加载，避免一次性占用内存

### 日志与结果
- 学生过程日志：项目根 `student_log.json`
- 广播/系统日志：项目根 `broadcast_log.json`
- 运行轨迹：`student/saving/` 与 `student/students/`
- 评测结果与可视化输入：`results/<StudentX>/...`

### 常见问题（FAQ）
- 显存/内存不足？
  - 关闭不必要的模型组件、降低并发、分批载入题库
- 掌握度更新不稳定？
  - 调整学习率 `η` 与稳定度增益/损失系数；增加题目-概念权重校准
- 题目难度不均？
  - 使用 `retrieve.py` 的过滤与排序；在 `new_exercise.py` 增加难度自适应策略

### 测试
- 单元/集成用例（示例）：
  - `student/test/`、`student/test_StudentA|B|C/`
  - 根目录 `test_*.py` 用于关键流程回归
```bash
pytest -q
```

### 开发建议
- 保持模块高内聚、低耦合：题目生成、评估、图谱更新、可视化分层
- 所有增量产物落到 `saving/`，便于回溯与对比实验
- 图谱更新留存 Evidence 与快照，确保可解释与可审计

### 入口参考
```bash
# 同步学生流程
python -m student.main

# 异步题目执行（Prompt/检索/执行）
python -m student.prompt.async_exercise
```

如需将现有 `results/` 与 `students/` 数据导入知识图谱并做在线评估，可在 `knowledge_graph.py` 增加导入脚本或提供最小服务化接口（POST /evidence，GET /mastery）。


