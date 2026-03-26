import requests
from datetime import datetime, timezone, timedelta

TZ8 = timezone(timedelta(hours=8))

def get_klines(symbol='BTCUSDT', interval='15m', limit=25):
    url = 'https://data-api.binance.vision/api/v3/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    result = []
    for k in data:
        result.append({
            'ts': datetime.fromtimestamp(k[0]/1000, tz=TZ8),
            'open': float(k[1]),
            'high': float(k[2]),
            'low':  float(k[3]),
            'close':float(k[4]),
            'vol':  float(k[5]),
        })
    return result

def ema_series(prices, n):
    k_factor = 2/(n+1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(p*k_factor + result[-1]*(1-k_factor))
    return result

klines = get_klines(limit=25)
now = datetime.now(tz=TZ8)

print(f"当前时间: {now.strftime('%H:%M')}  当前小时: {now.hour}")
print(f"凌晨过滤(0~6点): {'是，不推送' if 0 <= now.hour < 6 else '否，正常扫描'}")
print()

pin_k = klines[-2]
confirm_k = klines[-1]
prev5 = klines[-7:-2]

o = pin_k['open']
h = pin_k['high']
l = pin_k['low']
c = pin_k['close']
v = pin_k['vol']

body = abs(c - o)
lower_shadow = min(o, c) - l
upper_shadow = h - max(o, c)
kline_range = h - l
mid = l + kline_range / 2

print(f"==== 插针候选K线 ({pin_k['ts'].strftime('%H:%M')}) ====")
print(f"O={o:.1f} H={h:.1f} L={l:.1f} C={c:.1f} V={v:.2f}")
print(f"实体大小: {body:.1f}  下影线: {lower_shadow:.1f}  上影线: {upper_shadow:.1f}")
print(f"下影/实体比: {lower_shadow/body:.2f} (需>=1.5)" if body > 0 else "实体=0，无法计算")
print(f"收盘位置: {c:.1f}  K线中点: {mid:.1f}  {'收盘在上半段✅' if c > mid else '收盘在下半段❌'}")
cond1 = body > 0 and lower_shadow >= body * 1.5 and c > mid
print(f"条件1-下影插针: {'✅满足' if cond1 else '❌不满足'}")
print()

print(f"==== 确认K线 ({confirm_k['ts'].strftime('%H:%M')}) ====")
print(f"O={confirm_k['open']:.1f} H={confirm_k['high']:.1f} L={confirm_k['low']:.1f} C={confirm_k['close']:.1f}")
print(f"最低价>{l:.1f}(插针低点): {'✅' if confirm_k['low'] > l else '❌'}")
print(f"收盘上涨: {'✅' if confirm_k['close'] > confirm_k['open'] else '❌'}")
cond2 = confirm_k['low'] > l and confirm_k['close'] > confirm_k['open']
print(f"条件2-低点抬高+收涨: {'✅满足' if cond2 else '❌不满足'}")
print()

avg_vol = sum(k['vol'] for k in prev5) / len(prev5) if prev5 else 0
print(f"==== 成交量 ====")
print(f"插针K线量: {v:.2f}  前5根均量: {avg_vol:.2f}  比值: {v/avg_vol:.2f}(需>=1.3)" if avg_vol > 0 else "无法计算")
cond3 = avg_vol > 0 and v >= avg_vol * 1.3
print(f"条件3-放量: {'✅满足' if cond3 else '❌不满足'}")
print()

closes = [k['close'] for k in klines]
ema12 = ema_series(closes, 12)
ema26 = ema_series(closes, 26)
dif = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
dea = ema_series(dif, 9)
hist = [2*(d - de) for d, de in zip(dif, dea)]

print(f"==== MACD ====")
print(f"DIF[-3]={dif[-3]:.2f} DIF[-2]={dif[-2]:.2f}")
print(f"DEA[-3]={dea[-3]:.2f} DEA[-2]={dea[-2]:.2f}")
print(f"HIST[-3]={hist[-3]:.2f} HIST[-2]={hist[-2]:.2f}")
macd_no_new_low = hist[-2] > hist[-3]
macd_golden = dif[-3] < dea[-3] and dif[-2] >= dea[-2]
print(f"柱状图不创新低: {'✅' if macd_no_new_low else '❌'}  金叉: {'✅' if macd_golden else '❌'}")
cond4 = macd_no_new_low or macd_golden
print(f"条件4-MACD: {'✅满足' if cond4 else '❌不满足'}")
print()

klines_4h = get_klines(symbol='BTCUSDT', interval='1h', limit=5)
price_4h_ago = klines_4h[0]['close']
price_now = confirm_k['close']
drop_pct = (price_now - price_4h_ago) / price_4h_ago * 100
print(f"==== 4小时跌幅过滤 ====")
print(f"4小时前价格: {price_4h_ago:.1f}  当前: {price_now:.1f}  涨跌: {drop_pct:.2f}%")
print(f"跌幅超8%过滤: {'是，不推送' if drop_pct < -8 else '否，正常'}")
print()

all_ok = cond1 and cond2 and cond3 and cond4 and drop_pct >= -8
print(f"==== 总结 ====")
print(f"条件1: {'✅' if cond1 else '❌'}  条件2: {'✅' if cond2 else '❌'}  条件3: {'✅' if cond3 else '❌'}  条件4: {'✅' if cond4 else '❌'}")
print(f"结论: {'🔔 应该推送！' if all_ok else '📭 无信号，差的条件见上'}")
