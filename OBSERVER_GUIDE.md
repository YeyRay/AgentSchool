# Observer mode guide

[中文](./OBSERVER_GUIDE_ZH.md)

## Overview

Observer mode lets you monitor and (eventually) steer the simulation while it runs, without restarting.

## Quick start

### 1. Start the simulation

```bash
python run.py
```

You should see something like:

```
======================================================================
📝 [观察者模式] 已启动
======================================================================
命令文件: /path/to/AgentSchool/observer_cmd.json

可用命令:
  • pause     - 暂停仿真
  • resume    - 继续仿真
  • status    - 查看当前状态
  • intervene - 打断并调整教学计划（预留接口）
  • rollback  - 回溯到第k轮（需在JSON中提供rollback.turn与可选class）
  • exit      - 退出仿真

使用方法: 编辑 observer_cmd.json 文件，修改 'command' 字段并保存
======================================================================
```

*(Banner text may be partially localized; command names match `run.py`.)*

### 2. Send a command

Open `observer_cmd.json` in another terminal or editor, edit the JSON, and **save**. The listener polls about every **0.5 s** and processes a new non-empty `command`.

---

## Commands

### pause — pause the simulation

**Use when** you want to freeze after the current round and inspect state.

```json
{
  "command": "pause"
}
```

**Behavior**

- Pauses after the current time step completes
- Prints teacher and student state
- Waits for your next command

---

### resume — continue

**Use when** resuming from a pause.

```json
{
  "command": "resume"
}
```

**Behavior**: simulation continues from where it paused.

---

### status — print state (no pause)

**Use when** you want a snapshot without stopping the loop.

```json
{
  "command": "status"
}
```

**Includes**

- Time: simulated clock, active event
- Teacher: lesson index, phase, round, current content snippet
- Students: attention, current action, memory node counts

**Sample output**

```
======================================================================
📊 当前仿真状态
======================================================================

⏱️  时间信息:
  • 当前时间: 2025-09-01 08:15:30 Monday
  • 当前事件: class (ID: 1)

👨‍🏫 教师状态:
  • 姓名: 王老师
  • 课程进度: 第 1 节课
  • 教学阶段: subsection_lecture
  • 当前轮次: 15/40
  • 当前内容: 同学们，我们来看数轴上的-6和6这两个点...

👥 学生状态:
  • StudentA:
      - 注意力: 0.85
      - 当前行为: listening
      - 记忆节点数: 42
  • StudentB:
      - 注意力: 0.72
      - 当前行为: listening
      - 记忆节点数: 38
```

---

### rollback — restore saved teacher state

**Use when** a teacher checkpoint `status_<lesson>_<round>.json` exists and you want to rewind **the teacher only** (student state is **not** rolled back). After a successful jump, the simulation **resumes automatically** (`run.py`).

```json
{
  "command": "rollback",
  "rollback": { "turn": 12 }
}
```

Optional lesson index (defaults to current lesson):

```json
{
  "command": "rollback",
  "rollback": { "turn": 8, "class": 2 }
}
```

The round field may be `turn` or `k`. If the status file is missing, the terminal prints an error and skips rollback.

---

### intervene — observer intervention (stub)

**Intent**: interrupt and adjust the teaching plan.

```json
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "Student attention is dropping; add an interactive segment",
    "parameters": {
      "add_discussion": true,
      "topic": "Real-world use of opposites"
    }
  }
}
```

**`intervention` fields**

| Field | Type | Description | Examples |
|-------|------|-------------|----------|
| `type` | string | Intervention kind | `adjust_plan`, `change_strategy`, `skip_section` |
| `instruction` | string | Natural-language hint | `"Add a short group discussion"` |
| `parameters` | object | Optional structured args | See below |

**Examples by type**

#### adjust_plan

```json
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "Students are struggling; add worked examples",
    "parameters": {
      "add_examples": 2,
      "difficulty": "basic"
    }
  }
}
```

#### change_strategy

```json
{
  "command": "intervene",
  "intervention": {
    "type": "change_strategy",
    "instruction": "Switch to more inquiry-based teaching",
    "parameters": {
      "strategy": "inquiry_based"
    }
  }
}
```

#### skip_section

```json
{
  "command": "intervene",
  "intervention": {
    "type": "skip_section",
    "instruction": "Skip this subsection and move on",
    "parameters": {
      "skip_to": 5
    }
  }
}
```

**Current status**

- Hook exists; full plan rewriting is **not** implemented yet
- Entry point: `Teacher.handle_observer_intervention()` in `teacher/teacher.py`
- Today the run typically prints the payload and a “not fully implemented” style message

---

### exit — stop cleanly

```json
{
  "command": "exit"
}
```

**Behavior**: stops the simulation loop, saves state, and tears down resources.

---

## Typical workflows

### 1. Watch attention over time

```bash
python run.py
```

Then in `observer_cmd.json`:

```json
{"command": "status"}
```

```json
{"command": "pause"}
```

```json
{"command": "resume"}
```

### 2. Pause, inspect, try an intervention (stub)

```json
{"command": "pause"}
```

```json
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "Add a quick Q&A segment"
  }
}
```

```json
{"command": "resume"}
```

---

## Technical notes

### Command file handling

- Poll interval ~**0.5 s** (`run.py`)
- After handling, `command` is cleared so the same payload is not re-run
- Dedup uses `last_command`: repeating the identical command string is ignored until you issue a different command (see `observer_command_listener` in `run.py`)

### Pause semantics

- **Non-blocking**: does not deadlock the asyncio loop
- **Safe**: pause applies after the current round finishes
- While paused you can still reason about logs and send further commands

### Stub design for `intervene`

```python
async def handle_observer_intervention(self, intervention_data: dict):
    """
    Handle observer interventions and adjust teaching plans.

    TODO:
    - Parse natural language with an LLM
    - Branch on intervention type
    - Update self.plan, self.teaching_strategy, etc.
    - Return a structured result
    """
    # To be implemented...
```

---

## FAQ

### Commands seem ignored?

1. Validate JSON (`python -m json.tool observer_cmd.json`)
2. Check `command` spelling (lowercase after strip in code)
3. Watch the terminal for parse errors

### Logs plus commands?

- **Terminal 1**: `python run.py`
- **Terminal 2**: `tail -f logs/<run_id>/1/output.txt` (Unix) or open the log file in your editor
- **Editor**: keep `observer_cmd.json` open for edits

### Why does `intervene` not change the lesson?

It is a **reserved hook**: content is printed and the teacher method runs, but persistent replanning logic still needs to be implemented in `handle_observer_intervention`.

---

## Extending `intervene`

### 1. Edit `teacher/teacher.py`

```python
async def handle_observer_intervention(self, intervention_data: dict):
    intervention_type = intervention_data.get("type", "")

    if intervention_type == "adjust_plan":
        instruction = intervention_data.get("instruction", "")
        prompt = f"Adjust the teaching plan given this observer note: {instruction}"
        new_plan = call_LLM_sync(prompt, ...)
        self.plan = parse_plan(new_plan)
        return "Teaching plan updated"

    # Other types...
```

### 2. Smoke-test

```json
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "Your custom instruction"
  }
}
```

---

## Important caveats

- The command file’s `command` field is cleared after execution
- Simulated time does not advance while paused
- `exit` cannot be undone
- Frequent pause/resume may hurt narrative continuity
- **`rollback` restores teacher checkpoints only**, not full student memory graphs

---

## Contributing

Issues and pull requests are welcome.

If this document disagrees with the code, **`run.py` wins**.
