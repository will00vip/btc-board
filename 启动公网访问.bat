@echo off
chcp 65001 >nul
title BTC看板 - 公网访问
color 0A

echo ============================================
echo   BTC 看板公网穿透启动器
echo ============================================
echo.

REM 检查 cloudflared 是否存在
if not exist "D:\btc_monitor\cloudflared.exe" (
    echo [1/2] 正在下载 cloudflared...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'D:\btc_monitor\cloudflared.exe'"
    if errorlevel 1 (
        echo 下载失败，请手动下载：
        echo https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
        echo 放到 D:\btc_monitor\cloudflared.exe
        pause
        exit
    )
    echo 下载完成！
)

echo [2/2] 正在创建公网通道...
echo.
echo ★ 启动后会显示一个 https://xxxx.trycloudflare.com 链接
echo ★ 手机浏览器打开该链接即可访问看板
echo ★ 关闭此窗口则断开公网访问
echo.
echo ============================================
echo.

D:\btc_monitor\cloudflared.exe tunnel --url http://localhost:8899

pause
