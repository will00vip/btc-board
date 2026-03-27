import sys
sys.path.insert(0, '.')
from macd_watcher import detect_macd_cross, format_macd_message, get_macd_status_line
from data_fetcher import get_klines

print('=== 测试MACD模块加载 ===')
df = get_klines('btcusdt', '15min', limit=60)
if df.empty:
    print('[错误] 数据拉取失败')
else:
    price = df.iloc[-1]['close']
    print(f'K线数据: {len(df)}根, 最新价: {price:,.1f}')
    status = get_macd_status_line(df)
    print(f'MACD状态: {status}')

    # 模拟金叉场景测试格式化
    mock_cross = {
        'type': 'golden',
        'dif': -123.5,
        'dea': -145.2,
        'bar': 43.4,
        'prev_dif': -160.1,
        'prev_dea': -148.3,
        'strength': '中等',
        'axis_desc': '零轴下方金叉（超卖区反转，力度更强）',
        'time': '03月26日 20:15',
    }
    title, content = format_macd_message(mock_cross, price)
    print()
    print('=== 模拟金叉推送内容 ===')
    print(f'标题: {title}')
    print(content)

    print()
    print('=== 模拟死叉推送内容 ===')
    mock_dead = dict(mock_cross)
    mock_dead['type'] = 'dead'
    mock_dead['strength'] = '强势'
    mock_dead['axis_desc'] = '零轴上方死叉（超买区转弱，力度更强）'
    title2, content2 = format_macd_message(mock_dead, price)
    print(f'标题: {title2}')
    print(content2)

    print()
    print('=== 真实K线检测叉口 ===')
    real_cross = detect_macd_cross(df)
    if real_cross:
        print(f'发现叉口: {real_cross["type"]}  强度:{real_cross["strength"]}')
    else:
        print('当前无新叉口（正常，只有穿越那根K才触发）')
