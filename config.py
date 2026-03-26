# ================================================================
# BTC插针放量反转监控系统 — 配置文件
# 使用币安（Binance）API，国内网络直连
# ================================================================

# ── 交易所配置 ──
EXCHANGE = "htx"
SYMBOL = "btcusdt"          # 交易对（内部使用，会转为大写）
INTERVAL = "15min"          # K线周期：15分钟
CHECK_INTERVAL = 60 * 15    # 每15分钟检查一次（秒）

# ── 火币 HTX API Key（只读权限，公开行情无需Key，留作备用鉴权）──
HTX_ACCESS_KEY = "39e5870b-c24946b1-vfd5ghr532-ff3c3"
HTX_SECRET_KEY = "67ceaebe-d561fcd4-a676d541-f6423"

# ── 信号判断参数 ──
PIN_BAR_RATIO = 1.5         # 下影线长度 / 实体长度 最小倍数
CLOSE_POSITION_RATIO = 0.4  # 收盘价须高于K线总长度的40%位置
VOLUME_AMPLIFY_RATIO = 1.3  # 放量倍数：当根成交量 / 前5根均量
LOOKBACK_CANDLES = 5        # 成交量对比的参考K线数量

# ── 过滤规则 ──
MAX_DROP_4H_PCT = 8.0       # 过去4小时跌幅超过此值时，忽略信号（%）
NO_SIGNAL_HOURS = (0, 6)    # 凌晨此时间段内不推送（0点~6点）

# ── 微信推送配置（Server酱）──
# 获取方式：https://sct.ftqq.com/ 登录后复制你的SendKey
SERVERCHAN_KEY = "SCT328172T3Dbrhelvkng8k7jXdItahDfJ"

# ── 手机推送配置（PushDeer，Android震动提醒）──
# 获取方式：https://www.pushdeer.com/ 登录后复制PushKey
PUSHDEER_KEY = "PDU40148TxZdiIPWokKNhnK1UwmX6RiPuefuDi80f"

# ── 风控提示参数（推送信号时附带提醒）──
STOP_LOSS_BUFFER = 0.002    # 止损位 = 插针最低点 × (1 - 0.002)
TAKE_PROFIT_1 = 0.30        # 第一止盈：盈利30%
TAKE_PROFIT_2 = 0.50        # 第二止盈：盈利50%
MAX_LOSS_PCT = 0.10         # 单笔最大亏损：账户10%

# ================================================================
# ── 仓位管理参数（根据自己账户修改）──
# ================================================================
ACCOUNT_BALANCE   = 1000.0   # 账户总余额（USDT），根据实际修改
RISK_PER_TRADE    = 0.02     # 单笔风险比例（2% = 每笔最多亏账户2%）
MAX_POSITION_PCT  = 0.20     # 单笔最大仓位比例（账户20%以内）
CONTRACT_SIZE     = 0.001    # BTC合约每张面值（币本位=1BTC；U本位=0.001BTC，按交易所定）
DEFAULT_LEVERAGE  = 10       # 默认杠杆倍数（10x）

# ── 单日风控参数 ──
DAILY_MAX_LOSS_PCT   = 0.05  # 单日最大亏损：账户5%，超过当天停止推送
COOLDOWN_LOSS_COUNT  = 3     # 连续亏损N笔触发冷却
COOLDOWN_HOURS       = 2     # 冷却时间（小时）
