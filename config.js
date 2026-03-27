// config.js - 小程序配置参数
// 用户可根据自己账户情况修改这些参数

module.exports = {
  // 仓位管理参数
  ACCOUNT_BALANCE: 1000.0,   // 账户总余额（USDT），根据实际修改
  RISK_PER_TRADE: 0.02,      // 单笔风险比例（2% = 每笔最多亏账户2%）
  MAX_POSITION_PCT: 0.20,    // 单笔最大仓位比例（账户20%以内）
  CONTRACT_SIZE: 0.001,      // BTC合约每张面值（币本位=1BTC；U本位=0.001BTC，按交易所定）
  DEFAULT_LEVERAGE: 10,      // 默认杠杆倍数（10x）
  
  // 单日风控参数
  DAILY_MAX_LOSS_PCT: 0.05,  // 单日最大亏损：账户5%，超过当天停止推送
  COOLDOWN_LOSS_COUNT: 3,    // 连续亏损N笔触发冷却
  COOLDOWN_HOURS: 2,         // 冷却时间（小时）
  
  // 数据源配置
  DATA_SOURCES: [
    {
      name: '火币HTX',
      klineUrl: (iv, lim) => {
        // 完整14档周期映射（火币HTX支持的period值）
        const m = {
          '1m':'1min','3m':'3min','5m':'5min','15m':'15min','30m':'30min',
          '1h':'60min','2h':'2hour','4h':'4hour','6h':'6hour','12h':'12hour',
          '1d':'1day','3d':'3day','1w':'1week',
          '1s':'1min'  // 秒线HTX不支持，降级到1min
        }
        return `https://api.huobi.pro/market/history/kline?symbol=btcusdt&period=${m[iv]||'15min'}&size=${lim}`
      },
      parse: raw => {
        const d = raw.data || raw
        if (!Array.isArray(d)) throw new Error('HTX格式错误')
        return d.reverse().map(k => ({
          time: k.id * 1000, open: k.open, high: k.high, low: k.low, close: k.close, volume: k.vol
        }))
      }
    },
    {
      name: '币安镜像',
      klineUrl: (iv, lim) => `https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=${iv}&limit=${lim}`,
      parse: raw => raw.map(k => ({
        time: k[0], open: +k[1], high: +k[2], low: +k[3], close: +k[4], volume: +k[5]
      }))
    }
  ],
  
  // 交易时间过滤
  FILTER_NIGHT_HOURS: true,   // 是否过滤凌晨时段（0-6点）
  NIGHT_HOURS_START: 0,       // 过滤开始时间
  NIGHT_HOURS_END: 6,         // 过滤结束时间
  
  // 4H暴跌过滤
  FILTER_4H_CRASH: true,      // 是否过滤4小时暴跌
  MAX_4H_DROP_PCT: -8,        // 4小时最大跌幅（百分比）
  
  // 插针信号参数
  PIN_SHADOW_RATIO: 1.5,      // 插针影线/实体比例
  VOLUME_AMPLIFY_RATIO: 1.3,  // 放量比例（当前量/5日均量）
  
  // 更新detector.js中的CONFIG引用，使用此配置文件
  // 在detector.js中修改：const CONFIG = require('./config')
}