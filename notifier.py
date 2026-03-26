# ================================================================
# 推送模块（Server酱微信 + PushDeer手机震动）
# ================================================================

import requests
from config import SERVERCHAN_KEY, PUSHDEER_KEY


SERVERCHAN_URL = "https://sctapi.ftqq.com/{key}.send"
PUSHDEER_URL   = "https://api2.pushdeer.com/message/push"


def send_wechat(title: str, content: str) -> bool:
    """
    通过Server酱推送微信消息
    :param title: 消息标题（微信通知栏显示）
    :param content: 消息正文（支持Markdown）
    :return: 是否推送成功
    """
    if not SERVERCHAN_KEY or SERVERCHAN_KEY == "你的Server酱SendKey填这里":
        print("[推送跳过] 未配置Server酱Key，请先在config.py中填写SERVERCHAN_KEY")
        return False

    url = SERVERCHAN_URL.format(key=SERVERCHAN_KEY)
    data = {
        "title": title,
        "desp": content
    }
    try:
        resp = requests.post(url, data=data, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            print(f"[微信推送成功] {title}")
            return True
        else:
            print(f"[微信推送失败] {result.get('message', '未知错误')}")
            return False
    except Exception as e:
        print(f"[微信推送异常] {e}")
        return False


def send_pushdeer(title: str, content: str) -> bool:
    """
    通过PushDeer推送手机通知（Android/iOS 均支持，有震动）
    :param title: 消息标题
    :param content: 消息正文
    :return: 是否推送成功
    """
    if not PUSHDEER_KEY or PUSHDEER_KEY == "你的PushDeer Key填这里":
        print("[PushDeer跳过] 未配置PUSHDEER_KEY")
        return False

    data = {
        "pushkey": PUSHDEER_KEY,
        "title":   title,
        "desp":    content,
        "text":    content,
        "type":    "markdown",
    }
    try:
        resp = requests.post(PUSHDEER_URL, data=data, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            print(f"[PushDeer推送成功] {title}")
            return True
        else:
            print(f"[PushDeer推送失败] {result}")
            return False
    except Exception as e:
        print(f"[PushDeer推送异常] {e}")
        return False


def send_all(title: str, content: str) -> None:
    """同时推送微信（Server酱）和手机（PushDeer），任一成功即可"""
    send_wechat(title, content)
    send_pushdeer(title, content)


def format_signal_message(signal: dict) -> tuple[str, str]:
    """
    格式化信号为微信消息
    :return: (标题, 正文)
    """
    stars = "⭐" * signal["conditions_met"]
    low_rising_text = "✅ 低点已抬高" if signal["low_rising"] else "⏳ 等待低点确认"

    title = f"🔔 BTC插针买入信号 {stars}"

    content = f"""
## 🔔 BTC/USDT 插针放量反转信号

**时间：** {signal['time']}  
**当前价格：** {signal['entry_price']:,.1f} USDT  
**信号强度：** {stars}（{signal['conditions_met']}/4条满足）

---

### 📊 信号详情
| 条件 | 状态 | 数值 |
|------|------|------|
| 下影插针 | ✅ | 下影/实体={signal['shadow_ratio']}倍，收盘位于{signal['close_position']}% |
| 放量确认 | ✅ | 当根成交量={signal['volume_ratio']}倍均量 |
| 低点抬高 | {low_rising_text} | - |
| MACD配合 | {'✅' if signal['macd_ok'] else '❌'} | {signal['macd_desc']} |

---

### 💰 操作参考（需人工核对SOP）
- **止损位：** {signal['stop_loss']:,.1f} USDT（插针最低点×0.998）
- **第一止盈：** {signal['tp1']:,.1f} USDT（+30%）
- **第二止盈：** {signal['tp2']:,.1f} USDT（+50%）

---

### ⚠️ 操作提醒
1. 请先人工核对SOP全部条件
2. 按仓位公式控制仓位大小
3. 买入同时设置好止损条件单
4. 凌晨0-6点信号谨慎操作

> 本信号由自动监控程序生成，仅供参考，不构成投资建议
"""
    return title, content


def format_no_signal_message(current_price: float, scan_time: str) -> tuple[str, str]:
    """格式化无信号消息（静默，不推送微信，仅本地打印）"""
    return "", f"[{scan_time}] 当前价格: {current_price:,.1f} USDT — 无信号，继续监控中"
