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


# ── 推送 ─────────────────────────────────────────────────────────

def push(title, content):
    ok = 0
    if SERVERCHAN_KEY:
        try:
            r = http_post(
                'https://sctapi.ftqq.com/' + SERVERCHAN_KEY + '.send',
                {'title': title, 'desp': content}
            )
            errno = r.get('data', {}).get('errno', '?')
            print('[Server] errno=' + str(errno))
            if errno == 0:
                ok += 1
        except Exception as e:
            print('[Server error] ' + str(e))

    if PUSHDEER_KEY:
        try:
            r = http_post(
                'https://api2.pushdeer.com/message/push',
                {'pushkey': PUSHDEER_KEY, 'title': title, 'text': content, 'type': 'text'}
            )
            code = r.get('code', '?')
            print('[PushDeer] code=' + str(code))
            if code == 0:
                ok += 1
        except Exception as e:
            print('[PushDeer error] ' + str(e))

    if ok == 0:
        print('[push] both failed')


# ── MACD 叉口 ────────────────────────────────────────────────────

def check_macd_cross(dif, dea, hist, price_now, ts_str):
    if len(dif) < 3:
        return

    golden = dif[-2] < dea[-2] and dif[-1] >= dea[-1]
    dead   = dif[-2] > dea[-2] and dif[-1] <= dea[-1]

    if not golden and not dead:
        return

    dist = abs(dif[-1] - dea[-1])
    strength = 'strong' if dist > 100 else ('mid' if dist > 30 else 'weak')
    strength_cn = {'strong': 'strong', 'mid': 'mid', 'weak': 'weak'}[strength]

    if golden:
        axis = 'below-zero golden (oversold reversal)' if dif[-1] < 0 else 'above-zero golden (bull continue)'
        title = 'BTC MACD Golden Cross | ' + str(int(price_now)) + 'U | ' + strength_cn
        msg = (
            'MACD Golden Cross - Bullish Signal\n'
            '--------------------\n'
            'Time: ' + ts_str + '\n'
            'Price: ' + str(round(price_now, 1)) + ' USDT\n'
            'DIF: ' + str(round(dif[-2], 1)) + ' -> ' + str(round(dif[-1], 1)) + '\n'
            'DEA: ' + str(round(dea[-2], 1)) + ' -> ' + str(round(dea[-1], 1)) + '\n'
            'MACD Bar: ' + str(round(hist[-1], 1)) + '\n'
            'Position: ' + axis + '\n'
            '\nSuggestion: Consider long, confirm with pin bar'
        )
    else:
        axis = 'above-zero dead (overbought reversal)' if dif[-1] > 0 else 'below-zero dead (bear continue)'
        title = 'BTC MACD Dead Cross | ' + str(int(price_now)) + 'U | ' + strength_cn
        msg = (
            'MACD Dead Cross - Bearish Signal\n'
            '--------------------\n'
            'Time: ' + ts_str + '\n'
            'Price: ' + str(round(price_now, 1)) + ' USDT\n'
            'DIF: ' + str(round(dif[-2], 1)) + ' -> ' + str(round(dif[-1], 1)) + '\n'
            'DEA: ' + str(round(dea[-2], 1)) + ' -> ' + str(round(dea[-1], 1)) + '\n'
            'MACD Bar: ' + str(round(hist[-1], 1)) + '\n'
            'Position: ' + axis + '\n'
            '\nSuggestion: Consider short, confirm with pin bar'
        )

    push(title, msg)


# ── 主扫描 ────────────────────────────────────────────────────────

def check_signal():
    now  = datetime.now(tz=TZ8)
    hour = now.hour

    if 0 <= hour < 5:
        print('[' + now.strftime('%H:%M') + '] silent hours, skip')
        return

    print('[' + now.strftime('%H:%M') + '] scanning...')

    try:
        klines = get_klines(interval='15m', limit=40)
        print('klines: ' + str(len(klines)))
    except Exception as e:
        print('data error: ' + str(e))
        return

    if len(klines) < 10:
        print('not enough data')
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

    # ── Long: lower wick pin ─────────────────────────────────────
    long_pin = body > 0 and lower_shadow >= body * 1.5 and c > mid
    if long_pin and vol_ok:
        sl   = round(l * 0.9985, 1)
        risk = round(price_now - sl, 1)
        tp1  = round(price_now + risk * 1.0, 1)
        tp2  = round(price_now + risk * 1.5, 1)
        tp3  = round(price_now + risk * 2.5, 1)

        score = 0
        details = []
        details.append('lower wick pin (shadow/body=' + str(round(lower_shadow / body, 1)) + 'x)')
        score += 3
        if vol_strong:
            details.append('huge volume (' + str(vol_ratio) + 'x)')
            score += 3
        else:
            details.append('volume ok (' + str(vol_ratio) + 'x)')
            score += 2
        if macd_long_ok:
            details.append('MACD ok (DIF=' + str(round(dif[-1], 1)) + ')')
            score += 2
        else:
            details.append('MACD no')
        if long_confirm_strong:
            details.append('confirm K strong')
            score += 2
        elif long_confirm_weak:
            details.append('confirm K weak')
            score += 1
        else:
            details.append('no confirm K')

        if score >= 8:
            level  = 'SUPER STRONG'
            advice = 'Strongly recommended! Multiple indicators aligned'
            stars  = '*****'
        elif score >= 6:
            level  = 'STRONG'
            advice = 'Suggested entry, small position'
            stars  = '****'
        else:
            level  = 'NORMAL'
            advice = 'Wait for confirmation'
            stars  = '***'

        if score >= 5:
            title = 'BTC LONG ' + level + ' | ' + str(int(price_now)) + ' | ' + str(score) + '/10'
            msg = (
                'BTC LONG Signal  ' + level + '\n'
                + stars + '  Score ' + str(score) + '/10  RR 1.5:1\n'
                '--------------------\n'
                'Time: ' + ts_str + '\n'
                'Price: ' + str(round(price_now, 1)) + ' USDT\n'
                'Dir: LONG (lower wick reversal)\n'
                '\nSignal:\n' + '\n'.join(details) + '\n'
                '\nAdvice: ' + advice + '\n'
                '\nPlan:\n'
                '  SL   ' + str(sl) + '  (-' + str(round((price_now - sl) / price_now * 100, 2)) + '%)\n'
                '  TP1  ' + str(tp1) + '  (+' + str(round((tp1 - price_now) / price_now * 100, 2)) + '%)\n'
                '  TP2  ' + str(tp2) + '  (+' + str(round((tp2 - price_now) / price_now * 100, 2)) + '%)\n'
                '  TP3  ' + str(tp3) + '  (+' + str(round((tp3 - price_now) / price_now * 100, 2)) + '%)\n'
                '\nMax 30% position size'
            )
            print(msg)
            push(title, msg)
        else:
            print('long score ' + str(score) + ' < 5, skip')
        return

    # ── Short: upper wick pin ────────────────────────────────────
    short_pin = body > 0 and upper_shadow >= body * 1.5 and c < mid
    if short_pin and vol_ok:
        sl   = round(h * 1.0015, 1)
        risk = round(sl - price_now, 1)
        tp1  = round(price_now - risk * 1.0, 1)
        tp2  = round(price_now - risk * 1.5, 1)
        tp3  = round(price_now - risk * 2.5, 1)

        score = 0
        details = []
        details.append('upper wick pin (shadow/body=' + str(round(upper_shadow / body, 1)) + 'x)')
        score += 3
        if vol_strong:
            details.append('huge volume (' + str(vol_ratio) + 'x)')
            score += 3
        else:
            details.append('volume ok (' + str(vol_ratio) + 'x)')
            score += 2
        if macd_short_ok:
            details.append('MACD ok (DIF=' + str(round(dif[-1], 1)) + ')')
            score += 2
        else:
            details.append('MACD no')
        if short_confirm_strong:
            details.append('confirm K strong')
            score += 2
        elif short_confirm_weak:
            details.append('confirm K weak')
            score += 1
        else:
            details.append('no confirm K')

        if score >= 8:
            level  = 'SUPER STRONG'
            advice = 'Strongly recommended! Multiple indicators aligned'
            stars  = '*****'
        elif score >= 6:
            level  = 'STRONG'
            advice = 'Suggested entry, small position'
            stars  = '****'
        else:
            level  = 'NORMAL'
            advice = 'Wait for confirmation'
            stars  = '***'

        if score >= 5:
            title = 'BTC SHORT ' + level + ' | ' + str(int(price_now)) + ' | ' + str(score) + '/10'
            msg = (
                'BTC SHORT Signal  ' + level + '\n'
                + stars + '  Score ' + str(score) + '/10  RR 1.5:1\n'
                '--------------------\n'
                'Time: ' + ts_str + '\n'
                'Price: ' + str(round(price_now, 1)) + ' USDT\n'
                'Dir: SHORT (upper wick reversal)\n'
                '\nSignal:\n' + '\n'.join(details) + '\n'
                '\nAdvice: ' + advice + '\n'
                '\nPlan:\n'
                '  SL   ' + str(sl) + '  (+' + str(round((sl - price_now) / price_now * 100, 2)) + '%)\n'
                '  TP1  ' + str(tp1) + '  (-' + str(round((price_now - tp1) / price_now * 100, 2)) + '%)\n'
                '  TP2  ' + str(tp2) + '  (-' + str(round((price_now - tp2) / price_now * 100, 2)) + '%)\n'
                '  TP3  ' + str(tp3) + '  (-' + str(round((price_now - tp3) / price_now * 100, 2)) + '%)\n'
                '\nMax 30% position size'
            )
            print(msg)
            push(title, msg)
        else:
            print('short score ' + str(score) + ' < 5, skip')
        return

    # ── MACD cross ───────────────────────────────────────────────
    check_macd_cross(dif, dea, hist, price_now, ts_str)

    print('[' + now.strftime('%H:%M') + '] no signal (long:' + str(long_pin) +
          ' short:' + str(short_pin) + ' vol:' + str(vol_ok) + ')')


if __name__ == '__main__':
    check_signal()
