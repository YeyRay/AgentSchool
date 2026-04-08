# 观察者模式使用指南

[English](./OBSERVER_GUIDE.md)

## 功能概述

观察者模式允许你在仿真运行时实时监控并干预教学过程，无需重启仿真。

## 快速开始

### 1. 启动仿真

```bash
python run.py
```

启动后，你会看到类似的提示：

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
  • exit      - 退出仿真

使用方法: 编辑 observer_cmd.json 文件，修改 'command' 字段并保存
======================================================================
```

### 2. 发送命令

在另一个终端或文本编辑器中打开 `observer_cmd.json` 文件，编辑并保存即可发送命令。

---

## 可用命令详解

### ⏸️ pause - 暂停仿真

**用途**: 暂停当前仿真，查看状态或准备干预

**命令格式**:
```json
{
  "command": "pause"
}
```

**效果**: 
- 仿真会在当前时间步结束后暂停
- 自动显示当前教师和学生状态
- 等待下一步指令

---

### ▶️ resume - 继续仿真

**用途**: 从暂停状态恢复仿真

**命令格式**:
```json
{
  "command": "resume"
}
```

**效果**: 仿真从暂停处继续运行

---

### 📊 status - 查看当前状态

**用途**: 实时查看教师和学生的当前状态（不暂停仿真）

**命令格式**:
```json
{
  "command": "status"
}
```

**显示信息**:
- ⏱️ 时间信息：当前仿真时间、事件类型
- 👨‍🏫 教师状态：课程进度、教学阶段、当前内容
- 👥 学生状态：注意力、当前行为、记忆节点数

**示例输出**:
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

### 🔧 intervene - 观察者干预（预留接口）

**用途**: 打断教学并调整教学计划

**命令格式**:
```json
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "学生注意力下降，建议增加互动环节",
    "parameters": {
      "add_discussion": true,
      "topic": "相反数的实际应用"
    }
  }
}
```

**intervention 字段说明**:

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `type` | string | 干预类型 | `adjust_plan`, `change_strategy`, `skip_section` |
| `instruction` | string | 自然语言指令 | "增加小组讨论环节" |
| `parameters` | object | 可选的详细参数 | 见下方示例 |

**干预类型示例**:

#### 1️⃣ 调整教学计划 (adjust_plan)
```json
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "学生理解困难，增加例题讲解",
    "parameters": {
      "add_examples": 2,
      "difficulty": "basic"
    }
  }
}
```

#### 2️⃣ 改变教学策略 (change_strategy)
```json
{
  "command": "intervene",
  "intervention": {
    "type": "change_strategy",
    "instruction": "改用启发式教学",
    "parameters": {
      "strategy": "inquiry_based"
    }
  }
}
```

#### 3️⃣ 跳过章节 (skip_section)
```json
{
  "command": "intervene",
  "intervention": {
    "type": "skip_section",
    "instruction": "跳过当前小节，直接讲下一节",
    "parameters": {
      "skip_to": 5
    }
  }
}
```

**当前状态**: 
- ⚠️ 接口已预留，但具体功能尚未实现
- 📍 实现位置: `teacher/teacher.py` 中的 `handle_observer_intervention()` 方法
- 🔨 后续会根据需求完善

---

### 🛑 exit - 退出仿真

**用途**: 优雅地终止仿真

**命令格式**:
```json
{
  "command": "exit"
}
```

**效果**: 
- 立即停止仿真循环
- 保存当前状态
- 清理资源

---

## 典型使用场景

### 场景 1: 观察学生注意力变化

```bash
# 1. 启动仿真
python run.py

# 2. 随时查看状态
# 编辑 observer_cmd.json:
{"command": "status"}

# 3. 发现问题后暂停
{"command": "pause"}

# 4. 分析情况后继续
{"command": "resume"}
```

### 场景 2: 实时调整教学策略

```bash
# 1. 仿真运行中，发现学生困惑

# 2. 暂停查看详情
{"command": "pause"}

# 3. 发起干预（预留功能）
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "增加互动问答环节"
  }
}

# 4. 继续观察效果
{"command": "resume"}
```

---

## 技术细节

### 文件监听机制

- 每 0.5 秒检查一次 `observer_cmd.json` 文件修改时间
- 检测到修改后立即读取并执行命令
- 执行后自动清空 `command` 字段，避免重复触发

### 暂停机制

- **非阻塞**: 暂停不会卡死主循环
- **安全**: 在当前时间步完成后才暂停
- **状态保持**: 暂停期间可以多次查看状态

### 预留接口设计

干预功能的入口在 `Teacher.handle_observer_intervention()` 方法中：

```python
async def handle_observer_intervention(self, intervention_data: dict):
    """
    处理观察者干预，调整教学计划
    
    TODO:
    - 使用 LLM 理解自然语言指令
    - 根据 type 调用不同的处理方法
    - 修改 self.plan, self.teaching_strategy 等
    - 返回调整结果
    """
    # 待实现...
```

---

## 常见问题

### Q: 命令没有响应？

**A**: 检查以下几点：
1. 确保 `observer_cmd.json` 文件格式正确（有效的 JSON）
2. 确认 `command` 字段拼写正确
3. 查看终端是否有错误提示

### Q: 如何同时查看日志和发送命令？

**A**: 推荐使用以下方式：
- **终端 1**: 运行 `python run.py`
- **终端 2**: 使用 `tail -f logs/*/1/output.txt` 查看日志
- **VSCode/编辑器**: 打开 `observer_cmd.json` 发送命令

### Q: intervene 命令为什么不生效？

**A**: 这是正常的，因为：
- 该功能是**预留接口**，具体逻辑还未实现
- 当前只会打印干预内容，不会真正修改教学计划
- 后续需要在 `teacher.handle_observer_intervention()` 中实现

---

## 扩展开发

如果你想实现 `intervene` 功能，参考以下步骤：

### 1. 编辑 `teacher/teacher.py`

在 `handle_observer_intervention()` 方法中添加逻辑：

```python
async def handle_observer_intervention(self, intervention_data: dict):
    intervention_type = intervention_data.get("type", "")
    
    if intervention_type == "adjust_plan":
        # 调整教学计划
        instruction = intervention_data.get("instruction", "")
        
        # 使用 LLM 解析指令
        prompt = f"根据以下观察者建议调整教学计划：{instruction}"
        new_plan = call_LLM_sync(prompt, ...)
        
        # 更新计划
        self.plan = parse_plan(new_plan)
        return "教学计划已调整"
    
    # 其他类型...
```

### 2. 测试

```json
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "你的自定义指令"
  }
}
```

---

## 注意事项

⚠️ **重要提醒**:
- 命令文件会在执行后自动清空 `command` 字段
- 暂停期间仿真时间不会推进
- `exit` 命令会立即终止仿真，无法恢复
- 频繁暂停/继续可能影响仿真的连贯性

---

## 反馈与贡献

如果你有任何建议或发现问题，欢迎提交 Issue 或 Pull Request！

