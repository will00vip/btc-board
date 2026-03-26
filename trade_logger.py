# ================================================================
# 交易记录 & 复盘统计模块
# 功能：
#   1. 每次信号推送后自动写入 CSV 记录
#   2. 支持手动回填结果（盈/亏/平）
#   3. 月度统计：胜率、盈亏比、最大单笔盈亏、最大连亏
#   4. 哪些指标组合胜率最高
# 使用：
#   python trade_logger.py          → 打印本月统计
#   python trade_logger.py fill     → 回填最近未记录结果
#   python trade_logger.py month 2026-03  → 指定月份统计
# ================================================================

import csv
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

CST = timezone(timedelta(hours=8))
LOG_DIR  = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, "trade_records.csv")

FIELDNAMES = [
    "id", "time", "direction", "entry_price", "stop_loss",
    "tp1", "tp2", "tp3", "score", "level",
    "macd_ok", "kdj_ok", "rsi_ok", "wr_ok", "boll_ok",
    "trend_1h", "trend_4h",
    "result",      # win / loss / skip / -（未填）
    "exit_price",  # 出场价格
    "pnl_u",       # 盈亏U数（正=盈，负=亏）
    "note",        # 备注
]


def _ensure_file():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def _next_id() -> int:
    _ensure_file()
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return len(rows) + 1


def log_signal(signal: dict, trend: dict) -> int:
    """
    信号触发时自动写入一条记录（result 先留空 "-"）
    返回记录 ID，供后续回填
    """
    _ensure_file()
    rec_id = _next_id()
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    row = {
        "id":          rec_id,
        "time":        now,
        "direction":   signal.get("direction", ""),
        "entry_price": signal.get("entry_price", ""),
        "stop_loss":   signal.get("stop_loss", ""),
        "tp1":         signal.get("trade_tp_cons", ""),
        "tp2":         signal.get("trade_tp_std", ""),
        "tp3":         signal.get("trade_tp_agg", ""),
        "score":       signal.get("score", ""),
        "level":       signal.get("level", ""),
        "macd_ok":     int(signal.get("macd_ok", False)),
        "kdj_ok":      int(signal.get("kdj_ok", False)),
        "rsi_ok":      int(signal.get("rsi_ok", False)),
        "wr_ok":       int(signal.get("wr_ok", False)),
        "boll_ok":     int(signal.get("boll_ok", False)),
        "trend_1h":    trend.get("1h", ""),
        "trend_4h":    trend.get("4h", ""),
        "result":      "-",
        "exit_price":  "",
        "pnl_u":       "",
        "note":        "",
    }
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(row)
    return rec_id


def fill_result(rec_id: int, result: str, exit_price: float, pnl_u: float, note: str = "") -> bool:
    """
    回填交易结果
    result: "win" / "loss" / "skip"
    """
    _ensure_file()
    rows = []
    found = False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row["id"]) == rec_id:
                row["result"]     = result
                row["exit_price"] = exit_price
                row["pnl_u"]      = pnl_u
                row["note"]       = note
                found = True
            rows.append(row)

    if found:
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
    return found


def monthly_stats(month: Optional[str] = None) -> str:
    """
    生成月度统计报告
    month: "2026-03" 格式，默认当月
    """
    _ensure_file()
    if month is None:
        month = datetime.now(CST).strftime("%Y-%m")

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["time"].startswith(month)]

    total    = len(rows)
    filled   = [r for r in rows if r["result"] in ("win", "loss", "skip")]
    wins     = [r for r in filled if r["result"] == "win"]
    losses   = [r for r in filled if r["result"] == "loss"]
    skips    = [r for r in filled if r["result"] == "skip"]

    if total == 0:
        return f"[{month}] 暂无信号记录"

    win_rate = len(wins) / len(filled) * 100 if filled else 0

    pnl_list  = [float(r["pnl_u"]) for r in filled if r["pnl_u"] not in ("", "-")]
    total_pnl = sum(pnl_list)
    avg_win   = sum(p for p in pnl_list if p > 0) / max(len(wins), 1)
    avg_loss  = sum(abs(p) for p in pnl_list if p < 0) / max(len(losses), 1)
    rr_actual = avg_win / avg_loss if avg_loss > 0 else 0
    max_win   = max((p for p in pnl_list if p > 0), default=0)
    max_loss  = min((p for p in pnl_list if p < 0), default=0)

    # 最大连亏
    max_consec = 0
    cur_consec = 0
    for r in filled:
        if r["result"] == "loss":
            cur_consec += 1
            max_consec = max(max_consec, cur_consec)
        else:
            cur_consec = 0

    # 指标组合胜率（只看已填结果的信号）
    ind_stats: dict[str, list] = {}
    for r in filled:
        key = f"MACD{'✅' if r['macd_ok']=='1' else '❌'} KDJ{'✅' if r['kdj_ok']=='1' else '❌'} RSI{'✅' if r['rsi_ok']=='1' else '❌'}"
        ind_stats.setdefault(key, []).append(r["result"])

    ind_lines = []
    for combo, results in sorted(ind_stats.items(), key=lambda x: -len(x[1])):
        w = results.count("win")
        total_c = len([x for x in results if x in ("win","loss")])
        wr = w / total_c * 100 if total_c else 0
        ind_lines.append(f"  {combo}  {w}/{total_c}笔  胜率{wr:.0f}%")

    lines = [
        f"═══════════ {month} 复盘统计 ═══════════",
        f"信号总数：{total}  已填结果：{len(filled)}  跳过：{len(skips)}",
        f"胜率：{win_rate:.1f}%  盈 {len(wins)} 亏 {len(losses)}",
        f"实际盈亏比：{rr_actual:.2f}  总盈亏：{total_pnl:+.1f}U",
        f"最大盈利：+{max_win:.1f}U  最大亏损：{max_loss:.1f}U",
        f"最大连亏：{max_consec}笔",
        f"",
        f"── 指标组合胜率 ──",
    ] + ind_lines + [
        f"══════════════════════════════════",
    ]
    return "\n".join(lines)


def fill_interactive():
    """交互式回填最近未填结果"""
    _ensure_file()
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["result"] == "-"]

    if not rows:
        print("没有未填结果的记录。")
        return

    print(f"\n共 {len(rows)} 条未填记录：")
    for r in rows[-10:]:  # 最多显示最近10条
        print(f"  #{r['id']}  {r['time']}  {r['direction']}  进场:{r['entry_price']}  止损:{r['stop_loss']}  分:{r['score']}")

    while True:
        raw = input("\n输入记录ID（回车跳过）: ").strip()
        if not raw:
            break
        try:
            rec_id = int(raw)
        except ValueError:
            print("无效ID")
            continue

        result = input("结果 [win/loss/skip]: ").strip().lower()
        if result not in ("win", "loss", "skip"):
            print("无效结果，跳过")
            continue

        exit_p = input("出场价格: ").strip()
        pnl    = input("盈亏U数（盈正亏负）: ").strip()
        note   = input("备注（可空）: ").strip()

        try:
            ok = fill_result(rec_id, result, float(exit_p), float(pnl), note)
            print(f"{'✅ 已更新' if ok else '❌ 未找到记录'} #{rec_id}")
        except ValueError:
            print("格式错误，跳过")


# ── 命令行入口 ──────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "stats":
        month = args[1] if len(args) > 1 else None
        print(monthly_stats(month))
    elif args[0] == "fill":
        fill_interactive()
    elif args[0] == "month" and len(args) > 1:
        print(monthly_stats(args[1]))
    else:
        print("用法：")
        print("  python trade_logger.py           # 本月统计")
        print("  python trade_logger.py month 2026-03  # 指定月份统计")
        print("  python trade_logger.py fill      # 交互式回填结果")
