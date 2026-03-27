# -*- coding: utf-8 -*-
"""
BTC 15m 插针信号监控 - GitHub Actions 云端版
每15分钟由 Actions 调用，检测信号后推送到 Server酱 + PushDeer
"""
import urllib.request
import urllib.parse
import urllib.error
import json
import os
import time
from datetime import datetime, timezone, timedelta

TZ8 = timezone(timedelta(hours=8))

SERVERCHAN_KEY = os.environ.get('SERVERCHAN_KEY', '')
PUSHDEER_KEY   = os.environ.get('PUSHDEER_KEY', '')


# ── 工具 ─────────────────────────────────────────────────────────

def http_get(url, params=None, timeout=15):
    if params:
        qs = urllib.parse.urlencode(params)
        url = url + '?' + qs
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def http_post(url, data, timeout=10):
    body = urllib.parse.urlencode(data).encode()
    req  = urllib.request.Request(
        url, data=body,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0'
        }
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ── 数据源：币安镜像 ──────────────────────────────────────────────

def get_klines(interval='15m', limit=40):
    url = 'https://data-api.binance.vision/api/v3/klines'
    raw = http_get(url, {'symbol': 'BTCUSDT', 'interval': interval, 'limit': limit})
    result = []
    for k in raw:
        result.append({
            'ts':    datetime.fromtimestamp(k[0] / 1000, tz=TZ8),
            'open':  float(k[1]),
            'high':  float(k[2]),
            'low':   float(k[3]),
            'close': float(k[4]),
            'vol':   float(k[5]),
        })
    return result


# ── 指标 ─────────────────────────────────────────────────────────

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


def calc_rsi(closes, n=14):
    if len(closes) < n + 1:
        return 50
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[-n:]) / n
    al = sum(losses[-n:]) / n
    if al == 0:
        return 100
    rs = ag / al
    return round(100 - 100 / (1 + rs), 1)


def calc_kdj(klines, n=9):
    if len(klines) < n:
        return 50, 50, 50
    highs  = [k['high']  for k in klines[-n:]]
    lows   = [k['low']   for k in klines[-n:]]
    closes = [k['close'] for k in klines[-n:]]
    hh = max(highs)
    ll = min(lows)
    rsv = (closes[-1] - ll) / (hh - ll) * 100 if hh != ll else 50
    k_val = rsv * (1/3) + 50 * (2/3)
    d_val = k_val * (1/3) + 50 * (2/3)
    j_val = 3 * k_val - 2 * d_val
    return round(k_val, 1), round(d_val, 1), round(j_val, 1)


# ── 推送 ─────────────────────────────────────────────────────────

def push_serverchan(title, content):
    if not SERVERCHAN_KEY:
        return False
    try:
        r = http_post(
            'https://sctapi.ftqq.com/' + SERVERCHAN_KEY + '.send',
            {'title': title, 'desp': content}
        )
        errno = r.get('data', {}).get('errno', r.get('errno', '?'))
        print('[Server] errno=' + str(errno))
        return errno == 0
    except Exception as e:
        print('[Server error] ' + str(e))
        return False


def push_pushdeer(title, content):
    if not PUSHDEER_KEY:
        return False
    try:
        r = http_post(
            'https://api2.pushdeer.com/message/push',
            {'pushkey': PUSHDEER_KEY, 'text': title + '\n' + content, 'type': 'text'}
        )
        code = r.get('code', '?')
        print('[PushDeer] code=' + str(code))
        return code == 0
    except Exception as e:
        print('[PushDeer error] ' + str(e))
        return False


def push(title, content):
    ok1 = push_serverchan(title, content)
    ok2 = push_pushdeer(title, content)
    if not ok1 and not ok2:
        print('[push] both channels failed!')
    else:
        print('[push] ok sc=' + str(ok1) + ' pd=' + str(ok2))


# ── MACD 叉口 ────────────────────────────────────────────────────

def check_macd_cross(dif, dea, hist, price_now, ts_str):
    if len(dif) < 3:
        return

    golden = dif[-2] < dea[-2] and dif[-1] >= dea[-1]
    dead   = dif[-2] > dea[-2] and dif[-1] <= dea[-1]

    if not golden and not dead:
        return

    dist = abs(dif[-1] - dea[-1])
    strength_cn = '强' if dist > 100 else ('中' if dist > 30 else '弱')
    axis_pos = '零轴下方' if dif[-1] < 0 else '零轴上方'

    if golden:
        title = 'BTC MACD金叉 ' + axis_pos + ' | ' + str(int(price_now)) + 'U | ' + strength_cn
        msg = (
            'MACD 金叉 — 看多信号\n'
            '时间：' + ts_str + '\n'
            '价格：' + str(round(price_now, 1)) + ' USDT\n'
            'DIF：' + str(round(dif[-2], 1)) + ' → ' + str(round(dif[-1], 1)) + '\n'
            'DEA：' + str(round(dea[-2], 1)) + ' → ' + str(round(dea[-1], 1)) + '\n'
            'MACD柱：' + str(round(hist[-1], 1)) + '\n'
            '位置：' + axis_pos + ('（超卖区金叉，反转力强）' if dif[-1] < 0 else '（多头持续）') + '\n'
            '\n建议：关注下影插针，可考虑多单'
        )
    else:
        title = 'BTC MACD死叉 ' + axis_pos + ' | ' + str(int(price_now)) + 'U | ' + strength_cn
        msg = (
            'MACD 死叉 — 看空信号\n'
            '时间：' + ts_str + '\n'
            '价格：' + str(round(price_now, 1)) + ' USDT\n'
            'DIF：' + str(round(dif[-2], 1)) + ' → ' + str(round(dif[-1], 1)) + '\n'
            'DEA：' + str(round(dea[-2], 1)) + ' → ' + str(round(dea[-1], 1)) + '\n'
            'MACD柱：' + str(round(hist[-1], 1)) + '\n'
            '位置：' + axis_pos + ('（超买区死叉，反转力强）' if dif[-1] > 0 else '（空头持续）') + '\n'
            '\n建议：关注上影插针，可考虑空单'
        )

    push(title, msg)


# ── 主扫描 ────────────────────────────────────────────────────────

def check_signal():
    now  = datetime.now(tz=TZ8)
    hour = now.hour

    if 0 <= hour < 5:
        print('[' + now.strftime('%H:%M') + '] 静默时段(0-5点)，跳过')
        return

    print('[' + now.strftime('%H:%M') + '] 开始扫描...')

    try:
        klines = get_klines(interval='15m', limit=60)
        print('K线数量：' + str(len(klines)))
    except Exception as e:
        print('数据获取失败：' + str(e))
        return

    if len(klines) < 10:
        print('数据不足')
        return

    pin_k     = klines[-2]
    confirm_k = klines[-1]
    prev5     = klines[-7:-2]

    o = pin_k['open']
    h = pin_k['high']
    l = pin_k['low']
    c = pin_k['close']
    v = pin_k['vol']

    body         = abs(c - o)
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    mid          = l + (h - l) / 2

    avg_vol    = sum(k['vol'] for k in prev5) / len(prev5) if prev5 else 0
    vol_ratio  = round(v / avg_vol, 2) if avg_vol > 0 else 0
    vol_ok     = vol_ratio >= 1.3
    vol_strong = vol_ratio >= 2.0

    closes = [k['close'] for k in klines]
    dif, dea, hist = calc_macd(closes)
    rsi = calc_rsi(closes)
    k_val, d_val, j_val = calc_kdj(klines)

    macd_long_ok  = (len(hist) >= 3 and hist[-2] > hist[-3]) or \
                    (len(dif) >= 3 and dif[-3] < dea[-3] and dif[-2] >= dea[-2])
    macd_short_ok = (len(hist) >= 3 and hist[-2] < hist[-3]) or \
                    (len(dif) >= 3 and dif[-3] > dea[-3] and dif[-2] <= dea[-2])

    price_now = confirm_k['close']
    ts_str    = pin_k['ts'].strftime('%m-%d %H:%M')

    long_confirm_strong  = confirm_k['low'] > l and confirm_k['close'] > confirm_k['open']
    long_confirm_weak    = confirm_k['close'] > l * 1.001
    short_confirm_strong = confirm_k['high'] < h and confirm_k['close'] < confirm_k['open']
    short_confirm_weak   = confirm_k['close'] < h * 0.999

    # MA趋势
    ma20 = round(sum(closes[-20:]) / 20, 1) if len(closes) >= 20 else 0
    ma60 = round(sum(closes[-60:]) / 60, 1) if len(closes) >= 60 else 0
    trend = '多头' if price_now > ma20 > ma60 else ('空头' if price_now < ma20 < ma60 else '震荡')

    # ── 做多：下影插针 ─────────────────────────────────────────────
    long_pin = body > 0 and lower_shadow >= body * 1.5 and c > mid
    if long_pin and vol_ok:
        sl   = round(l * 0.9985, 1)
        risk = round(price_now - sl, 1)
        tp1  = round(price_now + risk * 1.0, 1)
        tp2  = round(price_now + risk * 1.5, 1)
        tp3  = round(price_now + risk * 2.5, 1)

        score = 0
        details = []
        details.append('下影插针（影/实=' + str(round(lower_shadow / body, 1)) + '倍）')
        score += 3
        if vol_strong:
            details.append('放量（' + str(vol_ratio) + 'x 超强放量）')
            score += 3
        else:
            details.append('放量（' + str(vol_ratio) + 'x）')
            score += 2
        if macd_long_ok:
            details.append('MACD看多（DIF=' + str(round(dif[-1], 1)) + '）')
            score += 2
        else:
            details.append('MACD中性')
        if rsi < 40:
            details.append('RSI超卖（' + str(rsi) + '）')
            score += 1
        if long_confirm_strong:
            details.append('确认K强（阳线收高）')
            score += 2
        elif long_confirm_weak:
            details.append('确认K弱')
            score += 1
        else:
            details.append('确认K待形成')

        if score >= 8:
            level = '超强信号'; stars = '★★★★★'; advice = '强烈建议参与，多指标共振'
        elif score >= 6:
            level = '强信号'; stars = '★★★★'; advice = '建议轻仓进场，注意止损'
        else:
            level = '普通信号'; stars = '★★★'; advice = '谨慎观察，等待进一步确认'

        if score >= 5:
            title = 'BTC做多 ' + ('🔥' if score >= 8 else '📈') + level + ' | ' + str(int(price_now)) + ' | ' + str(score) + '/10'
            msg = (
                'BTC 做多信号  ' + level + '\n'
                + stars + '  评分 ' + str(score) + '/10  盈亏比1.5:1\n'
                '————————————————\n'
                '时间：' + ts_str + '\n'
                '价格：' + str(round(price_now, 1)) + ' USDT\n'
                '方向：做多（下影插针反转）\n'
                '趋势：' + trend + '  MA20=' + str(ma20) + '  MA60=' + str(ma60) + '\n'
                'RSI：' + str(rsi) + '  KDJ-J：' + str(j_val) + '\n'
                '\n信号详情：\n' + '\n'.join(['· ' + d for d in details]) + '\n'
                '\n建议：' + advice + '\n'
                '\n交易计划：\n'
                '  止损  ' + str(sl) + '  (-' + str(round((price_now - sl) / price_now * 100, 2)) + '%)\n'
                '  TP1   ' + str(tp1) + '  (+' + str(round((tp1 - price_now) / price_now * 100, 2)) + '%)\n'
                '  TP2   ' + str(tp2) + '  (+' + str(round((tp2 - price_now) / price_now * 100, 2)) + '%)\n'
                '  TP3   ' + str(tp3) + '  (+' + str(round((tp3 - price_now) / price_now * 100, 2)) + '%)\n'
                '\n仓位建议：不超过总仓位30%'
            )
            print(msg)
            push(title, msg)
        else:
            print('做多评分' + str(score) + '<5，不推送')
        return

    # ── 做空：上影插针 ────────────────────────────────────────────
    short_pin = body > 0 and upper_shadow >= body * 1.5 and c < mid
    if short_pin and vol_ok:
        sl   = round(h * 1.0015, 1)
        risk = round(sl - price_now, 1)
        tp1  = round(price_now - risk * 1.0, 1)
        tp2  = round(price_now - risk * 1.5, 1)
        tp3  = round(price_now - risk * 2.5, 1)

        score = 0
        details = []
        details.append('上影插针（影/实=' + str(round(upper_shadow / body, 1)) + '倍）')
        score += 3
        if vol_strong:
            details.append('放量（' + str(vol_ratio) + 'x 超强放量）')
            score += 3
        else:
            details.append('放量（' + str(vol_ratio) + 'x）')
            score += 2
        if macd_short_ok:
            details.append('MACD看空（DIF=' + str(round(dif[-1], 1)) + '）')
            score += 2
        else:
            details.append('MACD中性')
        if rsi > 60:
            details.append('RSI超买（' + str(rsi) + '）')
            score += 1
        if short_confirm_strong:
            details.append('确认K强（阴线收低）')
            score += 2
        elif short_confirm_weak:
            details.append('确认K弱')
            score += 1
        else:
            details.append('确认K待形成')

        if score >= 8:
            level = '超强信号'; stars = '★★★★★'; advice = '强烈建议参与，多指标共振'
        elif score >= 6:
            level = '强信号'; stars = '★★★★'; advice = '建议轻仓做空，注意止损'
        else:
            level = '普通信号'; stars = '★★★'; advice = '谨慎观察，等待进一步确认'

        if score >= 5:
            title = 'BTC做空 ' + ('🔥' if score >= 8 else '📉') + level + ' | ' + str(int(price_now)) + ' | ' + str(score) + '/10'
            msg = (
                'BTC 做空信号  ' + level + '\n'
                + stars + '  评分 ' + str(score) + '/10  盈亏比1.5:1\n'
                '————————————————\n'
                '时间：' + ts_str + '\n'
                '价格：' + str(round(price_now, 1)) + ' USDT\n'
                '方向：做空（上影插针反转）\n'
                '趋势：' + trend + '  MA20=' + str(ma20) + '  MA60=' + str(ma60) + '\n'
                'RSI：' + str(rsi) + '  KDJ-J：' + str(j_val) + '\n'
                '\n信号详情：\n' + '\n'.join(['· ' + d for d in details]) + '\n'
                '\n建议：' + advice + '\n'
                '\n交易计划：\n'
                '  止损  ' + str(sl) + '  (+' + str(round((sl - price_now) / price_now * 100, 2)) + '%)\n'
                '  TP1   ' + str(tp1) + '  (-' + str(round((price_now - tp1) / price_now * 100, 2)) + '%)\n'
                '  TP2   ' + str(tp2) + '  (-' + str(round((price_now - tp2) / price_now * 100, 2)) + '%)\n'
                '  TP3   ' + str(tp3) + '  (-' + str(round((price_now - tp3) / price_now * 100, 2)) + '%)\n'
                '\n仓位建议：不超过总仓位30%'
            )
            print(msg)
            push(title, msg)
        else:
            print('做空评分' + str(score) + '<5，不推送')
        return

    # ── MACD叉口 ─────────────────────────────────────────────────
    check_macd_cross(dif, dea, hist, price_now, ts_str)

    print('[' + now.strftime('%H:%M') + '] 本次无信号 (做多:' + str(long_pin) +
          ' 做空:' + str(short_pin) + ' 放量:' + str(vol_ok) + ' 量比:' + str(vol_ratio) + ')')


if __name__ == '__main__':
    check_signal()
