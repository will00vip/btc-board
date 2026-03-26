@echo off
chcp 65001 >nul
title BTC看板服务 - 手机访问
color 0B

echo ============================================
echo   BTC 看板HTTP服务（局域网+手机访问）
echo ============================================
echo.
echo 看板地址（局域网）：
echo   http://192.168.61.36:8899
echo.
echo 手机和电脑连同一个WiFi，直接用手机浏览器打开上面的地址
echo 然后点浏览器菜单 → "添加到桌面" 即可安装为App
echo.
echo 如需公网访问，另外双击"启动公网访问.bat"
echo.
echo ============================================
echo 服务启动中，关闭此窗口则停止...
echo.

cd /d D:\btc_monitor
python -m http.server 8899 --bind 0.0.0.0

pause
