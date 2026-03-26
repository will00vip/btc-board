# -*- coding: utf-8 -*-
"""
BTC 15分钟插针信号扫描（双向：做多+做空）
数据源：币安镜像 → 火币(HTX) → OKX  自动切换，哪个通就用哪个
"""
import sys, io, os, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datetime import datetime, timezone, timedelta

TZ8 = timezone(timedelta(hours=8))

# ── 加载配置 ──
_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from config import SERVERCHAN_KEY, PUSHDEER_KEY, HTX_ACCESS_KEY, HTX_SECRET_KEY


# ══════════════════════════════════════════════════════════
# 数据源：三源自动切换
# ══════════════════════════════════════════════════════════

def _get_klines_binance(interval='15m', limit=30):
    """币安镜像（公司网络通常可直连）"""
    url = 'https://data-api.binance.vision/api/v3/klines'
    resp = requests.get(url, params={'symbol': 'BTCUSDT', 'interval': interval, 'limit': limit}, timeout=10)
    resp.raise_for_status()
    result = []
    for k in resp.json():
        result.append({
            'ts':    datetime.fromtimestamp(k[0]/1000, tz=TZ8),
            'open':  float(k[1]),
            'high':  float(k[2]),
            'low':   float(k[3]),
            'close': float(k[4]),
            'vol':   float(k[5]),
        })
    return result


def _get_klines_htx(interval='15m', limit=30):
    """火币 HTX（国内可访问，优先使用）"""
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
        result.append({
            'ts':    datetime.fromtimestamp(k['id'], tz=TZ8),
            'open':  float(k['open']),
            'high':  float(k['high']),
            'low':   float(k['low']),
            'close': float(k['close']),
            'vol':   float(k['vol']),
        })
    return result


def _get_klines_okx(interval='15m', limit=30):
    """OKX（国内有时可直连）"""
    # OKX bar: 1m 3m 5m 15m 30m 1H 4H 1D 1W
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
    for k in reversed(data['data']):   # OKX也是倒序
        result.append({
            'ts':    datetime.fromtimestamp(int(k[0])/1000, tz=TZ8),
            'open':  float(k[1]),
            'high':  float(k[2]),
            'low':   float(k[3]),
            'close': float(k[4]),
            'vol':   float(k[5]),
        })
    return result


def get_klines(interval='15m', limit=30):
    """
    三源自动切换：币安镜像 → 火币 → OKX
    哪个能通就用哪个，全失败才报错
    """
    sources = [
        ('火币HTX',  _get_klines_htx),
        ('币安镜像', _get_klines_binance),
        ('OKX',      _get_klines_okx),
    ]
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
    raise RuntimeError(f'三个数据源全部失败，最后错误：{last_err}')


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
    # Server酱
    try:
        if SERVERCHAN_KEY and 'SendKey' not in SERVERCHAN_KEY:
            r = requests.post(f'https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send',
                              data={'title': title, 'desp': content}, timeout=10)
            print(f'[Server酱] {r.json().get("message","ok")}')
    except Exception as e:
        print(f'[Server酱异常] {e}')

    # PushDeer
    try:
        if PUSHDEER_KEY and 'Key' not in PUSHDEER_KEY:
            r = requests.post('https://api2.pushdeer.com/message/push',
                              data={'pushkey': PUSHDEER_KEY, 'title': title,
                                    'desp': content, 'text': content, 'type': 'markdown'}, timeout=10)
            print(f'[PushDeer] {r.json().get("code","?")}')
    except Exception as e:
        print(f'[PushDeer异常] {e}')


# ══════════════════════════════════════════════════════════
# 主扫描逻辑
# ══════════════════════════════════════════════════════════

def check_signal():
    now = datetime.now(tz=TZ8)

    # 过滤凌晨 0~6 点
    if 0 <= now.hour < 6:
        print("本次扫描无信号，继续监控中。")
        return

    try:
        klines = get_klines(interval='15m', limit=30)
    except RuntimeError as e:
        print(f'❌ 数据获取失败：{e}')
        return

    if len(klines) < 10:
        print("本次扫描无信号，继续监控中。")
        return

    # 倒数第2根（已收盘）为候选K线，倒数第1根为确认K线
    pin_k     = klines[-2]
    confirm_k = klines[-1]
    prev5     = klines[-7:-2]

    o, h, l, c, v = pin_k['open'], pin_k['high'], pin_k['low'], pin_k['close'], pin_k['vol']
    body         = abs(c - o)
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    kline_range  = h - l
    mid          = l + kline_range / 2

    # 成交量
    avg_vol = sum(k['vol'] for k in prev5) / len(prev5) if prev5 else 0
    vol_ok  = avg_vol > 0 and v >= avg_vol * 1.3

    # MACD
    closes = [k['close'] for k in klines]
    dif, dea, hist = calc_macd(closes)
    macd_ok = (len(hist) >= 3 and hist[-2] > hist[-3]) or \
              (dif[-3] < dea[-3] and dif[-2] >= dea[-2])

    # 4小时跌涨（用1小时K线取近5根近似）
    try:
        kl4h = get_klines(interval='1h', limit=5)
        drop_pct = (confirm_k['close'] - kl4h[0]['close']) / kl4h[0]['close'] * 100
    except Exception:
        drop_pct = 0  # 取不到就不过滤

    if drop_pct < -8:
        print("本次扫描无信号，继续监控中。")
        return

    price_now = confirm_k['close']
    ts_str    = pin_k['ts'].strftime("%m月%d日 %H:%M")

    # ── 做多信号：下影插针 ──
    long_cond1 = body > 0 and lower_shadow >= body * 1.5 and c > mid
    long_cond2 = confirm_k['low'] > l and confirm_k['close'] > confirm_k['open']

    if long_cond1 and long_cond2 and vol_ok and macd_ok:
        conditions = [
            "✅ 下影插针（下影≥实体1.5倍，收盘在上半段）",
            "✅ 低点抬高+收盘上涨（确认K线）",
            "✅ 成交量放大（≥前5根均量1.3倍）",
            "✅ MACD柱状图不再创新低/金叉",
        ]
        title = "🔔 BTC做多信号｜下影插针"
        msg = f"""🔔【BTC插针做多信号】
时间：{ts_str}
当前价格：{price_now:.1f} USDT
插针最低点（止损位参考）：{l:.1f} USDT
方向：📈 做多
满足条件：
""" + "\n".join(conditions) + "\n\n请人工核对SOP后决策！"
        print(msg)
        push(title, msg)
        return

    # ── 做空信号：上影插针 ──
    short_cond1   = body > 0 and upper_shadow >= body * 1.5 and c < mid
    short_cond2   = confirm_k['high'] < h and confirm_k['close'] < confirm_k['open']
    macd_short_ok = (len(hist) >= 3 and hist[-2] < hist[-3]) or \
                    (dif[-3] > dea[-3] and dif[-2] <= dea[-2])

    if short_cond1 and short_cond2 and vol_ok and macd_short_ok:
        conditions = [
            "✅ 上影插针（上影≥实体1.5倍，收盘在下半段）",
            "✅ 高点降低+收盘下跌（确认K线）",
            "✅ 成交量放大（≥前5根均量1.3倍）",
            "✅ MACD柱状图不再创新高/死叉",
        ]
        title = "🔔 BTC做空信号｜上影插针"
        msg = f"""🔔【BTC插针做空信号】
时间：{ts_str}
当前价格：{price_now:.1f} USDT
插针最高点（止损位参考）：{h:.1f} USDT
方向：📉 做空
满足条件：
""" + "\n".join(conditions) + "\n\n请人工核对SOP后决策！"
        print(msg)
        push(title, msg)
        return

    print("本次扫描无信号，继续监控中。")


if __name__ == '__main__':
    check_signal()
