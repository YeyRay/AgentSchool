<p align="center">
  <img src="./static/logo.png" width="280" alt="AgentSchool Logo">
</p>

<h1 align="center">AgentSchool</h1>

<p align="center">
  <strong>面向教育场景的多智能体仿真系统</strong>
</p>

<p align="center">
  <a href="./README.md">🌍 English</a> •
  <a href="./OBSERVER_GUIDE_ZH.md">观察者模式</a> •
  <a href="./TESTING_GUIDE_ZH.md">测试指南</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.x-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

---

## 📖 目录

- [项目简介](#-项目简介)
- [核心特性](#-核心特性)
- [技术架构](#-技术架构)
- [环境要求](#-环境要求)
- [快速开始](#-快速开始)
- [配置指南](#-配置指南)
- [运行与评估](#-运行与评估)
- [观察者模式](#-观察者模式)
- [测试与排错](#-测试与排错)
- [项目结构](#-项目结构)
- [代码模块说明](#-代码模块说明)
- [延伸阅读](#-延伸阅读)

---

## 🎯 项目简介

**AgentSchool** 是一个用于教学场景的多智能体仿真项目，在虚拟课堂中同时模拟**教师**与多名**学生**的行为：支持授课互动、记忆与认知状态演化、练习与问卷等环节，并输出结构化日志供事后分析。项目适合用于教育技术、学习科学或多智能体教学策略的实验与演示。

### 适用场景

- 课堂教学流程与师生互动的仿真复现
- 不同学生画像（人格、认知、情感）下的学习行为对比
- 与评估流水线结合，对仿真日志做量化分析
- 运行时通过观察者接口暂停、查看状态或回溯教师状态

---

## ✨ 核心特性

### 多智能体课堂

- **教师智能体**：按课表与教材推进教学，支持策略与经验等配置（`config/teacher.json`）。
- **学生智能体**：感知、检索、反思、计划与执行闭环；记忆分为事件、想法、对话、知识等类型。
- **时间与事件**：按 `config/schedule.json` 驱动课程与仿真节奏。

### 数据与评估

- **运行日志**：每次运行写入 `logs/<时间戳>/<课次>/`，含行动、广播、终端输出与学生日志。
- **评估脚本**：`evaluation/Evaluation.py` 基于日志做教学过程与学生表现分析。

### 观察者模式（运行时控制）

- 无需改代码：编辑项目根目录下的 `observer_cmd.json` 即可下发命令（约每 0.5 秒轮询一次）。
- 支持 **pause / resume / status / exit**，以及 **rollback**（回溯教师已保存状态）与 **intervene**（预留接口，见 `teacher/teacher.py`）。

---

## 🏗️ 技术架构


| 类别         | 说明                                                                                                         |
| ---------- | ---------------------------------------------------------------------------------------------------------- |
| **语言与运行时** | Python 3，异步流程（`asyncio`）                                                                                   |
| **大模型调用**  | 通过 `util/model.py` 使用环境变量 `SCHOOLAGENT_API_KEY`，接口与模型在 `config/model.json` 中按角色拆分                          |
| **向量与检索**  | 学生侧可用环境变量 `BGE_MODEL` 指定本地 Embedding；教师向量库可用 `BGE_MODEL_L`（见 `student/exercise.py`、`teacher/vector_db.py`） |
| **消息与记录**  | `util/BroadcastSys.py`、`util/Recorder.py` 等负责广播与日志落地                                                       |


依赖清单以仓库内 `student/requirements.txt` 为准；若其中包含与本机环境不兼容的固定版本或本地路径包，请按需在虚拟环境中调整后再安装。

---

## 📋 环境要求

### 必需

- **Python 3.x**
- **大模型 API**：设置环境变量 `SCHOOLAGENT_API_KEY`（与 `util/model.py` 一致）

### 可选

- `**BGE_MODEL`**：学生相关练习与提示中的 Embedding 模型路径或 Hugging Face 模型名；不设置时可能自动下载，具体情况视网络与缓存而定
- `**BGE_MODEL_L**`：教师侧向量库使用的较大 Embedding 模型

---

## 🚀 快速开始

### 1. 进入项目并安装依赖

```bash
cd AgentSchool
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r student/requirements.txt
```

### 2. 配置 API 与 Embedding

**Linux / macOS：**

```bash
export SCHOOLAGENT_API_KEY="你的API_KEY"
# 可选：本地向量模型目录或 Hub 模型名
# export BGE_MODEL="/path/to/bge-small-zh-v1.5"
# export BGE_MODEL_L="/path/to/bge-large-zh"
```

**Windows（PowerShell）：**

```powershell
$env:SCHOOLAGENT_API_KEY = "你的API_KEY"
```

### 3. 启动仿真

```bash
python run.py
```

启动成功后，终端会提示观察者命令文件路径（默认同目录 `observer_cmd.json`）。另开终端或编辑器修改该文件中的 `command` 字段并保存即可下发命令。

### 4. 仅跑问卷与练习

（可选）不跑完整课表时，可使用：

```bash
python eval_only.py
```

（默认使用 `student/问卷.json` 与 `student/data.jsonl`，可按需修改脚本内常量。）

---

## ⚙️ 配置指南

参数集中在 `config/` 目录。

### `model.json`（模型与 API）

为教师、学生、教材处理、评估等角色分别指定 API 地址与模型名，便于混用不同服务商或模型。

```json
{
  "teacher_api_url": "https://api.deepseek.com/v1",
  "teacher_model": "deepseek-chat",
  "student_api_url": "https://api.deepseek.com/v1",
  "student_model": "deepseek-chat",
  "textbook_api_url": "https://api.deepseek.com/v1",
  "textbook_model": "deepseek-reasoner",
  "evaluation_api_url": "https://api.deepseek.com/v1",
  "evaluation_model": "deepseek-chat"
}
```

### `schedule.json`（课表与时间）

定义每轮时长、总课次数、开学日期及周内课程安排（课程名、类型、起止时间等）。

```json
{
  "round_time": 60,
  "total_courses": 2,
  "start_date": "2025-09-01",
  "Monday": [
    {
      "name": "math_class",
      "type": "class",
      "start": "08:00",
      "end": "08:40"
    }
  ]
}
```

### `config/student/*.json`（学生）

每位学生一个 JSON，需包含 `folder`（状态落盘目录，如 `student/students/StudentA`）以及姓名、年级、人格、认知/情感描述、学习风格等字段；运行时会据此生成或更新 `scratch.json` 与记忆文件。

### `teacher.json`（教师）

包含姓名、科目、`textbook_file`、`personalize_or_not`、`experience_level`、`pck_level`、`overall_target`、`teaching_strategy_template`、`teaching_strategy` 等。字段含义见原配置注释或仓库内示例 `config/teacher.json`。

---

## ▶️ 运行与评估


| 入口                                | 说明                           |
| --------------------------------- | ---------------------------- |
| `python run.py`                   | 主仿真：加载配置、初始化师生智能体、驱动课表与观察者循环 |
| `python evaluation/Evaluation.py` | 评估模块：分析已产生的日志                |


日志目录示例：`logs/20250822_140638/1/` 表示某次运行中第 1 节课，内含 `action_log.json`、`broadcast_log.json`、`output.txt`、`student_log.json` 等。

---

## 👁️ 观察者模式

仿真运行期间，通过根目录 `**observer_cmd.json**` 发送命令（保存即生效；同一命令不会重复触发，与 `run.py` 中 `last_command` 去重逻辑一致）。

### 命令一览


| 命令          | 作用                                                                      |
| ----------- | ----------------------------------------------------------------------- |
| `pause`     | 当前轮次结束后暂停，并展示状态                                                         |
| `resume`    | 从暂停恢复                                                                   |
| `status`    | 打印当前时间、教师阶段与轮次、学生注意力与行为等（不强制暂停）                                         |
| `exit`      | 优雅结束仿真                                                                  |
| `rollback`  | 回溯到已保存的**教师**状态文件 `status_<课次>_<轮次>.json`；**仅恢复教师状态**，学生状态不回滚；成功后自动继续仿真 |
| `intervene` | 调用 `Teacher.handle_observer_intervention()`，**具体教学计划改写仍为预留能力**          |


### `rollback` 示例

```json
{
  "command": "rollback",
  "rollback": { "turn": 12 }
}
```

指定课次（默认为当前课）：

```json
{
  "command": "rollback",
  "rollback": { "turn": 8, "class": 2 }
}
```

`turn` 也可写作 `k`。若对应 `status_*.json` 不存在，终端会报错并跳过回溯。

<!-- ### `intervene` 示例（预留）

```json
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "学生注意力下降，建议增加互动环节",
    "parameters": { "add_discussion": true }
  }
}
```

扩展实现入口：`teacher/teacher.py` 中的 `handle_observer_intervention`。 -->

### 快捷脚本（Bash）

在 Linux/macOS 或 Git Bash 下可使用：

```bash
./send_command.sh pause
./send_command.sh status
./send_command.sh rollback 12
./send_command.sh rollback 8 2
```

一键设置环境并启动可参考 `./test_observer.sh`（使用前请将其中 API Key 与模型路径改为本机值）。

更完整的命令说明、场景示例与 FAQ 见 **[OBSERVER_GUIDE_ZH.md](./OBSERVER_GUIDE_ZH.md)**；英文版见 [OBSERVER_GUIDE.md](./OBSERVER_GUIDE.md)（若与当前代码不一致，以 `run.py` 为准）。

---

## 🧪 测试与排错

建议按下列顺序做**冒烟验证**（详细步骤、预期终端输出与报告模板见 **[TESTING_GUIDE_ZH.md](./TESTING_GUIDE_ZH.md)**；英文版见 [TESTING_GUIDE.md](./TESTING_GUIDE.md)）：

1. 设置 `SCHOOLAGENT_API_KEY` 后执行 `python run.py`，确认出现观察者模式启动横幅。
2. 写入 `{"command":"status"}`，确认打印教师与学生摘要。
3. `pause` → `resume` 各执行一次，确认暂停与恢复。
4. `rollback`：在已知已生成状态文件的轮次上测试；接受「仅教师回滚」的提示行为。
5. `intervene`：确认会调用教师处理函数并提示功能未完全实现（若当前版本仍如此）。
6. 故意写入非法 JSON 或未知 `command`，进程应保持稳定。

**常见问题**

- 提示未设置 `SCHOOLAGENT_API_KEY`：检查当前 shell 是否已 `export` / `$env:` 设置。
- Embedding 加载失败：检查 `BGE_MODEL` 路径，或暂时取消该变量让程序按默认方式获取模型。
- 观察者无响应：确认 JSON 已保存、字段名为 `command`，可用 `python -m json.tool observer_cmd.json` 校验格式。

---

## 📁 项目结构

```
AgentSchool/
├── config/
│   ├── student/           # 各学生 JSON 配置
│   ├── model.json
│   ├── schedule.json
│   └── teacher.json
├── evaluation/
│   ├── Evaluation.py
│   ├── class_analyser.py
│   └── analysis_output/
├── logs/                  # 每次运行的按时间戳与课次划分的日志
├── student/               # 学生智能体、提示词、练习与问卷资源等
├── teacher/               # 教师智能体、教材与向量库等
├── util/
│   ├── BroadcastMessage.py
│   ├── BroadcastSys.py
│   ├── Events.py
│   ├── file_manager.py
│   ├── model.py           # LLM API
│   ├── Recorder.py
│   └── TimeManager.py
├── observer_cmd.json      # 观察者命令（可自动生成/覆盖）
├── send_command.sh
├── test_observer.sh
├── run.py                 # 全课堂仿真主入口
├── eval_only.py           # 问卷+练习快捷入口（可选）
└── main.py                # 单学生智能体调试入口（命令行参数指定学生）
```

---

## 🧩 代码模块说明

### `util/`

- **BroadcastMessage / BroadcastSys**：消息定义与广播分发。
- **Events / TimeManager**：事件与时间推进。
- **Recorder**：行动、广播、学生侧记录。
- **model.py**：统一读取环境变量并调用大模型接口。

### `student/`

- **cognitive_module**：`memory.py`（记忆图与序列）、`scratch.py`（静态档案）、`student.py`（学生实体与持久化）。
- **move.py**：行动主流程，串联 **perceive → retrieve → reflect → plan → execute**（具体实现分布在 `perceive.py`、`retrieve.py`、`reflect.py`、`plan.py`、`execute.py` 等）。
- **prompt/**：调用 LLM 的提示词与工具脚本。
- **exercise / evaluate**：做题与量表评估。
- **saving**（若使用）：断点快照，用于恢复中间状态。

### `teacher/`

教师行为、教材预处理、向量检索与人格相关配置等（详见目录内脚本与 `Textbook/`）。

---

## 📚 延伸阅读


| 文档                                       | 内容                       |
| ---------------------------------------- | ------------------------ |
| [OBSERVER_GUIDE_ZH.md](./OBSERVER_GUIDE_ZH.md) | 观察者命令详解、典型场景、技术细节与扩展开发提示 |
| [TESTING_GUIDE_ZH.md](./TESTING_GUIDE_ZH.md)   | 环境准备、脚本测试流程、检查清单与排错      |
<!-- | [OBSERVER_GUIDE.md](./OBSERVER_GUIDE.md)       | Observer guide (English) |
| [TESTING_GUIDE.md](./TESTING_GUIDE.md)         | Testing guide (English)  | -->
| [student/README.md](./student/README.md) | 学生子模块说明             |


教学仿真与日志分析请以实际运行输出与 `config` 为准。

---

## 📄 开源许可

本项目采用 [MIT](https://opensource.org/licenses/MIT) 许可证。

```
MIT License

Copyright (c) 2026 AgentSchool Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```