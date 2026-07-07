#!/bin/bash
# 开启 Chrome 远程调试模式（你的标签页会恢复，不用担心）

echo "1/3 正在关闭 Chrome..."
osascript -e 'tell app "Google Chrome" to quit' 2>/dev/null

echo "2/3 等待完全关闭..."
until ! pgrep -f "Google Chrome" > /dev/null 2>&1; do
    sleep 1
done
sleep 1

echo "3/3 正在以调试模式启动 Chrome..."
nohup /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9222 \
    --restore-last-session \
    > /dev/null 2>&1 &

sleep 4

# 验证
if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then
    echo ""
    echo "✅ 成功！Chrome 已支持 X 搜索"
    echo "   调试端口: http://localhost:9222"
else
    echo "❌ 启动失败，请手动运行:"
    echo "   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222"
fi
