# -*- coding: utf-8 -*-
"""
BTC 15分钟插针信号扫描 v2 — 分层推送
 强信号：插针 + 放量 + 确认K + MACD  → 🔥 立刻推
 普通信号：插针 + 放量（确认K可选）   → ⚠️ 提醒推
 MACD叉口：单独一路推（macd_watcher已有，本脚本不重复）
数据源：火币HTX → 币安镜像 → OKX  自动切换
"""
import sys, io, os, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datetime import datetime, timezone, timedelta

TZ8 = timezone(timedelta(hours=8))

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from config import SERVERCHAN_KEY, PUSHDEER_KEY, HTX_ACCESS_KEY, HTX_SECRET_KEY


# ══════════════════════════════════════════════════════════
# 数据源：三源自动切换
# ══════════════════════════════════════════════════════════

def _get_klines_binance(interval='15m', limit=30):
    url = 'https://data-api.binance.vision/api/v3/klines'
    resp = requests.get(url, params={'symbol': 'BTCUSDT', 'interval': interval, 'limit': limit}, timeout=10)
    resp.raise_for_status()
    result = []
    for k in resp.json():
        result.append({'ts': datetime.fromtimestamp(k[0]/1000, tz=TZ8),
                        'open': float(k[1]), 'high': float(k[2]),
                        'low':  float(k[3]), 'close': float(k[4]), 'vol': float(k[5])})
    return result


def _get_klines_htx(interval='15m', limit=30):
    _map = {'1m':'1min','3m':'5min','5m':'5min','15m':'15min','30m':'30min',
            '1h':'60min','4h':'4hour','1d':'1day','1w':'1week'}
    period = _map.get(interval, '15min')
    url = 'https://api.huobi.pro/market/history/kline'
    headers = {'AccessKeyId': HTX_ACCESS_KEY} if HTX_ACCESS_KEY else {}
    resp = requests.get(url, params={'symbol': 'btcusdt', 'period': period, 'size': limit},
                        headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get('status') != 'ok':
        raise ValueError(f"HTX返回异常: {data.get('err-msg','unknown')}")
    result = []
    for k in reversed(data['data']):
        result.append({'ts': datetime.fromtimestamp(k['id'], tz=TZ8),
                        'open': float(k['open']), 'high': float(k['high']),
                        'low':  float(k['low']),  'close': float(k['close']), 'vol': float(k['vol'])})
    return result


def _get_klines_okx(interval='15m', limit=30):
    _map = {'1m':'1m','3m':'3m','5m':'5m','15m':'15m','30m':'30m',
            '1h':'1H','4h':'4H','1d':'1D','1w':'1W'}
    bar = _map.get(interval, '15m')
    url = 'https://www.okx.com/api/v5/market/candles'
    resp = requests.get(url, params={'instId': 'BTC-USDT', 'bar': bar, 'limit': limit}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get('code') != '0':
        raise ValueError(f"OKX返回异常: {data.get('msg','unknown')}")
    result = []
    for k in reversed(data['data']):
        result.append({'ts': datetime.fromtimestamp(int(k[0])/1000, tz=TZ8),
                        'open': float(k[1]), 'high': float(k[2]),
                        'low':  float(k[3]), 'close': float(k[4]), 'vol': float(k[5])})
    return result


def get_klines(interval='15m', limit=30):
    sources = [('火币HTX', _get_klines_htx), ('币安镜像', _get_klines_binance), ('OKX', _get_klines_okx)]
    last_err = None
    for name, fn in sources:
        try:
            data = fn(interval=interval, limit=limit)
            if data:
                print(f'[数据源] {name} ✅')
                return data
        except Exception as e:
            print(f'[数据源] {name} ❌ {e}')
            last_err = e
    raise RuntimeError(f'三个数据源全部失败：{last_err}')


# ══════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════

def ema_series(prices, n):
    kf = 2 / (n + 1)
    r = [prices[0]]
    for p in prices[1:]:
        r.append(p * kf + r[-1] * (1 - kf))
    return r


def calc_macd(closes):
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    dif   = [a - b for a, b in zip(ema12, ema26)]
    dea   = ema_series(dif, 9)
    hist  = [2 * (d - de) for d, de in zip(dif, dea)]
    return dif, dea, hist


def push(title, content):
    """双渠道推送：Server酱 + PushDeer"""
    ok_count = 0
    try:
        if SERVERCHAN_KEY and 'SendKey' not in SERVERCHAN_KEY:
            r = requests.post(f'https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send',
                              data={'title': title, 'desp': content}, timeout=10)
            print(f'[Server酱] {r.json().get("message","ok")} errno={r.json().get("data",{}).get("errno","?")}')
            ok_count += 1
    except Exception as e:
        print(f'[Server酱异常] {e}')

    try:
        if PUSHDEER_KEY and 'Key' not in PUSHDEER_KEY:
            # PushDeer API: text = 正文, type = text/markdown
            r = requests.post('https://api2.pushdeer.com/message/push',
                              data={'pushkey': PUSHDEER_KEY,
                                    'title':   title,
                                    'text':    content,          # ← 必填字段
                                    'type':    'text'}, timeout=10)
            resp_json = r.json()
            code = resp_json.get('code', '?')
            print(f'[PushDeer] code={code}')
            if code == 0:
                ok_count += 1
            else:
                print(f'[PushDeer错误] {resp_json}')
    except Exception as e:
        print(f'[PushDeer异常] {e}')

    if ok_count == 0:
        print('[推送] 两路均失败，请检查网络和Key配置')


# ══════════════════════════════════════════════════════════
# 主扫描逻辑（分层推送）
# ══════════════════════════════════════════════════════════

def check_signal():
    now = datetime.now(tz=TZ8)

    # 凌晨 0-5 点不推（欧美盘高活跃 22-02 不屏蔽，只过滤深夜静默时段）
    if 0 <= now.hour < 5:
        print(f"[{now.strftime('%H:%M')}] 凌晨静默时段，跳过扫描")
        return

    try:
        klines = get_klines(interval='15m', limit=40)
    except RuntimeError as e:
        print(f'❌ 数据获取失败：{e}')
        return

    if len(klines) < 10:
        print("数据不足，跳过")
        return

    # 当前已收盘K（倒数第2根），确认K（倒数第1根，可能未收）
    pin_k     = klines[-2]
    confirm_k = klines[-1]
    prev5     = klines[-7:-2]

    o, h, l, c, v = pin_k['open'], pin_k['high'], pin_k['low'], pin_k['close'], pin_k['vol']
    body         = abs(c - o)
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    kline_range  = h - l
    mid          = l + kline_range / 2

    # ── 成交量 ──
    avg_vol = sum(k['vol'] for k in prev5) / len(prev5) if prev5 else 0
    vol_ratio = round(v / avg_vol, 2) if avg_vol > 0 else 0
    vol_ok = vol_ratio >= 1.3
    vol_strong = vol_ratio >= 2.0   # 超级放量

    # ── MACD ──
    closes = [k['close'] for k in klines]
    dif, dea, hist = calc_macd(closes)
    macd_long_ok  = (len(hist) >= 3 and hist[-2] > hist[-3]) or \
                    (len(dif) >= 3 and dif[-3] < dea[-3] and dif[-2] >= dea[-2])
    macd_short_ok = (len(hist) >= 3 and hist[-2] < hist[-3]) or \
                    (len(dif) >= 3 and dif[-3] > dea[-3] and dif[-2] <= dea[-2])

    price_now = confirm_k['close']
    ts_str    = pin_k['ts'].strftime("%m月%d日 %H:%M")

    # ── 确认K辅助条件（宽松版，任满足其一即可）──
    long_confirm_strong = confirm_k['low'] > l and confirm_k['close'] > confirm_k['open']  # 严格版
    long_confirm_weak   = confirm_k['close'] > l * 1.001                                  # 宽松：价格离插针低点有距离
    short_confirm_strong = confirm_k['high'] < h and confirm_k['close'] < confirm_k['open']
    short_confirm_weak   = confirm_k['close'] < h * 0.999

    # ═════════════════════════════
    #  做多信号：下影插针
    # ═════════════════════════════
    long_pin = body > 0 and lower_shadow >= body * 1.5 and c > mid

    if long_pin and vol_ok:
        sl   = round(l * 0.9985, 1)        # 止损：插针低点下方0.15%
        risk = round(price_now - sl, 1)
        tp1  = round(price_now + risk * 1.0, 1)
        tp2  = round(price_now + risk * 1.5, 1)
        tp3  = round(price_now + risk * 2.5, 1)

        # 评分
        score = 0
        details = []
        details.append(f"✅ 下影插针 (下影/实体 = {round(lower_shadow/body,1)}x)")
        score += 3
        if vol_strong:
            details.append(f"✅ 超级放量 ({vol_ratio}x，强度极高)")
            score += 3
        else:
            details.append(f"✅ 成交量放大 ({vol_ratio}x)")
            score += 2
        if macd_long_ok:
            details.append(f"✅ MACD配合 (DIF={round(dif[-1],1)})")
            score += 2
        else:
            details.append(f"⚠️ MACD未配合 (DIF={round(dif[-1],1)}, DEA={round(dea[-1],1)})")
        if long_confirm_strong:
            details.append("✅ 确认K强（低点抬高+阳线）")
            score += 2
        elif long_confirm_weak:
            details.append("⚠️ 确认K弱（价格未跌回插针低点）")
            score += 1
        else:
            details.append("❌ 确认K未出现")

        # 强度标签 + 建议评级
        rr = round(risk * 1.5 / risk, 1) if risk > 0 else 0  # TP2盈亏比=1.5
        rr_str = f"1:{rr}" if rr > 0 else "--"
        if score >= 8:
            level   = "🔥🔥 超强信号"
            emoji   = "🚀"
            advice  = "强烈推荐！多项指标共振，可考虑开仓"
            stars   = "⭐⭐⭐⭐⭐"
        elif score >= 6:
            level   = "🔥 强信号"
            emoji   = "📈"
            advice  = "建议参与，注意控仓（≤2成）"
            stars   = "⭐⭐⭐⭐"
        else:
            level   = "⚠️ 普通信号"
            emoji   = "👀"
            advice  = "谨慎观察，等确认K再决定"
            stars   = "⭐⭐⭐"

        # 标题：一眼读懂方向/价格/评分
        title = f"🚀 BTC做多 {level} | {price_now:.0f} | {score}/10"
        msg = f"""🚀 BTC 做多信号  {level}
{stars}  评分 {score}/10  盈亏比 1.5:1
━━━━━━━━━━━━━━━━━━━━━━
⏰ {ts_str}
💵 当前价格：{price_now:.1f} USDT
📊 方向：做多 ▲（下影插针反转）

📍 信号明细：
{chr(10).join(details)}

💡 建议：{advice}

💰 交易计划（15分钟视角）：
  🔴 止损  {sl}  （亏 {round((price_now-sl)/price_now*100,2)}%）
  🟡 TP1   {tp1}  （盈 {round((tp1-price_now)/price_now*100,2)}%，保本离场）
  🟢 TP2   {tp2}  （盈 {round((tp2-price_now)/price_now*100,2)}%，主要目标）
  💎 TP3   {tp3}  （盈 {round((tp3-price_now)/price_now*100,2)}%，超额利润）

⚠️ 仓位建议：信号越强仓位越重，≤30%本金
   结合大趋势判断，顺势为王！"""
        print(msg)
        push(title, msg)
        return

    # ═════════════════════════════
    #  做空信号：上影插针
    # ═════════════════════════════
    short_pin = body > 0 and upper_shadow >= body * 1.5 and c < mid

    if short_pin and vol_ok:
        sl   = round(h * 1.0015, 1)
        risk = round(sl - price_now, 1)
        tp1  = round(price_now - risk * 1.0, 1)
        tp2  = round(price_now - risk * 1.5, 1)
        tp3  = round(price_now - risk * 2.5, 1)

        score = 0
        details = []
        details.append(f"✅ 上影插针 (上影/实体 = {round(upper_shadow/body,1)}x)")
        score += 3
        if vol_strong:
            details.append(f"✅ 超级放量 ({vol_ratio}x，强度极高)")
            score += 3
        else:
            details.append(f"✅ 成交量放大 ({vol_ratio}x)")
            score += 2
        if macd_short_ok:
            details.append(f"✅ MACD配合 (DIF={round(dif[-1],1)})")
            score += 2
        else:
            details.append(f"⚠️ MACD未配合 (DIF={round(dif[-1],1)}, DEA={round(dea[-1],1)})")
        if short_confirm_strong:
            details.append("✅ 确认K强（高点下降+阴线）")
            score += 2
        elif short_confirm_weak:
            details.append("⚠️ 确认K弱（价格未涨回插针高点）")
            score += 1
        else:
            details.append("❌ 确认K未出现")

        # 强度标签 + 建议评级
        if score >= 8:
            level   = "🔥🔥 超强信号"
            emoji   = "💥"
            advice  = "强烈推荐！多项指标共振，可考虑开仓"
            stars   = "⭐⭐⭐⭐⭐"
        elif score >= 6:
            level   = "🔥 强信号"
            emoji   = "📉"
            advice  = "建议参与，注意控仓（≤2成）"
            stars   = "⭐⭐⭐⭐"
        else:
            level   = "⚠️ 普通信号"
            emoji   = "👀"
            advice  = "谨慎观察，等确认K再决定"
            stars   = "⭐⭐⭐"

        # 标题：一眼读懂方向/价格/评分
        title = f"💥 BTC做空 {level} | {price_now:.0f} | {score}/10"
        msg = f"""💥 BTC 做空信号  {level}
{stars}  评分 {score}/10  盈亏比 1.5:1
━━━━━━━━━━━━━━━━━━━━━━
⏰ {ts_str}
💵 当前价格：{price_now:.1f} USDT
📊 方向：做空 ▼（上影插针反转）

📍 信号明细：
{chr(10).join(details)}

💡 建议：{advice}

💰 交易计划（15分钟视角）：
  🔴 止损  {sl}  （亏 {round((sl-price_now)/price_now*100,2)}%）
  🟡 TP1   {tp1}  （盈 {round((price_now-tp1)/price_now*100,2)}%，保本离场）
  🟢 TP2   {tp2}  （盈 {round((price_now-tp2)/price_now*100,2)}%，主要目标）
  💎 TP3   {tp3}  （盈 {round((price_now-tp3)/price_now*100,2)}%，超额利润）

⚠️ 仓位建议：信号越强仓位越重，≤30%本金
   结合大趋势判断，顺势为王！"""
        print(msg)
        push(title, msg)
        return

    print(f"[{now.strftime('%H:%M')}] 本次扫描无信号（做多:{long_pin} 做空:{short_pin} 放量:{vol_ok}），继续监控")


if __name__ == '__main__':
    check_signal()
