# ================================================================
# 行情数据获取模块 — 三源自动切换
# 数据源：火币HTX → 币安镜像 → OKX，哪个通用哪个
# ================================================================

import pandas as pd
import requests
from datetime import datetime, timezone, timedelta

TZ8 = timezone(timedelta(hours=8))

# 超时配置
TIMEOUT = 10

# 数据源：interval 映射
_HTX_MAP = {
    '1min':'1min','5min':'5min','15min':'15min','30min':'30min',
    '60min':'60min','4hour':'4hour','1day':'1day','1week':'1week',
    '1hour':'60min',
}
_BINANCE_MAP = {
    '1min':'1m','5min':'5m','15min':'15m','30min':'30m',
    '60min':'1h','1hour':'1h','4hour':'4h','1day':'1d','1week':'1w',
}
_OKX_MAP = {
    '1min':'1m','5min':'5m','15min':'15m','30min':'30m',
    '60min':'1H','1hour':'1H','4hour':'4H','1day':'1D','1week':'1W',
}

# 读取HTX Key（可选）
try:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import HTX_ACCESS_KEY
except Exception:
    HTX_ACCESS_KEY = ''


def _htx(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    period = _HTX_MAP.get(interval, '15min')
    url = 'https://api.huobi.pro/market/history/kline'
    headers = {'AccessKeyId': HTX_ACCESS_KEY} if HTX_ACCESS_KEY else {}
    r = requests.get(url, params={'symbol': symbol.lower().replace('-',''), 'period': period, 'size': limit},
                     headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get('status') != 'ok':
        raise ValueError(f"HTX: {data.get('err-msg','error')}")
    rows = []
    for k in reversed(data['data']):
        rows.append({
            'timestamp': datetime.fromtimestamp(k['id'], tz=TZ8),
            'open':  float(k['open']),
            'high':  float(k['high']),
            'low':   float(k['low']),
            'close': float(k['close']),
            'volume': float(k['vol']),
        })
    return pd.DataFrame(rows)


def _binance(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    iv = _BINANCE_MAP.get(interval, '15m')
    url = 'https://data-api.binance.vision/api/v3/klines'
    r = requests.get(url, params={'symbol': symbol.upper().replace('-',''), 'interval': iv, 'limit': limit},
                     timeout=TIMEOUT)
    r.raise_for_status()
    rows = []
    for k in r.json():
        rows.append({
            'timestamp': datetime.fromtimestamp(k[0]/1000, tz=TZ8),
            'open':  float(k[1]),
            'high':  float(k[2]),
            'low':   float(k[3]),
            'close': float(k[4]),
            'volume': float(k[5]),
        })
    return pd.DataFrame(rows)


def _okx(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    bar = _OKX_MAP.get(interval, '15m')
    inst_id = symbol.upper()
    if 'USDT' in inst_id and '-' not in inst_id:
        inst_id = inst_id.replace('USDT', '-USDT')
    url = 'https://www.okx.com/api/v5/market/candles'
    r = requests.get(url, params={'instId': inst_id, 'bar': bar, 'limit': limit}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get('code') != '0':
        raise ValueError(f"OKX: {data.get('msg','error')}")
    rows = []
    for k in reversed(data['data']):
        rows.append({
            'timestamp': datetime.fromtimestamp(int(k[0])/1000, tz=TZ8),
            'open':  float(k[1]),
            'high':  float(k[2]),
            'low':   float(k[3]),
            'close': float(k[4]),
            'volume': float(k[5]),
        })
    return pd.DataFrame(rows)


def get_klines(symbol: str, interval: str, limit: int = 50) -> pd.DataFrame:
    """
    三源自动切换：火币HTX → 币安镜像 → OKX
    返回 DataFrame，列：timestamp, open, high, low, close, volume
    """
    sources = [
        ('火币HTX',  _htx),
        ('币安镜像', _binance),
        ('OKX',      _okx),
    ]
    for name, fn in sources:
        try:
            df = fn(symbol, interval, limit)
            if not df.empty:
                import logging
                logging.getLogger('btc_monitor').info(f'[数据源] {name} ✅')
                return df
        except Exception as e:
            import logging
            logging.getLogger('btc_monitor').warning(f'[数据源] {name} ❌ {e}')
    return pd.DataFrame()


def get_price_change_pct(symbol: str, hours: int = 4) -> float:
    """
    获取最近N小时的价格涨跌幅
    """
    candles_needed = hours * 4 + 5
    df = get_klines(symbol, '15min', limit=candles_needed + 1)
    if df.empty or len(df) < 2:
        return 0.0
    idx = min(candles_needed, len(df) - 1)
    start_price = df.iloc[-idx]['close']
    end_price   = df.iloc[-1]['close']
    return (end_price - start_price) / start_price * 100


def get_trend(symbol: str) -> dict:
    """
    获取1H和4H级别趋势判断
    趋势判断方法：EMA20 vs EMA50 + 近期高低点结构
    返回 {"1h": "上涨/震荡/下跌", "4h": "上涨/震荡/下跌",
          "1h_pct": float, "4h_pct": float, "bias": "顺势/中性/逆势(做多)"}
    """
    import numpy as np

    def _judge(df: pd.DataFrame, direction: str = "long") -> tuple[str, float]:
        if df.empty or len(df) < 55:
            return "数据不足", 0.0
        close = df['close']
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        e20 = ema20.iloc[-1]
        e50 = ema50.iloc[-1]
        # 斜率：EMA20最近5根的变化率
        slope = (ema20.iloc[-1] - ema20.iloc[-5]) / ema20.iloc[-5] * 100
        pct = round((close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100, 2)

        if e20 > e50 * 1.002 and slope > 0:
            trend = "📈上涨"
        elif e20 < e50 * 0.998 and slope < 0:
            trend = "📉下跌"
        else:
            trend = "↔️震荡"
        return trend, pct

    result = {"1h": "—", "4h": "—", "1h_pct": 0.0, "4h_pct": 0.0}

    try:
        df1h = get_klines(symbol, '60min', limit=60)
        trend1h, pct1h = _judge(df1h)
        result["1h"] = trend1h
        result["1h_pct"] = pct1h
    except Exception:
        pass

    try:
        df4h = get_klines(symbol, '4hour', limit=60)
        trend4h, pct4h = _judge(df4h)
        result["4h"] = trend4h
        result["4h_pct"] = pct4h
    except Exception:
        pass

    # 综合偏向（做多为例）
    up_count = sum(1 for t in [result["1h"], result["4h"]] if "上涨" in t)
    dn_count = sum(1 for t in [result["1h"], result["4h"]] if "下跌" in t)
    if up_count == 2:
        result["bias"] = "✅ 双周期上涨，顺势做多"
    elif dn_count == 2:
        result["bias"] = "⚠️ 双周期下跌，做多需谨慎"
    elif up_count == 1:
        result["bias"] = "🔶 趋势分歧，中性偏多"
    elif dn_count == 1:
        result["bias"] = "🔶 趋势分歧，中性偏空"
    else:
        result["bias"] = "↔️ 双周期震荡，区间交易"

    return result
