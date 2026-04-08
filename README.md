<p align="center">
  <img src="./static/logo.png" width="280" alt="AgentSchool Logo">
</p>

<h1 align="center">AgentSchool</h1>

<p align="center">
  <strong>Multi-agent simulation for educational scenarios</strong>
</p>

<p align="center">
  <a href="./README_ZH.md">🇨🇳 中文</a> •
  <a href="./OBSERVER_GUIDE.md">Observer mode</a> •
  <a href="./TESTING_GUIDE.md">Testing guide</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.x-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

---

## 📖 Table of contents

- [Overview](#-overview)
- [Key features](#-key-features)
- [Architecture](#-architecture)
- [Requirements](#-requirements)
- [Quick start](#-quick-start)
- [Configuration](#-configuration)
- [Running and evaluation](#-running-and-evaluation)
- [Observer mode](#-observer-mode)
- [Testing and troubleshooting](#-testing-and-troubleshooting)
- [Project layout](#-project-layout)
- [Code modules](#-code-modules)
- [Further reading](#-further-reading)
- [License](#-license)

---

## 🎯 Overview

**AgentSchool** is a multi-agent simulation for classroom settings. It models a **teacher** and multiple **students** in a virtual class: lecture-style interaction, evolving memory and cognitive state, exercises, questionnaires, and structured logs for offline analysis. It suits experiments and demos in learning technology, learning sciences, or multi-agent teaching strategies.

### Use cases

- Replaying class flow and teacher–student interaction
- Comparing learning behavior under different student profiles (personality, cognition, affect)
- Piping logs into an evaluation pipeline for quantitative analysis
- Pausing, inspecting state, or rolling back **teacher** state at runtime via the observer interface

---

## ✨ Key features

### Multi-agent classroom

- **Teacher agent**: Advances lessons from schedule and textbook; strategy and experience settings in `config/teacher.json`.
- **Student agent**: Closed loop of perceive → retrieve → reflect → plan → execute; memory types include events, thoughts, chats, and knowledge.
- **Time and events**: Class and simulation pace driven by `config/schedule.json`.

### Data and evaluation

- **Run logs**: Each run writes under `logs/<timestamp>/<lesson>/`, including actions, broadcasts, terminal capture, and per-student logs.
- **Evaluation**: `evaluation/Evaluation.py` analyzes teaching process and student performance from logs.

### Observer mode (runtime control)

- No code changes: edit `observer_cmd.json` in the project root (polled about every 0.5s).
- Supports **pause / resume / status / exit**, plus **rollback** (restore saved **teacher** state) and **intervene** (stub; see `teacher/teacher.py`).

---

## 🏗️ Architecture

| Area | Description |
|------|-------------|
| **Language & runtime** | Python 3, asynchronous flow (`asyncio`) |
| **LLM calls** | `util/model.py` reads `SCHOOLAGENT_API_KEY`; endpoints and models per role in `config/model.json` |
| **Embeddings & retrieval** | Students: optional `BGE_MODEL` (local path or Hugging Face name). Teacher vector DB: optional `BGE_MODEL_L` (see `student/exercise.py`, `teacher/vector_db.py`) |
| **Messaging & logging** | `util/BroadcastSys.py`, `util/Recorder.py`, etc. |

Install dependencies from `student/requirements.txt`. If pinned versions or local-path wheels conflict with your machine, adjust them inside a virtual environment before installing.

---

## 📋 Requirements

### Required

- **Python 3.x**
- **LLM API**: set `SCHOOLAGENT_API_KEY` (see `util/model.py`)

### Optional

- **`BGE_MODEL`**: embedding model path or Hugging Face id for student exercises and prompts; if unset, the app may download automatically depending on network and cache.
- **`BGE_MODEL_L`**: larger embedding model for the teacher-side vector store.

---

## 🚀 Quick start

### 1. Enter the project and install dependencies

```bash
cd AgentSchool
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r student/requirements.txt
```

### 2. Configure API and embeddings

**Linux / macOS:**

```bash
export SCHOOLAGENT_API_KEY="YOUR_API_KEY"
# Optional: local embedding directory or Hub model id
# export BGE_MODEL="/path/to/bge-small-zh-v1.5"
# export BGE_MODEL_L="/path/to/bge-large-zh"
```

**Windows (PowerShell):**

```powershell
$env:SCHOOLAGENT_API_KEY = "YOUR_API_KEY"
```

### 3. Start the simulation

```bash
python run.py
```

After startup, the terminal shows the path to the observer command file (default: `observer_cmd.json` in the project root). In another terminal or editor, set the `command` field and save to send a command.

### 4. Questionnaires and exercises only (optional)

To skip the full timetable:

```bash
python eval_only.py
```

By default this uses `student/问卷.json` and `student/data.jsonl`; change the constants in the script if needed.

---

## ⚙️ Configuration

Settings live under `config/`.

### `model.json` (models and APIs)

Per-role API base URLs and model names for teacher, student, textbook pipeline, evaluation, etc., so you can mix providers.

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

### `schedule.json` (timetable and time)

Round duration, total lessons, start date, and weekly slots (name, type, start/end times).

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

### `config/student/*.json` (students)

One JSON per student. Must include `folder` (state directory, e.g. `student/students/StudentA`) plus name, grade, personality, cognitive/affective notes, learning style, etc. The run creates or updates `scratch.json` and memory files there.

### `teacher.json` (teacher)

Fields such as name, subject, `textbook_file`, `personalize_or_not`, `experience_level`, `pck_level`, `overall_target`, `teaching_strategy_template`, `teaching_strategy`. See comments or the sample `config/teacher.json` in the repo.

---

## ▶️ Running and evaluation

| Entry | Description |
|-------|-------------|
| `python run.py` | Main simulation: load config, init agents, drive schedule and observer loop |
| `python evaluation/Evaluation.py` | Evaluation over generated logs |

Example log path: `logs/20250822_140638/1/` is lesson 1 of that run, containing `action_log.json`, `broadcast_log.json`, `output.txt`, `student_log.json`, etc.

---

## 👁️ Observer mode

While the simulation runs, write commands to `observer_cmd.json` in the project root (save to apply; the same command is not fired twice—matches `last_command` deduplication in `run.py`).

### Commands

| Command | Effect |
|---------|--------|
| `pause` | Pause after the current round; print state |
| `resume` | Resume from pause |
| `status` | Print time, teacher phase and round, student attention and behavior (does not force pause) |
| `exit` | Shut down cleanly |
| `rollback` | Restore saved **teacher** state from `status_<lesson>_<round>.json`; **students are not rolled back**; simulation continues automatically after success |
| `intervene` | Calls `Teacher.handle_observer_intervention()`; **rewriting the live teaching plan is still a stub** |

### `rollback` examples

```json
{
  "command": "rollback",
  "rollback": { "turn": 12 }
}
```

Target a specific lesson (defaults to current):

```json
{
  "command": "rollback",
  "rollback": { "turn": 8, "class": 2 }
}
```

`turn` may be written as `k`. If the matching `status_*.json` is missing, the terminal reports an error and skips rollback.

For `intervene` payloads, `rollback`, and extension points, see **[OBSERVER_GUIDE.md](./OBSERVER_GUIDE.md)** (if it diverges from code, trust `run.py`).

### Helper scripts (Bash)

On Linux/macOS or Git Bash:

```bash
./send_command.sh pause
./send_command.sh status
./send_command.sh rollback 12
./send_command.sh rollback 8 2
```

See `./test_observer.sh` for a one-shot env setup and launch (edit API key and model paths first).

---

## 🧪 Testing and troubleshooting

Suggested **smoke order** (detailed steps, sample console output, and a report template: **[TESTING_GUIDE.md](./TESTING_GUIDE.md)**):

1. Set `SCHOOLAGENT_API_KEY`, run `python run.py`, confirm the observer banner appears.
2. Write `{"command":"status"}` and confirm teacher/student summaries print.
3. Run `pause` then `resume` once each.
4. `rollback`: test on a round where a status file exists; expect “teacher only” rollback behavior.
5. `intervene`: confirm the teacher handler runs and may report incomplete implementation.
6. Invalid JSON or unknown `command` should not crash the process.

**FAQ**

- `SCHOOLAGENT_API_KEY` missing: ensure `export` (Unix) or `$env:` (PowerShell) in the **same** shell that runs Python.
- Embedding load errors: verify `BGE_MODEL` path, or unset it and let defaults apply.
- Observer silent: ensure JSON is saved, key is `command`; validate with `python -m json.tool observer_cmd.json`.

---

## 📁 Project layout

```
AgentSchool/
├── config/
│   ├── student/           # Per-student JSON profiles
│   ├── model.json
│   ├── schedule.json
│   └── teacher.json
├── evaluation/
│   ├── Evaluation.py
│   ├── class_analyser.py
│   └── analysis_output/
├── logs/                  # Per-run timestamp and lesson folders
├── student/               # Student agents, prompts, exercises, questionnaires
├── teacher/               # Teacher agent, textbook, vector DB
├── util/
│   ├── BroadcastMessage.py
│   ├── BroadcastSys.py
│   ├── Events.py
│   ├── file_manager.py
│   ├── model.py           # LLM API
│   ├── Recorder.py
│   └── TimeManager.py
├── observer_cmd.json      # Observer commands (auto-created/overwritten)
├── send_command.sh
├── test_observer.sh
├── run.py                 # Full classroom simulation entry
├── eval_only.py           # Questionnaire + exercise shortcut (optional)
└── main.py                # Single-student debug CLI
```

---

## 🧩 Code modules

### `util/`

- **BroadcastMessage / BroadcastSys**: message types and broadcast routing.
- **Events / TimeManager**: events and simulated time.
- **Recorder**: actions, broadcasts, student-side records.
- **model.py**: env vars and LLM calls.

### `student/`

- **cognitive_module**: `memory.py` (graph and sequences), `scratch.py` (profile), `student.py` (entity and persistence).
- **move.py**: main action loop **perceive → retrieve → reflect → plan → execute** (see `perceive.py`, `retrieve.py`, `reflect.py`, `plan.py`, `execute.py`).
- **prompt/**: prompts and helper scripts for LLM calls.
- **exercise / evaluate**: exercises and scales.
- **saving** (if used): snapshots for mid-run restore.

### `teacher/`

Teacher behavior, textbook preprocessing, vector retrieval, personality assets—see scripts under this tree and `Textbook/`.

---

## 📚 Further reading

| Doc | Contents |
|-----|----------|
| [OBSERVER_GUIDE.md](./OBSERVER_GUIDE.md) | Observer commands, scenarios, internals, extension notes |
| [TESTING_GUIDE.md](./TESTING_GUIDE.md) | Env setup, scripted tests, checklists |
<!-- | [OBSERVER_GUIDE_ZH.md](./OBSERVER_GUIDE_ZH.md) | 上述观察者指南（中文） |
| [TESTING_GUIDE_ZH.md](./TESTING_GUIDE_ZH.md) | 上述测试指南（中文） | -->
| [student/README.md](./student/README.md) | Student subsystem overview |

Treat live console output and `config/` as the source of truth for behavior and analysis.

---

## 📄 License

This project is licensed under the [MIT License](https://opensource.org/licenses/MIT).

```
MIT License

Copyright (c) 2026 AgentSchool Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```
