# -*- coding: utf-8 -*-
import sys, io, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datetime import datetime, timezone, timedelta

TZ8 = timezone(timedelta(hours=8))

def get_klines(symbol='BTCUSDT', interval='15m', limit=25):
    url = 'https://data-api.binance.vision/api/v3/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()
    result = []
    for k in data:
        result.append({
            'ts': datetime.fromtimestamp(k[0]/1000, tz=TZ8),
            'open': float(k[1]), 'high': float(k[2]),
            'low': float(k[3]), 'close': float(k[4]), 'vol': float(k[5]),
        })
    return result

def ema_series(prices, n):
    kf = 2/(n+1)
    r = [prices[0]]
    for p in prices[1:]:
        r.append(p*kf + r[-1]*(1-kf))
    return r

klines = get_klines(limit=25)
now = datetime.now(tz=TZ8)
print(f"当前时间: {now.strftime('%H:%M')}")

pin_k   = klines[-2]
confirm_k = klines[-1]
prev5   = klines[-7:-2]

o = pin_k['open']; h = pin_k['high']
l = pin_k['low'];  c = pin_k['close']; v = pin_k['vol']

body         = abs(c - o)
lower_shadow = min(o, c) - l
kline_range  = h - l
mid          = l + kline_range / 2

print(f"\n--- 插针候选K线 {pin_k['ts'].strftime('%H:%M')} ---")
print(f"  O={o:.1f}  H={h:.1f}  L={l:.1f}  C={c:.1f}  V={v:.1f}")
if body > 0:
    print(f"  实体={body:.1f}  下影={lower_shadow:.1f}  下影/实体比={lower_shadow/body:.2f} (需>=1.5)")
else:
    print("  实体=0，十字星形态")
print(f"  收盘{c:.1f}  K线中点{mid:.1f}  收盘在上半段: {c > mid}")
cond1 = body > 0 and lower_shadow >= body * 1.5 and c > mid
print(f"  [条件1-下影插针]: {'满足' if cond1 else '不满足'}")

print(f"\n--- 确认K线 {confirm_k['ts'].strftime('%H:%M')} ---")
print(f"  L={confirm_k['low']:.1f}  C={confirm_k['close']:.1f}  O={confirm_k['open']:.1f}")
print(f"  低点高于插针低点({l:.1f}): {confirm_k['low'] > l}")
print(f"  收盘上涨: {confirm_k['close'] > confirm_k['open']}")
cond2 = confirm_k['low'] > l and confirm_k['close'] > confirm_k['open']
print(f"  [条件2-确认]: {'满足' if cond2 else '不满足'}")

avg_vol = sum(k['vol'] for k in prev5) / len(prev5) if prev5 else 0
print(f"\n--- 成交量 ---")
if avg_vol > 0:
    print(f"  插针量={v:.1f}  前5均量={avg_vol:.1f}  比值={v/avg_vol:.2f} (需>=1.3)")
cond3 = avg_vol > 0 and v >= avg_vol * 1.3
print(f"  [条件3-放量]: {'满足' if cond3 else '不满足'}")

closes = [k['close'] for k in klines]
ema12  = ema_series(closes, 12)
ema26  = ema_series(closes, 26)
dif    = [a - b for a, b in zip(ema12, ema26)]
dea    = ema_series(dif, 9)
hist   = [2*(d - de) for d, de in zip(dif, dea)]
print(f"\n--- MACD ---")
print(f"  HIST[-3]={hist[-3]:.2f}  HIST[-2]={hist[-2]:.2f}  (柱不创新低: {hist[-2] > hist[-3]})")
print(f"  DIF[-3]={dif[-3]:.2f}  DEA[-3]={dea[-3]:.2f}  => DIF金叉: {dif[-3] < dea[-3] and dif[-2] >= dea[-2]}")
cond4 = hist[-2] > hist[-3] or (dif[-3] < dea[-3] and dif[-2] >= dea[-2])
print(f"  [条件4-MACD]: {'满足' if cond4 else '不满足'}")

kl4h = get_klines(interval='1h', limit=5)
drop = (confirm_k['close'] - kl4h[0]['close']) / kl4h[0]['close'] * 100
print(f"\n--- 4小时跌幅过滤 ---")
print(f"  4h前={kl4h[0]['close']:.1f}  现在={confirm_k['close']:.1f}  涨跌={drop:.2f}%  超8%触发过滤: {drop < -8}")

print(f"\n========== 汇总 ==========")
print(f"  条件1(插针): {'OK' if cond1 else 'FAIL'}")
print(f"  条件2(确认): {'OK' if cond2 else 'FAIL'}")
print(f"  条件3(放量): {'OK' if cond3 else 'FAIL'}")
print(f"  条件4(MACD): {'OK' if cond4 else 'FAIL'}")
print(f"  4h跌幅过滤: {'触发(不推)' if drop < -8 else '未触发'}")
all_ok = cond1 and cond2 and cond3 and cond4 and drop >= -8
print(f"\n  结论: {'>>> 应该推送信号！' if all_ok else '无信号 —— 差的条件见上'}")
