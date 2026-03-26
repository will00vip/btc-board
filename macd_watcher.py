# ================================================================
# MACD 金叉/死叉独立监控模块
# 每次扫描时自动检测15分钟K线的MACD状态变化
# 金叉（DIF上穿DEA）→ 推送做多提示
# 死叉（DIF下穿DEA）→ 推送做空提示
# ================================================================

import logging
from datetime import datetime, timezone, timedelta
import pandas as pd

from signal_detector import calc_macd

logger = logging.getLogger("btc_monitor")

CST = timezone(timedelta(hours=8))

# ── 状态记录 ────────────────────────────────────────────────────
# 记录上一次扫描的MACD叉口状态，用于检测穿越事件
_macd_state = {
    "last_cross":      None,    # "golden" | "dead" | None
    "last_cross_time": None,    # datetime，上次叉口发生时间
    "last_dif":        None,    # 上一次扫描的DIF值
    "last_dea":        None,    # 上一次扫描的DEA值
    "last_push_cross": None,    # 最后一次推送的叉口类型，防重推
    "last_push_time":  None,    # 最后一次推送时间
}

# 同类型叉口最短推送间隔（分钟），防止震荡区间反复推
CROSS_COOLDOWN_MINUTES = 30


def detect_macd_cross(df: pd.DataFrame) -> dict | None:
    """
    检测MACD金叉/死叉事件
    返回：
      None         → 无新叉口
      dict         → 新叉口详情
        type:      "golden" | "dead"
        dif:       当前DIF值
        dea:       当前DEA值
        bar:       当前MACD柱
        prev_dif:  前一根DIF
        prev_dea:  前一根DEA
        strength:  叉口强度描述
        time:      发生时间字符串
    """
    if len(df) < 30:
        return None

    dif, dea, macd_bar = calc_macd(df["close"])

    curr_dif = dif.iloc[-1]
    curr_dea = dea.iloc[-1]
    prev_dif = dif.iloc[-2]
    prev_dea = dea.iloc[-2]
    curr_bar = macd_bar.iloc[-1]

    # 判断当前叉口类型
    if curr_dif >= curr_dea and prev_dif < prev_dea:
        cross_type = "golden"   # 金叉：DIF从下方穿越DEA
    elif curr_dif <= curr_dea and prev_dif > prev_dea:
        cross_type = "dead"     # 死叉：DIF从上方穿越DEA
    else:
        return None  # 无新叉口

    # ── 冷却检查：同类型叉口30分钟内不重复推 ──
    last_cross = _macd_state.get("last_push_cross")
    last_time  = _macd_state.get("last_push_time")
    now = datetime.now(CST)
    if (last_cross == cross_type and last_time is not None and
            (now - last_time) < timedelta(minutes=CROSS_COOLDOWN_MINUTES)):
        logger.info(f"[MACD去重] {cross_type}叉口{CROSS_COOLDOWN_MINUTES}分钟内已推过，跳过")
        return None

    # ── 叉口强度评估 ──
    cross_dist = abs(curr_dif - curr_dea)   # DIF与DEA的距离
    if cross_dist > 100:
        strength = "强势"
    elif cross_dist > 30:
        strength = "中等"
    else:
        strength = "弱"

    # ── 零轴位置判断 ──
    if cross_type == "golden":
        if curr_dif < 0:
            axis_desc = "零轴下方金叉（超卖区反转，力度更强）"
        else:
            axis_desc = "零轴上方金叉（多头延续）"
    else:
        if curr_dif > 0:
            axis_desc = "零轴上方死叉（超买区转弱，力度更强）"
        else:
            axis_desc = "零轴下方死叉（空头延续）"

    return {
        "type":      cross_type,
        "dif":       round(curr_dif, 2),
        "dea":       round(curr_dea, 2),
        "bar":       round(curr_bar, 2),
        "prev_dif":  round(prev_dif, 2),
        "prev_dea":  round(prev_dea, 2),
        "strength":  strength,
        "axis_desc": axis_desc,
        "time":      now.strftime("%m月%d日 %H:%M"),
    }


def format_macd_message(cross: dict, current_price: float) -> tuple[str, str]:
    """
    格式化MACD叉口推送内容
    """
    is_golden = cross["type"] == "golden"
    emoji     = "🟢" if is_golden else "🔴"
    name      = "金叉" if is_golden else "死叉"
    dir_hint  = "📈 看多信号" if is_golden else "📉 看空信号"
    action    = "考虑做多" if is_golden else "考虑做空"

    title = f"{emoji} BTC MACD {name} | {current_price:,.0f}U | {cross['strength']}叉"

    lines = [
        f"━━ {emoji} MACD {name}  {dir_hint} ━━",
        f"时间：{cross['time']}",
        f"价格：{current_price:,.1f} USDT",
        f"",
        f"【叉口数据】",
        f"  DIF：{cross['prev_dif']} → {cross['dif']}",
        f"  DEA：{cross['prev_dea']} → {cross['dea']}",
        f"  MACD柱：{cross['bar']}",
        f"  强度：{cross['strength']}叉",
        f"  位置：{cross['axis_desc']}",
        f"",
        f"【操作参考】",
        f"  ➡ {action}，结合K线形态确认",
        f"  ➡ 插针信号 + MACD叉口 = 最强共振",
        f"  ➡ 无插针时轻仓或仅观察",
        f"",
        f"⚠️ MACD叉口存在滞后，请结合价格形态判断",
    ]

    return title, "\n".join(lines)


def update_macd_push_state(cross_type: str) -> None:
    """推送成功后更新状态"""
    _macd_state["last_push_cross"] = cross_type
    _macd_state["last_push_time"]  = datetime.now(CST)


def get_macd_status_line(df: pd.DataFrame) -> str:
    """
    返回当前MACD状态的一行摘要（用于日志）
    格式：MACD DIF:xxx DEA:xxx [金叉中/死叉中/零轴上/零轴下]
    """
    if len(df) < 30:
        return "MACD: 数据不足"
    dif, dea, macd_bar = calc_macd(df["close"])
    curr_dif = round(dif.iloc[-1], 1)
    curr_dea = round(dea.iloc[-1], 1)
    curr_bar = round(macd_bar.iloc[-1], 1)

    if curr_dif > curr_dea:
        cross_status = "多头排列" if curr_dif > 0 else "零轴下多头"
    else:
        cross_status = "空头排列" if curr_dif < 0 else "零轴上空头"

    return f"MACD | DIF:{curr_dif} DEA:{curr_dea} 柱:{curr_bar} [{cross_status}]"
