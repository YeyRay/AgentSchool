# 🧪 观察者功能测试指南

[English](./TESTING_GUIDE.md)

## 准备工作

### 1. 设置环境变量

你需要设置以下环境变量：

```bash
# 必需：设置 DeepSeek API Key
export SCHOOLAGENT_API_KEY="sk-xxxxxxxxxxxxxxxx"

# 可选：设置本地 Embedding 模型路径
export BGE_MODEL="/mnt/shared-storage-user/zhangbo1/models/bge-small-zh-v1.5"

# 或者使用 bge-large-zh（更准确但更慢）
# export BGE_MODEL="/mnt/shared-storage-user/zhangbo1/models/bge-large-zh"
```

### 2. 验证模型路径

```bash
# 检查模型文件是否存在
ls -lh /mnt/shared-storage-user/zhangbo1/models/bge-small-zh-v1.5/

# 如果没有，可以不设置 BGE_MODEL，程序会自动从 Hugging Face 下载
```

---

## 🚀 快速测试（方法一：使用脚本）

### 步骤 1: 编辑测试脚本

```bash
cd /mnt/shared-storage-user/zhangbo1/AgentSchool-10-30/AgentSchool

# 编辑 test_observer.sh，替换你的 API Key
nano test_observer.sh
# 找到这一行: export SCHOOLAGENT_API_KEY="your_api_key_here"
# 替换为你的实际 API Key
```

### 步骤 2: 运行仿真

```bash
./test_observer.sh
```

### 步骤 3: 在另一个终端发送命令

**新开一个终端窗口**，然后：

```bash
cd /mnt/shared-storage-user/zhangbo1/AgentSchool-10-30/AgentSchool

# 方法 A: 使用快捷脚本
./send_command.sh pause     # 暂停
./send_command.sh status    # 查看状态
./send_command.sh resume    # 继续
./send_command.sh exit      # 退出

# 方法 B: 直接编辑文件
nano observer_cmd.json
# 修改 "command" 字段，保存即可
```

---

## 📝 手动测试（方法二：手动设置）

### 终端 1: 启动仿真

```bash
cd /mnt/shared-storage-user/zhangbo1/AgentSchool-10-30/AgentSchool

# 设置环境变量
export SCHOOLAGENT_API_KEY="sk-xxxxxxxxxxxxxxxx"
export BGE_MODEL="/mnt/shared-storage-user/zhangbo1/models/bge-small-zh-v1.5"

# 运行
python run.py
```

你会看到类似输出：

```
======================================================================
📝 [观察者模式] 已启动
======================================================================
命令文件: /mnt/shared-storage-user/zhangbo1/AgentSchool-10-30/AgentSchool/observer_cmd.json

可用命令:
  • pause     - 暂停仿真
  • resume    - 继续仿真
  • status    - 查看当前状态
  • intervene - 打断并调整教学计划（预留接口）
  • exit      - 退出仿真
======================================================================

===== 教学场景模拟开始 =====
...
```

### 终端 2: 发送命令

**方式 1: 使用脚本**

```bash
cd /mnt/shared-storage-user/zhangbo1/AgentSchool-10-30/AgentSchool
./send_command.sh pause
```

**方式 2: 手动编辑 JSON**

```bash
cd /mnt/shared-storage-user/zhangbo1/AgentSchool-10-30/AgentSchool

# 使用你喜欢的编辑器打开
nano observer_cmd.json
# 或
vim observer_cmd.json
# 或在 VSCode 中打开
```

编辑内容为：

```json
{
  "command": "pause"
}
```

保存后，终端 1 会立即响应！

---

## ✅ 测试清单

### 基础功能测试

1. **测试 pause 命令**
```json
{"command": "pause"}
```
期望结果：
- ✅ 仿真暂停
- ✅ 显示当前状态
- ✅ 提示如何继续

2. **测试 status 命令**（仿真运行中）
```json
{"command": "status"}
```
期望结果：
- ✅ 显示时间、教师状态、学生状态
- ✅ 仿真不暂停，继续运行

3. **测试 resume 命令**（暂停后）
```json
{"command": "resume"}
```
期望结果：
- ✅ 仿真继续运行
- ✅ 时间从暂停处继续

4. **测试 exit 命令**
```json
{"command": "exit"}
```
期望结果：
- ✅ 仿真优雅退出
- ✅ 保存当前状态

### 干预功能测试（预留接口）

5. **测试 intervene 命令**
```json
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "学生注意力下降，建议增加互动环节"
  }
}
```
期望结果：
- ✅ 仿真暂停
- ✅ 显示干预内容
- ✅ 调用 `teacher.handle_observer_intervention()`
- ⚠️  显示"功能待实现"提示（正常）

### 异常处理测试

6. **测试无效 JSON**
```
这不是有效的JSON
```
期望结果：
- ✅ 不崩溃
- ✅ 忽略无效命令

7. **测试未知命令**
```json
{"command": "unknown"}
```
期望结果：
- ✅ 忽略未知命令

8. **测试快速连续命令**

快速执行：
```bash
./send_command.sh pause
./send_command.sh status
./send_command.sh resume
```

期望结果：
- ✅ 所有命令都被正确处理

---

## 📊 预期输出示例

### pause 命令的输出

```
======================================================================
📝 [观察者] 收到命令: pause
======================================================================
⏸️  仿真将在当前轮次结束后暂停...

======================================================================
⏸️  [观察者] 仿真已暂停
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

======================================================================

💡 提示: 编辑 observer_cmd.json 文件，设置 'command': 'resume' 以继续
         或设置 'command': 'status' 查看最新状态
======================================================================
```

### status 命令的输出

```
======================================================================
📝 [观察者] 收到命令: status
======================================================================

📊 当前仿真状态
======================================================================
... (状态信息) ...
```

### intervene 命令的输出

```
======================================================================
📝 [观察者] 收到命令: intervene
======================================================================

======================================================================
🔧 [观察者干预] 正在处理...
======================================================================
干预内容: {
  "type": "adjust_plan",
  "instruction": "学生注意力下降，建议增加互动环节"
}

[Teacher.handle_observer_intervention] 收到观察者干预
  类型: adjust_plan
  指令: 学生注意力下降，建议增加互动环节

🤖 教师响应: ⚠️  观察者干预接口已调用，但具体功能尚未实现
======================================================================
```

---

## 🐛 常见问题排查

### 问题 1: 提示 "SCHOOLAGENT_API_KEY 环境变量未设置"

**解决方案**:
```bash
export SCHOOLAGENT_API_KEY="你的API密钥"
```

### 问题 2: 模型加载失败

**解决方案 A** - 使用本地模型:
```bash
# 确保路径正确
ls /mnt/shared-storage-user/zhangbo1/models/bge-small-zh-v1.5/
export BGE_MODEL="/mnt/shared-storage-user/zhangbo1/models/bge-small-zh-v1.5"
```

**解决方案 B** - 使用在线模型（需要网络）:
```bash
# 不设置 BGE_MODEL，让程序自动下载
unset BGE_MODEL
```

### 问题 3: 命令没有响应

**检查清单**:
- ✅ JSON 格式是否正确？
- ✅ 文件是否保存？
- ✅ `observer_cmd.json` 是否在正确的目录？

**调试方法**:
```bash
# 查看命令文件内容
cat observer_cmd.json

# 验证 JSON 格式
python -m json.tool observer_cmd.json

# 查看文件修改时间
ls -l observer_cmd.json
```

### 问题 4: 仿真启动后立即退出

**可能原因**: 配置文件缺失或格式错误

**检查**:
```bash
# 检查必要的配置文件
ls -l config/teacher.json
ls -l config/schedule.json
ls -l config/student/
```

---

## 📹 测试录屏建议

为了更好地演示，建议录屏时：

1. **分屏显示**
   - 左侧：运行仿真的终端
   - 右侧：编辑命令文件的编辑器

2. **测试顺序**
   1. 启动仿真
   2. 等待几秒让仿真运行
   3. 发送 `pause` 命令
   4. 观察暂停效果和状态显示
   5. 发送 `status` 命令
   6. 发送 `resume` 命令
   7. 发送 `intervene` 命令（展示预留接口）
   8. 发送 `exit` 命令

---

## 📝 测试报告模板

```markdown
## 观察者功能测试报告

**测试时间**: YYYY-MM-DD HH:MM
**测试环境**: 
- Python 版本: 
- API Key: 已设置
- BGE 模型: 

### 测试结果

| 功能 | 测试结果 | 备注 |
|------|---------|------|
| pause 命令 | ✅/❌ | |
| resume 命令 | ✅/❌ | |
| status 命令 | ✅/❌ | |
| exit 命令 | ✅/❌ | |
| intervene 命令 | ✅/❌ | 预留接口 |
| 异常处理 | ✅/❌ | |

### 发现的问题

1. 

### 建议

1. 
```

---

需要帮助吗？请查看 [OBSERVER_GUIDE_ZH.md](./OBSERVER_GUIDE_ZH.md)（或 [英文版 OBSERVER_GUIDE.md](./OBSERVER_GUIDE.md)）获取更多详细信息！

