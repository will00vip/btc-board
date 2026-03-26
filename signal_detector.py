# ================================================================
# 信号识别模块 — 插针形态 + 放量 + MACD + KDJ + RSI + WR + BOLL
# ================================================================

import pandas as pd
import numpy as np
from config import (
    PIN_BAR_RATIO, CLOSE_POSITION_RATIO,
    VOLUME_AMPLIFY_RATIO, LOOKBACK_CANDLES
)


# ── 基础指标计算 ────────────────────────────────────────────────

def calc_macd(close: pd.Series, fast=12, slow=26, signal=9):
    """计算MACD指标"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd_bar = (dif - dea) * 2
    return dif, dea, macd_bar


def calc_kdj(df: pd.DataFrame, n=9, m1=3, m2=3):
    """计算KDJ指标"""
    low_min = df['low'].rolling(n).min()
    high_max = df['high'].rolling(n).max()
    rsv = (df['close'] - low_min) / (high_max - low_min + 1e-10) * 100
    K = rsv.ewm(com=m1 - 1, adjust=False).mean()
    D = K.ewm(com=m2 - 1, adjust=False).mean()
    J = 3 * K - 2 * D
    return K, D, J


def calc_rsi(close: pd.Series, period=14):
    """计算RSI指标"""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_wr(df: pd.DataFrame, period=14):
    """计算威廉指标WR（范围-100~0，越低越超卖）"""
    high_max = df['high'].rolling(period).max()
    low_min = df['low'].rolling(period).min()
    wr = -100 * (high_max - df['close']) / (high_max - low_min + 1e-10)
    return wr


def calc_boll(close: pd.Series, period=20, std_dev=2):
    """计算布林带"""
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower


# ── 形态判断 ────────────────────────────────────────────────────

def is_pin_bar(candle: pd.Series, direction: str = "long") -> tuple[bool, dict]:
    """
    判断插针K线
    direction='long'  → 下影插针（做多信号）
    direction='short' → 上影插针（做空信号）
    """
    o = candle["open"]
    h = candle["high"]
    l = candle["low"]
    c = candle["close"]

    body = abs(c - o)
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    total_range = h - l

    if total_range == 0:
        return False, {}

    close_position = (c - l) / total_range  # 0=收盘在最低, 1=收盘在最高

    if direction == "long":
        # 下影线 ≥ 实体1.5倍，收盘在上半段
        shadow_ok = (body > 0 and lower_shadow >= body * PIN_BAR_RATIO) or \
                    (body == 0 and lower_shadow > upper_shadow * 2)
        close_ok = close_position >= CLOSE_POSITION_RATIO
        shadow_ratio = round(lower_shadow / body, 2) if body > 0 else 999
        extreme_price = l  # 插针极值点=最低价
    else:  # short
        # 上影线 ≥ 实体1.5倍，收盘在下半段
        shadow_ok = (body > 0 and upper_shadow >= body * PIN_BAR_RATIO) or \
                    (body == 0 and upper_shadow > lower_shadow * 2)
        close_ok = close_position <= (1 - CLOSE_POSITION_RATIO)
        shadow_ratio = round(upper_shadow / body, 2) if body > 0 else 999
        extreme_price = h  # 插针极值点=最高价

    detail = {
        "body": round(body, 2),
        "lower_shadow": round(lower_shadow, 2),
        "upper_shadow": round(upper_shadow, 2),
        "total_range": round(total_range, 2),
        "shadow_ratio": shadow_ratio,
        "close_position": round(close_position * 100, 1),
        "low_price": l,
        "high_price": h,
        "extreme_price": extreme_price,
        "close_price": c,
        "direction": direction,
    }
    return (shadow_ok and close_ok), detail


def is_volume_amplified(df: pd.DataFrame, pin_idx: int) -> tuple[bool, float]:
    """判断插针K线成交量是否放大"""
    if len(df) < LOOKBACK_CANDLES + 1:
        return False, 0.0
    pin_vol = df.iloc[pin_idx]["volume"]
    prev_vols = df.iloc[pin_idx - LOOKBACK_CANDLES: pin_idx]["volume"]
    avg_vol = prev_vols.mean()
    if avg_vol == 0:
        return False, 0.0
    ratio = pin_vol / avg_vol
    return ratio >= VOLUME_AMPLIFY_RATIO, round(ratio, 2)


def is_extreme_confirmed(df: pd.DataFrame, pin_idx: int, direction: str) -> bool:
    """
    做多：低点抬高（后续K线低点 > 插针低点）
    做空：高点下降（后续K线高点 < 插针高点）
    """
    if len(df) < abs(pin_idx) + 2:
        return False
    follow_candles = df.iloc[pin_idx + 1:]
    if len(follow_candles) < 1:
        return False
    if direction == "long":
        pin_low = df.iloc[pin_idx]["low"]
        return all(follow_candles["low"] > pin_low)
    else:
        pin_high = df.iloc[pin_idx]["high"]
        return all(follow_candles["high"] < pin_high)


# ── 指标信号检查 ────────────────────────────────────────────────

def check_macd(df: pd.DataFrame, direction: str = "long") -> tuple[bool, str]:
    """MACD：做多=金叉/底背离；做空=死叉/顶背离"""
    dif, dea, macd_bar = calc_macd(df["close"])
    if len(macd_bar) < 3:
        return False, "数据不足"

    if direction == "long":
        golden_cross = (dif.iloc[-2] < dea.iloc[-2]) and (dif.iloc[-1] >= dea.iloc[-1])
        recent_bars = macd_bar.iloc[-3:]
        bar_not_new_low = (recent_bars.iloc[-1] > recent_bars.iloc[-2] or
                           recent_bars.iloc[-2] > recent_bars.iloc[-3])
        bottom_divergence = all(b < 0 for b in recent_bars) and bar_not_new_low
        if golden_cross:
            return True, f"MACD金叉✅ (DIF:{round(dif.iloc[-1],1)})"
        elif bottom_divergence:
            return True, f"MACD底背离✅ (Bar:{round(macd_bar.iloc[-1],1)})"
        else:
            return False, f"MACD无配合 (DIF:{round(dif.iloc[-1],1)}, DEA:{round(dea.iloc[-1],1)})"
    else:  # short
        dead_cross = (dif.iloc[-2] > dea.iloc[-2]) and (dif.iloc[-1] <= dea.iloc[-1])
        recent_bars = macd_bar.iloc[-3:]
        bar_not_new_high = (recent_bars.iloc[-1] < recent_bars.iloc[-2] or
                            recent_bars.iloc[-2] < recent_bars.iloc[-3])
        top_divergence = all(b > 0 for b in recent_bars) and bar_not_new_high
        if dead_cross:
            return True, f"MACD死叉✅ (DIF:{round(dif.iloc[-1],1)})"
        elif top_divergence:
            return True, f"MACD顶背离✅ (Bar:{round(macd_bar.iloc[-1],1)})"
        else:
            return False, f"MACD无配合 (DIF:{round(dif.iloc[-1],1)}, DEA:{round(dea.iloc[-1],1)})"


def check_kdj(df: pd.DataFrame, direction: str = "long") -> tuple[bool, str]:
    """
    KDJ：做多=金叉+超卖反弹；做空=死叉+超买回落
    """
    K, D, J = calc_kdj(df)
    if len(K) < 3:
        return False, "KDJ数据不足"

    k_val = round(K.iloc[-1], 1)
    d_val = round(D.iloc[-1], 1)
    j_val = round(J.iloc[-1], 1)

    if direction == "long":
        golden_cross = (K.iloc[-2] < D.iloc[-2]) and (K.iloc[-1] >= D.iloc[-1])
        j_oversold_bounce = (J.iloc[-2] < 20) and (J.iloc[-1] > J.iloc[-2])
        kd_oversold = (k_val < 30) and (d_val < 30)
        if golden_cross and (j_oversold_bounce or kd_oversold):
            return True, f"KDJ金叉+超卖✅ (K:{k_val}, D:{d_val}, J:{j_val})"
        elif golden_cross:
            return True, f"KDJ金叉✅ (K:{k_val}, D:{d_val}, J:{j_val})"
        elif j_oversold_bounce:
            return True, f"KDJ超卖反弹✅ (J:{j_val}回升)"
        else:
            return False, f"KDJ无信号 (K:{k_val}, D:{d_val}, J:{j_val})"
    else:  # short
        dead_cross = (K.iloc[-2] > D.iloc[-2]) and (K.iloc[-1] <= D.iloc[-1])
        j_overbought_drop = (J.iloc[-2] > 80) and (J.iloc[-1] < J.iloc[-2])
        kd_overbought = (k_val > 70) and (d_val > 70)
        if dead_cross and (j_overbought_drop or kd_overbought):
            return True, f"KDJ死叉+超买✅ (K:{k_val}, D:{d_val}, J:{j_val})"
        elif dead_cross:
            return True, f"KDJ死叉✅ (K:{k_val}, D:{d_val}, J:{j_val})"
        elif j_overbought_drop:
            return True, f"KDJ超买回落✅ (J:{j_val}下降)"
        else:
            return False, f"KDJ无信号 (K:{k_val}, D:{d_val}, J:{j_val})"


def check_rsi(df: pd.DataFrame, direction: str = "long") -> tuple[bool, str]:
    """
    RSI：做多=超卖反弹（RSI<30↑）；做空=超买回落（RSI>70↓）
    """
    rsi = calc_rsi(df["close"])
    if len(rsi) < 3:
        return False, "RSI数据不足"

    rsi_val = round(rsi.iloc[-1], 1)
    rsi_prev = round(rsi.iloc[-2], 1)

    if direction == "long":
        oversold_bounce = (rsi_prev < 30) and (rsi_val > rsi_prev)
        strong_oversold = rsi_prev < 25
        if strong_oversold and oversold_bounce:
            return True, f"RSI强超卖反弹✅ (RSI:{rsi_val}↑, 前:{rsi_prev})"
        elif oversold_bounce:
            return True, f"RSI超卖反弹✅ (RSI:{rsi_val}↑)"
        elif rsi_val < 35:
            return True, f"RSI接近超卖✅ (RSI:{rsi_val})"
        else:
            return False, f"RSI中性 (RSI:{rsi_val})"
    else:  # short
        overbought_drop = (rsi_prev > 70) and (rsi_val < rsi_prev)
        strong_overbought = rsi_prev > 75
        if strong_overbought and overbought_drop:
            return True, f"RSI强超买回落✅ (RSI:{rsi_val}↓, 前:{rsi_prev})"
        elif overbought_drop:
            return True, f"RSI超买回落✅ (RSI:{rsi_val}↓)"
        elif rsi_val > 65:
            return True, f"RSI接近超买✅ (RSI:{rsi_val})"
        else:
            return False, f"RSI中性 (RSI:{rsi_val})"


def check_wr(df: pd.DataFrame, direction: str = "long") -> tuple[bool, str]:
    """
    WR威廉指标：做多=超卖反弹（WR<-80↑）；做空=超买回落（WR>-20↓）
    WR范围 -100~0，越低越超卖，越高越超买
    """
    wr = calc_wr(df)
    if len(wr) < 3:
        return False, "WR数据不足"

    wr_val = round(wr.iloc[-1], 1)
    wr_prev = round(wr.iloc[-2], 1)

    if direction == "long":
        oversold_bounce = (wr_prev < -80) and (wr_val > wr_prev)
        strong_oversold = wr_prev < -90
        if strong_oversold and oversold_bounce:
            return True, f"WR极度超卖反弹✅ (WR:{wr_val}↑)"
        elif oversold_bounce:
            return True, f"WR超卖反弹✅ (WR:{wr_val}↑)"
        elif wr_val < -75:
            return True, f"WR超卖区✅ (WR:{wr_val})"
        else:
            return False, f"WR中性 (WR:{wr_val})"
    else:  # short
        overbought_drop = (wr_prev > -20) and (wr_val < wr_prev)
        strong_overbought = wr_prev > -10
        if strong_overbought and overbought_drop:
            return True, f"WR极度超买回落✅ (WR:{wr_val}↓)"
        elif overbought_drop:
            return True, f"WR超买回落✅ (WR:{wr_val}↓)"
        elif wr_val > -25:
            return True, f"WR超买区✅ (WR:{wr_val})"
        else:
            return False, f"WR中性 (WR:{wr_val})"


def check_boll(df: pd.DataFrame, direction: str = "long") -> tuple[bool, str]:
    """
    BOLL布林带：做多=触及下轨反弹；做空=触及上轨回落
    """
    upper, mid, lower = calc_boll(df["close"])
    if lower.iloc[-1] is None or pd.isna(lower.iloc[-1]):
        return False, "BOLL数据不足"

    low_val   = df.iloc[-1]["low"]
    high_val  = df.iloc[-1]["high"]
    close_val = df.iloc[-1]["close"]
    lower_val = round(lower.iloc[-1], 1)
    mid_val   = round(mid.iloc[-1], 1)
    upper_val = round(upper.iloc[-1], 1)

    if direction == "long":
        touched_lower = low_val <= lower_val * 1.002
        close_above_lower = close_val > lower_val
        if touched_lower and close_above_lower:
            return True, f"BOLL触下轨反弹✅ (下轨:{lower_val}, 收:{round(close_val,1)})"
        elif close_val < lower_val:
            return False, f"BOLL跌破下轨⚠️ (下轨:{lower_val})"
        else:
            return False, f"BOLL正常区间 (下:{lower_val}, 中:{mid_val})"
    else:  # short
        touched_upper = high_val >= upper_val * 0.998
        close_below_upper = close_val < upper_val
        if touched_upper and close_below_upper:
            return True, f"BOLL触上轨回落✅ (上轨:{upper_val}, 收:{round(close_val,1)})"
        elif close_val > upper_val:
            return False, f"BOLL突破上轨⚠️ (上轨:{upper_val})"
        else:
            return False, f"BOLL正常区间 (上:{upper_val}, 中:{mid_val})"


# ── 交易价值评估 ────────────────────────────────────────────────

def evaluate_trade_value(
    entry_price: float,
    stop_loss: float,
    score: int,
    drop_4h: float,
    macd_ok: bool,
    kdj_ok: bool,
    rsi_ok: bool,
    wr_ok: bool,
    boll_ok: bool,
    low_rising: bool,
    direction: str = "long",
) -> dict:
    """
    综合评估这笔交易值不值得做（支持多空双向）
    """
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        risk = entry_price * 0.005  # 兜底0.5%

    # 止盈目标（做多向上，做空向下）
    if direction == "long":
        tp_conservative = round(entry_price + risk * 1.5, 1)
        tp_standard     = round(entry_price + risk * 2.5, 1)
        tp_aggressive   = round(entry_price + risk * 4.0, 1)
    else:
        tp_conservative = round(entry_price - risk * 1.5, 1)
        tp_standard     = round(entry_price - risk * 2.5, 1)
        tp_aggressive   = round(entry_price - risk * 4.0, 1)

    rr_standard = 2.5  # 固定标准盈亏比

    strong_indicators = sum([macd_ok, kdj_ok])
    trend_ok = drop_4h > -3 if direction == "long" else drop_4h < 3

    dir_cn   = "做多" if direction == "long" else "做空"
    dir_macd = "金叉" if direction == "long" else "死叉"
    dir_conf = "低点" if direction == "long" else "高点"

    if score >= 8 and strong_indicators >= 2 and low_rising and trend_ok:
        rating = f"🟢 强烈推荐{dir_cn}"
        advice = f"信号极强，可按仓位20~30%建仓，止损{stop_loss:,.0f}，目标{tp_standard:,.0f}"
        confidence = "高"
    elif score >= 6 and strong_indicators >= 1 and trend_ok:
        rating = f"🟡 建议{dir_cn}"
        advice = f"信号较好，轻仓10~20%试探，止损{stop_loss:,.0f}，目标{tp_conservative:,.0f}"
        confidence = "中"
    elif score >= 5:
        rating = f"🟠 可以考虑（谨慎）"
        advice = f"盈亏比尚可({rr_standard}:1)，超轻仓5~10%，止损{stop_loss:,.0f}"
        confidence = "低"
    else:
        rating = "🔴 不建议做"
        advice = "指标配合不足或盈亏比差，等更好机会"
        confidence = "极低"

    risk_notes = []
    if direction == "long" and drop_4h < -5:
        risk_notes.append("⚠️ 4小时跌幅较大，反弹力度存疑")
    if direction == "short" and drop_4h > 5:
        risk_notes.append("⚠️ 4小时涨幅较大，回落力度存疑")
    if not low_rising:
        risk_notes.append(f"⚠️ {dir_conf}未确认，形态有待验证")
    if not macd_ok:
        risk_notes.append(f"⚠️ MACD未{dir_macd}，可等信号确认再入")

    return {
        "rating": rating,
        "confidence": confidence,
        "advice": advice,
        "rr_ratio": rr_standard,
        "tp_conservative": tp_conservative,
        "tp_standard": tp_standard,
        "tp_aggressive": tp_aggressive,
        "risk_per_unit": round(risk, 1),
        "risk_notes": risk_notes,
    }


# ── 综合信号评分 ────────────────────────────────────────────────

def score_signal(macd_ok, kdj_ok, rsi_ok, wr_ok, boll_ok, low_rising) -> tuple[int, str]:
    """
    综合评分：
    - 插针形态+放量 是前提条件（必须满足）
    - 低点抬高：+2分（强确认）
    - MACD配合：+2分
    - KDJ配合：+2分
    - RSI超卖：+1分
    - WR超卖：+1分
    - BOLL触下轨：+1分
    满分10分，≥5分触发推送，≥8分为强信号
    """
    score = 0
    if low_rising: score += 2
    if macd_ok:    score += 2
    if kdj_ok:     score += 2
    if rsi_ok:     score += 1
    if wr_ok:      score += 1
    if boll_ok:    score += 1

    if score >= 8:
        level = "🔥强信号"
    elif score >= 5:
        level = "⚡中等信号"
    else:
        level = "⚠️弱信号"

    return score, level


# ── 主检测函数 ──────────────────────────────────────────────────

def detect_signal(df: pd.DataFrame, drop_4h: float = 0.0) -> dict | None:
    """
    主信号检测函数（支持做多/做空双向）
    返回信号字典（score≥5时）或 None
    drop_4h: 4小时涨跌幅，用于交易价值评估
    """
    if len(df) < 30:
        return None

    # 先检测做多（下影插针），再检测做空（上影插针）
    for direction in ["long", "short"]:
        for lookback in [-3, -2, -1]:
            pin_ok, pin_detail = is_pin_bar(df.iloc[lookback], direction=direction)
            if not pin_ok:
                continue

            vol_ok, vol_ratio = is_volume_amplified(df, lookback)
            if not vol_ok:
                continue

            extreme_confirmed = is_extreme_confirmed(df, lookback, direction)
            if not extreme_confirmed and lookback != -1:
                continue

            # 各指标检查（传入方向）
            macd_ok, macd_desc = check_macd(df, direction)
            kdj_ok,  kdj_desc  = check_kdj(df,  direction)
            rsi_ok,  rsi_desc  = check_rsi(df,  direction)
            wr_ok,   wr_desc   = check_wr(df,   direction)
            boll_ok, boll_desc = check_boll(df, direction)

            # 综合评分（仅供参考，不再作为推送门槛）
            score, level = score_signal(macd_ok, kdj_ok, rsi_ok, wr_ok, boll_ok, extreme_confirmed)

            entry_price = df.iloc[-1]["close"]

            if direction == "long":
                pin_extreme = pin_detail["low_price"]
                stop_loss   = round(pin_extreme * 0.998, 1)
                tp1 = round(entry_price * 1.30, 1)
                tp2 = round(entry_price * 1.50, 1)
            else:
                pin_extreme = pin_detail["high_price"]
                stop_loss   = round(pin_extreme * 1.002, 1)
                tp1 = round(entry_price * 0.70, 1)
                tp2 = round(entry_price * 0.50, 1)

            # 交易价值评估
            trade_eval = evaluate_trade_value(
                entry_price=entry_price,
                stop_loss=stop_loss,
                score=score,
                drop_4h=drop_4h,
                macd_ok=macd_ok,
                kdj_ok=kdj_ok,
                rsi_ok=rsi_ok,
                wr_ok=wr_ok,
                boll_ok=boll_ok,
                low_rising=extreme_confirmed,
                direction=direction,
            )

            return {
                "found": True,
                "direction": direction,   # "long" 或 "short"
                "score": score,
                "level": level,
                "time": df.iloc[-1]["timestamp"].strftime("%m月%d日 %H:%M"),
                "entry_price": entry_price,
                "pin_extreme": pin_extreme,  # 做多=低点，做空=高点
                "stop_loss": stop_loss,
                "tp1": tp1,
                "tp2": tp2,
                "shadow_ratio": pin_detail["shadow_ratio"],
                "close_position": pin_detail["close_position"],
                "volume_ratio": vol_ratio,
                "extreme_confirmed": extreme_confirmed,
                "low_rising": extreme_confirmed,  # 兼容旧字段名
                "macd_ok": macd_ok,   "macd_desc": macd_desc,
                "kdj_ok":  kdj_ok,    "kdj_desc":  kdj_desc,
                "rsi_ok":  rsi_ok,    "rsi_desc":  rsi_desc,
                "wr_ok":   wr_ok,     "wr_desc":   wr_desc,
                "boll_ok": boll_ok,   "boll_desc": boll_desc,
                # 交易价值评估
                "trade_rating":   trade_eval["rating"],
                "trade_advice":   trade_eval["advice"],
                "trade_rr":       trade_eval["rr_ratio"],
                "trade_tp_cons":  trade_eval["tp_conservative"],
                "trade_tp_std":   trade_eval["tp_standard"],
                "trade_tp_agg":   trade_eval["tp_aggressive"],
                "trade_risk_per": trade_eval["risk_per_unit"],
                "trade_conf":     trade_eval["confidence"],
                "trade_risks":    trade_eval["risk_notes"],
            }

    return None

