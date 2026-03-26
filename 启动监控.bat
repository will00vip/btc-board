@echo off
chcp 65001 >nul
echo ============================================
echo   BTC插针放量反转监控系统
echo ============================================

:: 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit
)

:: 安装依赖
echo 正在检查依赖库...
pip install -r requirements.txt -q

:: 检查是否已配置Server酱Key
findstr /C:"你的Server酱SendKey填这里" config.py >nul
if not errorlevel 1 (
    echo.
    echo [提醒] 检测到你还没有配置微信推送Key！
    echo 请按以下步骤操作：
    echo   1. 打开浏览器访问: https://sct.ftqq.com/
    echo   2. 用微信扫码登录
    echo   3. 复制页面上的 SendKey
    echo   4. 用记事本打开 config.py
    echo   5. 将 SERVERCHAN_KEY = "你的Server酱SendKey填这里"
    echo      改为 SERVERCHAN_KEY = "你复制的Key"
    echo   6. 保存后重新双击本文件启动
    echo.
    pause
    exit
)

:: 启动监控
echo 启动监控程序...
echo.
python main.py
pause
