# ================================================================
# BTC插针放量反转监控系统 — 主程序 v3.0
# 运行方式：python main.py
# ================================================================

import time
import sys
import os
import logging
from datetime import datetime, timezone, timedelta

from config import (
    SYMBOL, INTERVAL, CHECK_INTERVAL,
    DAILY_MAX_LOSS_PCT, COOLDOWN_LOSS_COUNT, COOLDOWN_HOURS,
    ACCOUNT_BALANCE,
)
from data_fetcher import get_klines, get_price_change_pct, get_trend
from signal_detector import detect_signal
from notifier import send_all
from trade_logger import log_signal
from macd_watcher import detect_macd_cross, format_macd_message, update_macd_push_state, get_macd_status_line

CST = timezone(timedelta(hours=8))

# ── 日志配置 ──────────────────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(__file__), "monitor.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("btc_monitor")

# ── 信号去重：记录上次推送时间（方向 -> datetime） ─────────────────
_last_signal_time: dict[str, datetime] = {}
DEDUP_HOURS = 4   # 同方向信号 N 小时内只推一次

# ── 单日风控状态 ────────────────────────────────────────────────
_risk_state = {
    "today_date":       "",        # 当日日期字符串，用于跨日重置
    "today_loss_u":     0.0,       # 今日已亏损U数（手动回填，默认0）
    "consecutive_loss": 0,         # 连续亏损笔数
    "cooldown_until":   None,      # 冷却截止时间
}


def _risk_check() -> tuple[bool, str]:
    """
    风控检查，返回 (是否允许推送, 原因说明)
    风控状态需外部手动更新（见 update_risk_state 函数）
    """
    now = datetime.now(CST)
    today_str = now.strftime("%Y-%m-%d")

    # 跨日自动重置
    if _risk_state["today_date"] != today_str:
        _risk_state["today_date"]       = today_str
        _risk_state["today_loss_u"]     = 0.0
        _risk_state["consecutive_loss"] = 0
        _risk_state["cooldown_until"]   = None
        logger.info(f"[风控] 新的一天 {today_str}，风控状态已重置")

    # 冷却期检查
    if _risk_state["cooldown_until"] and now < _risk_state["cooldown_until"]:
        cd_end = _risk_state["cooldown_until"].strftime("%H:%M")
        return False, f"🧊 冷却期中（连亏{_risk_state['consecutive_loss']}笔），{cd_end}前暂停推送"

    # 单日亏损上限
    max_loss_u = ACCOUNT_BALANCE * DAILY_MAX_LOSS_PCT
    if _risk_state["today_loss_u"] >= max_loss_u:
        return False, f"🛑 今日已亏{_risk_state['today_loss_u']:.0f}U，达单日上限({max_loss_u:.0f}U)，今日停止推送"

    return True, ""


def update_risk_state(is_win: bool, pnl_u: float = 0.0) -> None:
    """
    外部调用：更新风控状态（每笔交易结果后调用）
    is_win: 盈利=True, 亏损=False
    pnl_u:  盈亏U数（亏损传负值）
    """
    if not is_win and pnl_u < 0:
        _risk_state["today_loss_u"] += abs(pnl_u)
        _risk_state["consecutive_loss"] += 1
        if _risk_state["consecutive_loss"] >= COOLDOWN_LOSS_COUNT:
            _risk_state["cooldown_until"] = datetime.now(CST) + timedelta(hours=COOLDOWN_HOURS)
            logger.warning(f"[风控] 连续亏损{_risk_state['consecutive_loss']}笔，冷却{COOLDOWN_HOURS}小时")
    else:
        _risk_state["consecutive_loss"] = 0  # 盈利则重置连亏计数


def _is_duplicate(direction: str) -> bool:
    """是否在去重窗口内（同方向 4 小时内已推过）"""
    last = _last_signal_time.get(direction)
    if last is None:
        return False
    return (datetime.now(CST) - last) < timedelta(hours=DEDUP_HOURS)


def _mark_sent(direction: str) -> None:
    _last_signal_time[direction] = datetime.now(CST)


# ── 推送内容格式化 ─────────────────────────────────────────────────

def format_signal_message(signal: dict, drop_pct: float, trend: dict) -> tuple[str, str]:
    """格式化推送内容 —— 三步法v4.1版"""
    score     = signal.get("score", 0)       # 12分制，硬上限12
    score_100 = signal.get("score_100", 0)   # 100分制（与App对齐）
    level     = signal.get("level", "⚡信号")
    rating    = signal.get("trade_rating", "")
    direction = signal.get("direction", "long")
    dir_emoji = "📈做多" if direction == "long" else "📉做空"
    dir_label = "买入" if direction == "long" else "卖出"

    daily_trend     = signal.get("daily_trend", "neutral")
    daily_trend_cn  = signal.get("daily_trend_cn", "↔️震荡")
    price_vs_ema50  = signal.get("price_vs_ema50", 0.0)
    h1_ok           = signal.get("h1_resonance", False)
    h1_desc         = signal.get("h1_desc", "—")
    h1_rsi          = signal.get("h1_rsi", 50.0)
    h1_icon         = "✅" if h1_ok else "⏳"
    consecutive_pins    = signal.get("consecutive_pins", 1)
    consecutive_penalty = signal.get("consecutive_penalty", 0)

    # 三步法完成情况
    step1_ok = daily_trend not in ("neutral",)
    step2_ok = h1_ok
    step3_ok = True
    steps_done = sum([step1_ok, step2_ok, step3_ok])

    # 超跌/超涨逆势标记
    contrarian_note = ""
    if daily_trend == "overdip":
        contrarian_note = f"  ⚠️ 逆势做多（超跌{price_vs_ema50:.1f}%）信号，止损要严格"
    elif daily_trend == "overblow":
        contrarian_note = f"  ⚠️ 逆势做空（超涨+{price_vs_ema50:.1f}%）信号，止损要严格"

    # 连续插针降权提示
    pin_note = ""
    if consecutive_pins >= 3:
        pin_note = f"  ⚠️ 同区域已出现{consecutive_pins}根插针，反转质量递减-扣{consecutive_penalty}分"

    # ── 标题 ──────────────────────────────────────────────────
    title = f"🔔BTC{dir_label}【{score}/12 | {score_100}/100】{level} | {signal['entry_price']:,.0f}U"

    # ── 环境提示 ──────────────────────────────────────────────
    now_hour = datetime.now(CST).hour
    time_tip = ""
    if 0 <= now_hour < 6:
        time_tip = "🌙 凌晨信号，流动性低，谨慎操作"
    elif 20 <= now_hour or now_hour < 2:
        time_tip = "🇺🇸 美股时段，波动较大"

    drop_tip = ""
    if drop_pct < -5:
        drop_tip = f"⚠️ 近4H急跌{drop_pct:.1f}%，轻仓试"
    elif drop_pct > 5:
        drop_tip = f"⚠️ 近4H急涨{drop_pct:.1f}%，做空需防假突破"

    risk_notes = signal.get("trade_risks", [])
    risk_lines = [f"  {r}" for r in risk_notes] if risk_notes else ["  ✅ 无额外风险"]

    conf_label = ("低点抬高✅" if direction == "long" else "高点下降✅") \
        if signal.get("extreme_confirmed") \
        else ("低点待确认⏳" if direction == "long" else "高点待确认⏳")

    lines = [
        # ── 核心决策 ──────────────────────────────────────────
        f"━━ {dir_emoji} 插针{dir_label}  {level} ━━",
        f"评分：{score}/12  ≈App {score_100}/100  三步法{steps_done}/3步",
        f"价格：{signal['entry_price']:,.1f}  时间：{signal['time']}",
        f"止损：{signal['stop_loss']:,.1f}  每U风险：{signal.get('trade_risk_per',0):.1f}",
        f"TP1 {signal.get('trade_tp_cons',0):,.0f}  TP2 {signal.get('trade_tp_std',0):,.0f}  TP3 {signal.get('trade_tp_agg',0):,.0f}",
        f"→ {rating}",
        f"",
        # ── 三步法状态 ────────────────────────────────────────
        f"【三步法共振】",
        f"  步骤1 大趋势：{daily_trend_cn}",
        f"  步骤2 1h共振：{h1_icon} {h1_desc}",
        f"  步骤3 15m触发：✅ 插针{signal['shadow_ratio']}倍 量{signal['volume_ratio']}倍",
        f"  {conf_label}",
    ]

    if contrarian_note:
        lines.append(contrarian_note)
    if pin_note:
        lines.append(pin_note)

    lines += [
        f"",
        # ── 仓位建议 ──────────────────────────────────────────
        f"【仓位建议】",
        f"  开仓：{signal.get('pos_lots',1)}张  保证金：{signal.get('pos_margin',0):.0f}U ({signal.get('pos_ratio',0):.1f}%仓位)",
        f"  杠杆：{signal.get('pos_leverage',10)}x  最大亏损：{signal.get('pos_risk_u',0):.0f}U",
        f"",
        # ── 大趋势背景 ────────────────────────────────────────
        f"【大趋势背景】",
        f"  1H：{trend.get('1h','—')}  |  4H：{trend.get('4h','—')}",
        f"  {trend.get('bias','—')}",
    ]

    if time_tip:
        lines.append(f"  {time_tip}")
    if drop_tip:
        lines.append(f"  {drop_tip}")

    lines += [
        f"",
        # ── 指标详情 ──────────────────────────────────────────
        f"【指标详情  {score}/12分 | 1h RSI={h1_rsi}】",
        f"  收盘位置：{signal['close_position']}%",
        f"  MACD：{signal['macd_desc']}",
        f"  KDJ ：{signal['kdj_desc']}",
        f"  RSI ：{signal['rsi_desc']}",
        f"  WR  ：{signal['wr_desc']}",
        f"  BOLL：{signal['boll_desc']}",
        f"",
        f"【风险提示】",
    ] + risk_lines + [
        f"",
        f"⚡ 核对SOP → 决策 → 挂止损单",
    ]

    return title, "\n".join(lines)


# ── 主扫描逻辑 ────────────────────────────────────────────────────

def run_once() -> None:
    logger.info(f"{'='*50}")
    logger.info(f"扫描 BTC/USDT {INTERVAL} K线...")

    df = get_klines(SYMBOL, INTERVAL, limit=60)
    if df.empty:
        logger.error("[错误] 获取K线数据失败，跳过本次扫描")
        return

    current_price = df.iloc[-1]["close"]
    logger.info(f"当前价格: {current_price:,.1f} USDT")

    drop_pct = get_price_change_pct(SYMBOL, hours=4)
    logger.info(f"4小时涨跌: {drop_pct:+.1f}%")

    # ── 拉取日线和1h数据（用于三步法共振） ─────────────────────
    df_daily, df_1h = None, None
    try:
        df_daily = get_klines(SYMBOL, "1day", limit=60)
        if not df_daily.empty:
            logger.info(f"[三步法] 日线数据加载成功 ({len(df_daily)}根)")
    except Exception as e:
        logger.warning(f"[三步法] 日线数据失败: {e}")

    try:
        df_1h = get_klines(SYMBOL, "60min", limit=100)
        if not df_1h.empty:
            logger.info(f"[三步法] 1h数据加载成功 ({len(df_1h)}根)")
    except Exception as e:
        logger.warning(f"[三步法] 1h数据失败: {e}")

    # ── MACD状态日志 ────────────────────────────────────────────
    logger.info(get_macd_status_line(df))

    # ══════════════════════════════════════════════════════════
    # ① MACD 金叉/死叉独立监控（无需插针，有叉就推）
    # ══════════════════════════════════════════════════════════
    macd_cross = detect_macd_cross(df)
    if macd_cross:
        cross_name = "金叉📈" if macd_cross["type"] == "golden" else "死叉📉"
        logger.info(f"🔔 MACD {cross_name}！强度:{macd_cross['strength']}  DIF:{macd_cross['dif']} DEA:{macd_cross['dea']}")
        m_title, m_content = format_macd_message(macd_cross, current_price)
        send_all(m_title, m_content)
        update_macd_push_state(macd_cross["type"])
    else:
        logger.info("MACD：无新叉口")

    # ══════════════════════════════════════════════════════════
    # ② 三步法插针形态检测（日线趋势 + 1h共振 + 15m插针）
    # ══════════════════════════════════════════════════════════
    signal = detect_signal(df, drop_4h=drop_pct, df_daily=df_daily, df_1h=df_1h)

    if signal and signal.get("found"):
        direction = signal.get("direction", "long")
        score     = signal.get("score", 0)
        logger.info(f"🔔 发现信号！方向:{direction} 综合得分:{score}/10 {signal.get('level','')}")

        if _is_duplicate(direction):
            last = _last_signal_time[direction].strftime("%H:%M")
            logger.info(f"[去重] {direction} 方向在 {last} 已推过，{DEDUP_HOURS}小时内不重复推送")
            return

        # ── 风控检查 ──────────────────────────────────────────────
        risk_ok, risk_msg = _risk_check()
        if not risk_ok:
            logger.warning(f"[风控拦截] {risk_msg}")
            send_all(f"[风控] BTC有信号但被拦截", risk_msg)  # 依然推一条风控通知
            return

        # 获取趋势（允许失败）
        try:
            trend = get_trend(SYMBOL)
            logger.info(f"趋势: 1H={trend['1h']} 4H={trend['4h']} | {trend['bias']}")
        except Exception as e:
            logger.warning(f"趋势获取失败: {e}")
            trend = {"1h": "—", "4h": "—", "bias": "—"}

        title, content = format_signal_message(signal, drop_pct, trend)
        logger.info(content)
        send_all(title, content)
        _mark_sent(direction)

        # 自动写入交易记录
        rec_id = log_signal(signal, trend)
        logger.info(f"✅ 推送完成 | 记录已写入 #{rec_id}（事后用 python trade_logger.py fill 回填结果）")
    else:
        logger.info("无信号（插针形态或放量条件未满足）")


def main():
    logger.info("=" * 50)
    logger.info("  BTC插针放量反转监控系统 v3.0")
    logger.info(f"  监控品种: {SYMBOL.upper()}")
    logger.info(f"  K线周期: {INTERVAL}")
    logger.info(f"  扫描间隔: {CHECK_INTERVAL // 60} 分钟")
    logger.info(f"  指标体系: MACD + KDJ + RSI + WR + BOLL")
    logger.info(f"  推送条件: 三步法 ≥5/12分（≈App 42分）才推送")
    logger.info(f"  信号去重: 同方向 {DEDUP_HOURS}H 内不重复")
    logger.info(f"  趋势判断: 1H + 4H 双周期 EMA20/EMA50")
    logger.info("=" * 50)
    logger.info("按 Ctrl+C 停止\n")

    run_once()

    while True:
        try:
            next_time = (datetime.now(CST) + timedelta(seconds=CHECK_INTERVAL)).strftime("%H:%M:%S")
            logger.info(f"下次扫描: {next_time}")
            time.sleep(CHECK_INTERVAL)
            run_once()
        except KeyboardInterrupt:
            logger.info("\n[停止] 监控程序已手动停止")
            sys.exit(0)
        except Exception as e:
            logger.error(f"[异常] {e}，60秒后重试...")
            time.sleep(60)


if __name__ == "__main__":
    main()
