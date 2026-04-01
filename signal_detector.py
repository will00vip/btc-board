# ================================================================
# 信号识别模块 — 插针形态 + 放量 + MACD + KDJ + RSI + WR + BOLL
# ================================================================

import pandas as pd
import numpy as np
from config import (
    PIN_BAR_RATIO, CLOSE_POSITION_RATIO,
    VOLUME_AMPLIFY_RATIO, LOOKBACK_CANDLES,
    ACCOUNT_BALANCE, RISK_PER_TRADE, MAX_POSITION_PCT,
    CONTRACT_SIZE, DEFAULT_LEVERAGE,
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
    """
    判断插针K线成交量是否放大
    优化：基准用前20根均量（而非前5根），避免量能枯竭期把小量当放量
    """
    BASE_CANDLES = 20  # 量比基准周期改为20根
    if len(df) < BASE_CANDLES + 1:
        return False, 0.0
    pin_vol = df.iloc[pin_idx]["volume"]
    prev_vols = df.iloc[pin_idx - BASE_CANDLES: pin_idx]["volume"]
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


# ── 仓位计算器 ──────────────────────────────────────────────────

def calc_position_size(
    entry_price: float,
    stop_loss: float,
    account: float = ACCOUNT_BALANCE,
    risk_pct: float = RISK_PER_TRADE,
    leverage: int = DEFAULT_LEVERAGE,
    contract_size: float = CONTRACT_SIZE,
) -> dict:
    """
    根据止损距离计算合理仓位
    逻辑：单笔最大亏损 = 账户 × risk_pct
         止损距离（U） = |entry - stop_loss|
         合约张数 = 最大亏损 / (止损距离 × contract_size) / leverage
    返回：张数、保证金、仓位占比、杠杆
    """
    risk_amount = account * risk_pct          # 本次愿意亏的最多U数
    sl_distance = abs(entry_price - stop_loss)
    if sl_distance <= 0:
        sl_distance = entry_price * 0.005

    # 每张合约价值（U本位）= entry_price × contract_size
    contract_value = entry_price * contract_size

    # 不带杠杆时，N张止损亏损 = N × contract_size × sl_distance
    # 带杠杆：所需保证金 = N × contract_value / leverage
    lots = risk_amount / (contract_size * sl_distance)
    lots = max(1, round(lots))  # 最少1张

    margin = lots * contract_value / leverage
    position_ratio = margin / account

    # 防止超过最大仓位限制
    max_margin = account * MAX_POSITION_PCT
    if margin > max_margin:
        lots = max(1, int(max_margin * leverage / contract_value))
        margin = lots * contract_value / leverage
        position_ratio = margin / account

    return {
        "lots":           lots,
        "margin":         round(margin, 1),
        "position_ratio": round(position_ratio * 100, 1),
        "leverage":       leverage,
        "risk_amount":    round(risk_amount, 1),
        "sl_distance":    round(sl_distance, 1),
    }


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


# ── 综合信号评分（对齐三步法，12分制） ──────────────────────────

def score_signal_3step(
    daily_trend: str,           # "strong_bull/bull/strong_bear/bear/neutral"
    h1_resonance: bool,         # 1h MACD+RSI共振是否满足（满分3分）
    pin_ratio: float,           # 影线/实体 比例（插针强度）
    vol_ratio: float,           # 量比（放量强度）
    rsi_val: float,             # 当前15m RSI值
    direction: str,             # "long" 或 "short"
    macd_ok: bool,              # MACD配合
    kdj_ok: bool,               # KDJ配合
    low_rising: bool,           # 极值确认（低点抬高/高点下降）
    h1_rsi_val: float = 50.0,   # 1h RSI值（用于共振降权判断）
) -> tuple[int, int, str]:
    """
    三步法对齐评分（硬上限12分制）：

    步骤1 - 日线大趋势（最多3分）：
        顺势强趋势 +3，顺势普通趋势 +2，震荡 +1
        [优化] 超跌/超涨（逆势但极端）允许 +1分触底反弹机会

    步骤2 - 1h共振（最多3分）→ 优化RSI宽松度：
        MACD方向对 且 RSI理想区(<55多/>45空)  → +3（满分）
        MACD方向对 且 RSI中性区(55~65多/35~45空) → +2（降权）
        MACD方向对 且 RSI偏热(65~75多/25~35空)   → +1（最低共振）
        无MACD配合 但 RSI极值(<30多/>70空)       → +1（极值救场）
        其他                                     → +0

    步骤3 - 15m形态强度（最多4分）：
        插针比例≥3倍 +2，≥1.5倍 +1
        量比≥2倍 +2，≥1.3倍 +1

    附加条件（最多2分）：
        RSI极值（<30多/>70空）+1，极端（<20多/>80空）再+1
        极值确认（低点抬高/高点下降）+1

    推送门槛：≥5/12分（≈App 42分）
    强信号：≥9/12分
    上限：min(score, 12)，100分换算基准固定12
    """
    score = 0

    # ── 步骤1：日线大趋势（最多3分） ──────────────────
    if direction == "long":
        if daily_trend == "strong_bull":
            score += 3
        elif daily_trend == "bull":
            score += 2
        elif daily_trend == "neutral":
            score += 1
        elif daily_trend in ("bear", "strong_bear"):
            # 逆势做多只有超跌才给分（步骤1贡献0，留给其他步骤撑）
            score += 0
    else:  # short
        if daily_trend == "strong_bear":
            score += 3
        elif daily_trend == "bear":
            score += 2
        elif daily_trend == "neutral":
            score += 1
        elif daily_trend in ("bull", "strong_bull"):
            score += 0  # 逆势做空，步骤1贡献0

    # ── 步骤2：1h共振（最多3分，RSI降权）─────────────
    # h1_resonance 是老接口（True/False），这里用精细化的 h1_rsi_val
    if h1_resonance:
        if direction == "long":
            if h1_rsi_val < 55:
                score += 3   # 理想区：多头共振且RSI未热
            elif h1_rsi_val < 65:
                score += 2   # 可接受：RSI偏热但还行
            else:
                score += 1   # 勉强：RSI已热，共振质量低
        else:  # short
            if h1_rsi_val > 45:
                score += 3   # 理想区：空头共振且RSI未冷
            elif h1_rsi_val > 35:
                score += 2   # 可接受
            else:
                score += 1   # RSI已超卖，空头共振质量低
    else:
        # 无共振但RSI极值（触底/触顶）给1分救场
        if direction == "long" and rsi_val < 30:
            score += 1
        elif direction == "short" and rsi_val > 70:
            score += 1

    # ── 步骤3：15m形态强度（最多4分）─────────────────
    if pin_ratio >= 3.0:
        score += 2
    elif pin_ratio >= 1.5:
        score += 1

    if vol_ratio >= 2.0:
        score += 2
    elif vol_ratio >= 1.3:
        score += 1

    # ── 附加：15m RSI位置（最多2分）──────────────────
    if direction == "long":
        if rsi_val < 20:
            score += 2   # 极度超卖
        elif rsi_val < 30:
            score += 1   # 超卖
    else:
        if rsi_val > 80:
            score += 2   # 极度超买
        elif rsi_val > 70:
            score += 1   # 超买

    # ── 附加：极值确认（1分）──────────────────────────
    if low_rising:
        score += 1

    # ══ 硬上限12分，换算100分 ══════════════════════════
    score = min(score, 12)
    score_100 = round(score / 12 * 100)

    if score >= 9:
        level = "🔥强信号"
    elif score >= 6:
        level = "⚡中等信号"
    elif score >= 4:
        level = "⚠️弱信号"
    else:
        level = "❄️噪音"

    return score, score_100, level


def score_signal(macd_ok, kdj_ok, rsi_ok, wr_ok, boll_ok, low_rising) -> tuple[int, str]:
    """旧版10分制（保留兼容，内部不再使用）"""
    score = 0
    if low_rising: score += 2
    if macd_ok:    score += 2
    if kdj_ok:     score += 2
    if rsi_ok:     score += 1
    if wr_ok:      score += 1
    if boll_ok:    score += 1
    level = "🔥强信号" if score >= 8 else ("⚡中等信号" if score >= 5 else "⚠️弱信号")
    return score, level


# ── 日线趋势判断（供 detect_signal 内部调用） ─────────────────────

def _calc_daily_trend(df_daily: pd.DataFrame) -> tuple[str, float]:
    """
    判断日线趋势类型
    返回 (trend_str, price_vs_ema50_pct)
    trend_str: 'strong_bull'/'bull'/'strong_bear'/'bear'/'neutral'
               + 特殊标记 'overdip'（超跌>8%于EMA50下方）/'overblow'（超涨>8%于EMA50上方）
    price_vs_ema50_pct: 价格偏离EMA50的百分比（正=在EMA50上方）

    [优化] 当价格已跌至EMA50下方≥8%时标记 overdip，
           允许逆势做多（超跌反弹）；
           当价格已涨至EMA50上方≥8%时标记 overblow，
           允许逆势做空（超涨回落）。
    """
    if df_daily is None or len(df_daily) < 30:
        return "neutral", 0.0

    close = df_daily["close"]
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    e20 = ema20.iloc[-1]
    e50 = ema50.iloc[-1]
    cur_price = close.iloc[-1]
    slope = (ema20.iloc[-1] - ema20.iloc[-6]) / ema20.iloc[-6] * 100  # 5日斜率%

    price_vs_ema50 = (cur_price - e50) / e50 * 100  # 偏离EMA50的%

    # 超跌/超涨优先判断（逆势触底/顶机会）
    if price_vs_ema50 <= -8.0:
        return "overdip", round(price_vs_ema50, 1)   # 超跌，支持逆势做多
    if price_vs_ema50 >= 8.0:
        return "overblow", round(price_vs_ema50, 1)  # 超涨，支持逆势做空

    if e20 > e50 * 1.005 and slope > 0.5:
        return "strong_bull", round(price_vs_ema50, 1)
    elif e20 > e50 * 1.001 and slope > 0:
        return "bull", round(price_vs_ema50, 1)
    elif e20 < e50 * 0.995 and slope < -0.5:
        return "strong_bear", round(price_vs_ema50, 1)
    elif e20 < e50 * 0.999 and slope < 0:
        return "bear", round(price_vs_ema50, 1)
    else:
        return "neutral", round(price_vs_ema50, 1)


def _calc_h1_resonance(df_1h: pd.DataFrame, direction: str) -> tuple[bool, str, float]:
    """
    判断1h MACD+RSI共振
    返回 (ok: bool, desc: str, rsi_val: float)
    rsi_val 用于评分函数的降权判断

    做多理想：1h MACD DIF > DEA 且 RSI < 55（未热）
    做多可接受：RSI 55~65 降权
    做多勉强：RSI 65~75 最低共振
    极端超卖（RSI<30）：即使MACD未配合也给1分救场（在评分函数处理）

    做空镜像对称
    """
    if df_1h is None or len(df_1h) < 30:
        return False, "1h数据不足", 50.0

    dif, dea, _ = calc_macd(df_1h["close"])
    rsi_1h = calc_rsi(df_1h["close"])
    dif_last = dif.iloc[-1]
    dea_last = dea.iloc[-1]
    rsi_val = round(rsi_1h.iloc[-1], 1)

    if direction == "long":
        macd_bull = dif_last > dea_last
        if macd_bull and rsi_val < 75:   # MACD方向对，RSI未极度超买就认可共振
            if rsi_val < 55:
                desc = f"1h MACD多头区✅ RSI={rsi_val}(理想)"
            elif rsi_val < 65:
                desc = f"1h MACD多头区⚡ RSI={rsi_val}(偏热-降权)"
            else:
                desc = f"1h MACD多头区⚠️ RSI={rsi_val}(热-弱共振)"
            return True, desc, rsi_val
        elif rsi_val < 30:
            return True, f"1h RSI极度超卖✅ RSI={rsi_val}", rsi_val
        else:
            return False, f"1h 多头共振未满足 MACD={'多头' if macd_bull else '空头'} RSI={rsi_val}", rsi_val
    else:
        macd_bear = dif_last < dea_last
        if macd_bear and rsi_val > 25:   # MACD方向对，RSI未极度超卖就认可共振
            if rsi_val > 45:
                desc = f"1h MACD空头区✅ RSI={rsi_val}(理想)"
            elif rsi_val > 35:
                desc = f"1h MACD空头区⚡ RSI={rsi_val}(偏冷-降权)"
            else:
                desc = f"1h MACD空头区⚠️ RSI={rsi_val}(冷-弱共振)"
            return True, desc, rsi_val
        elif rsi_val > 70:
            return True, f"1h RSI极度超买✅ RSI={rsi_val}", rsi_val
        else:
            return False, f"1h 空头共振未满足 MACD={'空头' if macd_bear else '多头'} RSI={rsi_val}", rsi_val


# ── 主检测函数 ──────────────────────────────────────────────────

# 推送门槛：三步法12分制，≥5分才推（对应App约42%）
PUSH_MIN_SCORE = 5    # 最低推送分（三步法12分制）
PUSH_STRONG_SCORE = 9 # 强信号分（三步法12分制）


def detect_signal(
    df: pd.DataFrame,
    drop_4h: float = 0.0,
    df_daily: pd.DataFrame = None,   # 日线数据（可选，有则更准确）
    df_1h: pd.DataFrame = None,      # 1h数据（可选，有则做共振检测）
) -> dict | None:
    """
    主信号检测函数（三步法对齐版 v4.1）
    推送门槛：三步法12分制 ≥5分（即App约42分以上）
    drop_4h:  4小时涨跌幅
    df_daily: 日线K线（用于步骤1大趋势）
    df_1h:    1h K线（用于步骤2共振检测）
    """
    if len(df) < 30:
        return None

    # ── 步骤1：计算日线大趋势 ──────────────────────────────────
    daily_trend, price_vs_ema50 = _calc_daily_trend(df_daily)

    daily_trend_cn = {
        "strong_bull": "🚀日线强多头",
        "bull":        "📈日线多头",
        "strong_bear": "💥日线强空头",
        "bear":        "📉日线空头",
        "neutral":     "↔️日线震荡",
        "overdip":     f"🩸超跌{price_vs_ema50:.1f}%(触底机会)",
        "overblow":    f"🌋超涨+{price_vs_ema50:.1f}%(顶部机会)",
    }.get(daily_trend, "↔️震荡")

    # ── 优化④：检测同支撑位连续插针（降权） ──────────────────
    # 统计最近6根K线中同方向插针数量，第2次以上降权
    def _count_recent_pins(direction: str, lookback_range=6) -> int:
        count = 0
        for i in range(-lookback_range, 0):
            if abs(i) <= len(df):
                ok, _ = is_pin_bar(df.iloc[i], direction=direction)
                if ok:
                    count += 1
        return count

    # ── 先检测做多（下影插针），再检测做空（上影插针） ────────
    for direction in ["long", "short"]:

        # 步骤1方向过滤
        if daily_trend == "strong_bull" and direction == "short":
            continue  # 日线强多头不做空
        if daily_trend == "strong_bear" and direction == "long":
            continue  # 日线强空头不做多
        # overdip 只做多，overblow 只做空
        if daily_trend == "overdip" and direction == "short":
            continue
        if daily_trend == "overblow" and direction == "long":
            continue

        # ── 步骤2：1h共振检测（返回3个值）──────────────────
        h1_ok, h1_desc, h1_rsi_val = _calc_h1_resonance(df_1h, direction)

        # 统计最近6根里的同向插针数（用于降权）
        recent_pin_count = _count_recent_pins(direction, lookback_range=6)

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

            # 各指标检查
            macd_ok, macd_desc = check_macd(df, direction)
            kdj_ok,  kdj_desc  = check_kdj(df,  direction)
            rsi_ok,  rsi_desc  = check_rsi(df,  direction)
            wr_ok,   wr_desc   = check_wr(df,   direction)
            boll_ok, boll_desc = check_boll(df, direction)

            # 当前15m RSI值（用于三步法评分）
            rsi_15m = calc_rsi(df["close"])
            rsi_15m_val = round(rsi_15m.iloc[-1], 1)

            # ── 三步法综合评分（12分制，硬上限） ─────────────
            pin_ratio = pin_detail["shadow_ratio"]
            score, score_100, level = score_signal_3step(
                daily_trend=daily_trend,
                h1_resonance=h1_ok,
                pin_ratio=pin_ratio,
                vol_ratio=vol_ratio,
                rsi_val=rsi_15m_val,
                direction=direction,
                macd_ok=macd_ok,
                kdj_ok=kdj_ok,
                low_rising=extreme_confirmed,
                h1_rsi_val=h1_rsi_val,
            )

            # ── 优化④：连续插针降权 ───────────────────────────
            # 同一支撑位出现≥3根插针，反转质量递减，扣1分
            consecutive_penalty = 0
            if recent_pin_count >= 3:
                consecutive_penalty = 1
                score = max(0, score - consecutive_penalty)
                score_100 = round(score / 12 * 100)
                # 重新判断level
                if score >= 9:
                    level = "🔥强信号"
                elif score >= 6:
                    level = "⚡中等信号"
                elif score >= 4:
                    level = "⚠️弱信号"
                else:
                    level = "❄️噪音"

            # ════════════════════════════════════════════════
            # 推送门槛：≥5分（12分制）才触发推送
            # ════════════════════════════════════════════════
            if score < PUSH_MIN_SCORE:
                import logging
                logging.getLogger('btc_monitor').info(
                    f"[过滤] {direction} 信号评分{score}/12({score_100}/100) < {PUSH_MIN_SCORE}分，不推送"
                    f" | 日线:{daily_trend_cn} | 1h:{h1_desc}"
                    + (f" | 连续插针{recent_pin_count}根-扣{consecutive_penalty}分" if consecutive_penalty else "")
                )
                continue

            entry_price = df.iloc[-1]["close"]

            if direction == "long":
                pin_extreme = pin_detail["low_price"]
                stop_loss   = round(pin_extreme * 0.998, 1)
            else:
                pin_extreme = pin_detail["high_price"]
                stop_loss   = round(pin_extreme * 1.002, 1)

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

            # 仓位计算
            pos = calc_position_size(entry_price, stop_loss)

            return {
                "found": True,
                "direction": direction,
                "score": score,           # 12分制（三步法，硬上限12）
                "score_100": score_100,   # 100分制（与App对齐）
                "level": level,
                "time": df.iloc[-1]["timestamp"].strftime("%m月%d日 %H:%M"),
                "entry_price": entry_price,
                "pin_extreme": pin_extreme,
                "stop_loss": stop_loss,
                # 三步法信息
                "daily_trend": daily_trend,
                "daily_trend_cn": daily_trend_cn,
                "price_vs_ema50": price_vs_ema50,   # 价格偏离EMA50%
                "h1_resonance": h1_ok,
                "h1_desc": h1_desc,
                "h1_rsi": h1_rsi_val,
                "consecutive_pins": recent_pin_count,   # 连续插针数
                "consecutive_penalty": consecutive_penalty,
                # 形态细节
                "shadow_ratio": pin_detail["shadow_ratio"],
                "close_position": pin_detail["close_position"],
                "volume_ratio": vol_ratio,
                "extreme_confirmed": extreme_confirmed,
                "low_rising": extreme_confirmed,
                # 指标
                "macd_ok": macd_ok,   "macd_desc": macd_desc,
                "kdj_ok":  kdj_ok,    "kdj_desc":  kdj_desc,
                "rsi_ok":  rsi_ok,    "rsi_desc":  rsi_desc,
                "wr_ok":   wr_ok,     "wr_desc":   wr_desc,
                "boll_ok": boll_ok,   "boll_desc": boll_desc,
                # 交易价值
                "trade_rating":   trade_eval["rating"],
                "trade_advice":   trade_eval["advice"],
                "trade_rr":       trade_eval["rr_ratio"],
                "trade_tp_cons":  trade_eval["tp_conservative"],
                "trade_tp_std":   trade_eval["tp_standard"],
                "trade_tp_agg":   trade_eval["tp_aggressive"],
                "trade_risk_per": trade_eval["risk_per_unit"],
                "trade_conf":     trade_eval["confidence"],
                "trade_risks":    trade_eval["risk_notes"],
                # 仓位建议
                "pos_lots":    pos["lots"],
                "pos_margin":  pos["margin"],
                "pos_ratio":   pos["position_ratio"],
                "pos_leverage":pos["leverage"],
                "pos_risk_u":  pos["risk_amount"],
            }

    return None

