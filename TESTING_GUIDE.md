# Observer feature testing guide

[中文](./TESTING_GUIDE_ZH.md)

## Prerequisites

### 1. Environment variables

```bash
# Required: LLM API key (see util/model.py)
export SCHOOLAGENT_API_KEY="sk-xxxxxxxxxxxxxxxx"

# Optional: local embedding model directory or Hugging Face model id
export BGE_MODEL="/path/to/bge-small-zh-v1.5"

# Optional: larger model for teacher vector DB
# export BGE_MODEL_L="/path/to/bge-large-zh"
```

**Windows (PowerShell)**

```powershell
$env:SCHOOLAGENT_API_KEY = "sk-xxxxxxxxxxxxxxxx"
```

### 2. Verify local model path (if set)

```bash
ls -lh "$BGE_MODEL"
```

If the directory does not exist, **unset** `BGE_MODEL` and let the program download from Hugging Face (needs network), or fix the path.

---

## Fast path (method A: helper script)

### Step 1: Edit `test_observer.sh`

```bash
cd /path/to/AgentSchool

# Set your real API key inside test_observer.sh
# Replace: export SCHOOLAGENT_API_KEY="your_api_key_here"
```

### Step 2: Run

```bash
./test_observer.sh
```

### Step 3: Send commands from another terminal

```bash
cd /path/to/AgentSchool

# Option A: helper script
./send_command.sh pause
./send_command.sh status
./send_command.sh resume
./send_command.sh exit
./send_command.sh rollback 12
./send_command.sh rollback 8 2

# Option B: edit observer_cmd.json directly
```

---

## Manual path (method B)

### Terminal 1 — start simulation

```bash
cd /path/to/AgentSchool
export SCHOOLAGENT_API_KEY="sk-xxxxxxxxxxxxxxxx"
# export BGE_MODEL="/path/to/your/embedding/model"

python run.py
```

Expected banner (excerpt): observer mode started, path to `observer_cmd.json`, list of commands including **rollback**.

### Terminal 2 — send commands

**Using the script**

```bash
cd /path/to/AgentSchool
./send_command.sh pause
```

**Editing JSON**

```json
{
  "command": "pause"
}
```

Save the file; terminal 1 should react within ~0.5 s.

---

## Test checklist

### Core commands

1. **pause**

```json
{"command": "pause"}
```

Expect: pause after current round, state printed, hint to resume.

2. **status** (while running)

```json
{"command": "status"}
```

Expect: time, teacher, students; simulation keeps running.

3. **resume** (after pause)

```json
{"command": "resume"}
```

Expect: simulation continues from pause point.

4. **exit**

```json
{"command": "exit"}
```

Expect: clean shutdown and state flush.

### Intervention (stub)

5. **intervene**

```json
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "Attention is low; add interaction"
  }
}
```

Expect: pause path engaged, payload printed, `handle_observer_intervention` called, “not fully implemented” style message is OK.

### Rollback

6. **rollback** (when `status_<lesson>_<round>.json` exists)

```json
{
  "command": "rollback",
  "rollback": { "turn": 12 }
}
```

Expect: teacher state restored from checkpoint; terminal notes **students are not rolled back**; run continues automatically on success.

### Robustness

7. **Invalid JSON** (e.g. paste plain text into the file)

Expect: no crash; invalid payload skipped.

8. **Unknown command**

```json
{"command": "unknown"}
```

Expect: ignored safely.

9. **Rapid sequence**

```bash
./send_command.sh pause
./send_command.sh status
./send_command.sh resume
```

Expect: each distinct command handled; remember identical consecutive commands may dedupe—vary commands if testing that path.

---

## Sample console output

### pause

```
======================================================================
📝 [观察者] 收到命令: pause
======================================================================
⏸️  仿真将在当前轮次结束后暂停...
...
⏸️  [观察者] 仿真已暂停
======================================================================
📊 当前仿真状态
...
💡 提示: 编辑 observer_cmd.json 文件，设置 'command': 'resume' 以继续
```

### status

```
======================================================================
📝 [观察者] 收到命令: status
======================================================================

📊 当前仿真状态
======================================================================
```

### intervene (stub)

```
======================================================================
📝 [观察者] 收到命令: intervene
======================================================================
...
[Teacher.handle_observer_intervention] 收到观察者干预
...
🤖 教师响应: ⚠️  观察者干预接口已调用，但具体功能尚未实现
```

---

## Troubleshooting

### `SCHOOLAGENT_API_KEY` not set

```bash
export SCHOOLAGENT_API_KEY="your_key"
```

Use the same shell session that runs `python run.py`.

### Embedding / model load errors

- Confirm `BGE_MODEL` points at a real directory, or `unset BGE_MODEL`
- Set `BGE_MODEL_L` only if you use the teacher vector DB path that reads it

### Commands ignored

- Save the file after edits
- Run from project root so `observer_cmd.json` is the one `run.py` watches
- Validate JSON: `python -m json.tool observer_cmd.json`

### Simulation exits immediately

Check configs:

```bash
ls -l config/teacher.json config/schedule.json config/student/
```

---

## Screen recording tips

1. Split view: simulation terminal + `observer_cmd.json` editor
2. Suggested order: start → wait → `pause` → `status` → `resume` → `rollback` (if files exist) → `intervene` → `exit`

---

## Test report template

```markdown
## Observer feature test report

**When**: YYYY-MM-DD HH:MM
**Environment**:
- Python:
- API key: set / not set
- BGE_MODEL:

| Case | Pass | Notes |
|------|------|-------|
| pause | | |
| resume | | |
| status | | |
| exit | | |
| rollback | | teacher-only |
| intervene | | stub |
| bad JSON | | |
| unknown command | | |

### Issues

1.

### Follow-ups

1.
```

---

More command semantics and extension notes: **[OBSERVER_GUIDE.md](./OBSERVER_GUIDE.md)**.

If this guide disagrees with the code, trust **`run.py`**.
