#!/bin/bash
# 快速发送观察者命令的脚本

COMMAND_FILE="observer_cmd.json"

# 显示用法
usage() {
    echo "用法: $0 <command> [options]"
    echo ""
    echo "可用命令:"
    echo "  pause       - 暂停仿真"
    echo "  resume      - 继续仿真"
    echo "  status      - 查看状态"
    echo "  exit        - 退出仿真"
    echo "  intervene   - 发起干预（需要额外参数）"
    echo "  rollback    - 回溯到第k轮: rollback <turn> [class]"
    echo ""
    echo "示例:"
    echo "  $0 pause"
    echo "  $0 resume"
    echo "  $0 status"
    echo "  $0 rollback 12            # 回到本节第12轮"
    echo "  $0 rollback 8 2           # 回到第2节课第8轮"
    echo ""
    exit 1
}

# 检查参数
if [ $# -lt 1 ]; then
    usage
fi

COMMAND=$1

# 根据命令生成 JSON
case "$COMMAND" in
    pause)
        cat > $COMMAND_FILE <<EOF
{
  "command": "pause"
}
EOF
        echo "✅ 已发送 pause 命令"
        ;;
    
    resume)
        cat > $COMMAND_FILE <<EOF
{
  "command": "resume"
}
EOF
        echo "✅ 已发送 resume 命令"
        ;;
    
    status)
        cat > $COMMAND_FILE <<EOF
{
  "command": "status"
}
EOF
        echo "✅ 已发送 status 命令"
        ;;
    
    exit)
        cat > $COMMAND_FILE <<EOF
{
  "command": "exit"
}
EOF
        echo "✅ 已发送 exit 命令"
        ;;
    
    intervene)
        INSTRUCTION="${2:-增加互动环节}"
        cat > $COMMAND_FILE <<EOF
{
  "command": "intervene",
  "intervention": {
    "type": "adjust_plan",
    "instruction": "$INSTRUCTION"
  }
}
EOF
        echo "✅ 已发送 intervene 命令: $INSTRUCTION"
        ;;

    rollback)
        TURN="$2"
        CLASS="$3"
        if [ -z "$TURN" ]; then
            echo "❌ 用法: $0 rollback <turn> [class]"
            exit 1
        fi
        case "$TURN" in
            ''|*[!0-9]*)
                echo "❌ turn 必须为正整数"
                exit 1
                ;;
        esac
        if [ -n "$CLASS" ]; then
            case "$CLASS" in
                *[!0-9]*)
                    echo "❌ class 必须为正整数"
                    exit 1
                    ;;
            esac
        fi
        if [ -n "$CLASS" ]; then
cat > $COMMAND_FILE <<EOF
{
  "command": "rollback",
  "rollback": { "turn": $TURN, "class": $CLASS }
}
EOF
        else
cat > $COMMAND_FILE <<EOF
{
  "command": "rollback",
  "rollback": { "turn": $TURN }
}
EOF
        fi
        echo "✅ 已发送 rollback 命令: turn=$TURN class=${CLASS:-当前课}"
        ;;
    
    *)
        echo "❌ 未知命令: $COMMAND"
        usage
        ;;
esac

echo ""
echo "命令内容:"
cat $COMMAND_FILE | python -m json.tool 2>/dev/null || cat $COMMAND_FILE

