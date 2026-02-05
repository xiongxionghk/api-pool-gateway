#!/bin/bash
# start.sh - 一键启动 API Pool Gateway (本地模式)

# 获取脚本所在目录
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 1. 检查 screen 是否安装
if ! command -v screen &> /dev/null; then
    echo "❌ 错误: 未找到 screen 命令。请先安装 screen。"
    exit 1
fi

# 2. 检查端口占用
PORT=8899
PID=$(lsof -t -i :$PORT)
if [ -n "$PID" ]; then
    echo "⚠️  端口 $PORT 被进程 $PID 占用，正在清理..."
    kill -9 $PID
    sleep 1
fi

# 3. 检查依赖 (简单检查)
if [ ! -d "backend/venv" ] && [ ! -d "venv" ]; then
    echo "ℹ️  提示: 如果缺少依赖，请运行: pip3 install -r backend/requirements.txt"
fi

# 4. 启动 screen 会话
echo "🚀 正在启动 API Pool Gateway..."
# 使用 -dmS 后台启动 screen 会话
screen -dmS api-gateway bash -c "cd backend && python3 main.py; exec bash"

# 5. 等待服务启动
echo "⏳ 等待服务启动..."
sleep 3
if lsof -i :$PORT > /dev/null; then
    echo "✅ 服务启动成功！"
    echo ""
    echo "🌐 访问地址: http://127.0.0.1:$PORT"
    echo "📄 接口文档: http://127.0.0.1:$PORT/docs"
    echo ""
    echo "🔧 运维命令:"
    echo "   - 查看日志/控制台: screen -r api-gateway"
    echo "     (退出查看请按 Ctrl+A, 然后按 D)"
    echo "   - 停止服务: lsof -t -i :$PORT | xargs kill -9"
else
    echo "❌ 服务启动可能失败，请使用 'screen -r api-gateway' 查看报错。"
fi
