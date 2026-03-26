// ───────────────────────────────────────────────
// 数据获取 + 信号检测  v2
// ───────────────────────────────────────────────
const { macd, kdj, rsi, wr, boll, calcScore } = require('./indicators')

// 数据源列表（依次尝试）— 火币HTX优先（有API Key更稳定）
const HTX_ACCESS_KEY = '39e5870b-c24946b1-vfd5ghr532-ff3c3'

const SOURCES = [
  {
    name: '火币HTX',
    klineUrl: (iv, lim) => {
      const m = { '1m':'1min','5m':'5min','15m':'15min','30m':'30min','1h':'60min','4h':'4hour','1d':'1day' }
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
]

/** wx.request 封装成 Promise，带超时 */
function fetchJson(url, timeout = 8000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('timeout')), timeout)
    wx.request({
      url,
      success: res => {
        clearTimeout(timer)
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          reject(new Error('HTTP ' + res.statusCode))
        }
      },
      fail: err => { clearTimeout(timer); reject(new Error(err.errMsg || 'request fail')) }
    })
  })
}

/** 多源拉K线，返回 bar 数组 */
async function fetchKlines(interval, limit) {
  let lastErr
  for (const src of SOURCES) {
    try {
      const raw = await fetchJson(src.klineUrl(interval, limit))
      const bars = src.parse(raw)
      if (bars && bars.length > 0) {
        console.log('[数据源]', src.name, bars.length, '根K线')
        return bars
      }
    } catch (e) {
      console.warn('[' + src.name + '] 失败:', e.message)
      lastErr = e
    }
  }
  throw new Error('所有数据源失败: ' + (lastErr ? lastErr.message : ''))
}

/** 主检测函数，返回完整分析对象 */
async function detectSignal(interval) {
  interval = interval || '15m'
  const limit = 200   // 拉足够多数据，支持左右拖动看历史

  const [bars, bars4h] = await Promise.all([
    fetchKlines(interval, limit),
    fetchKlines('4h', 10)
  ])

  const now = new Date()
  const h = now.getHours()

  // 凌晨过滤
  if (h >= 0 && h < 6) {
    return { type: 'filtered', reason: '凌晨时段(0-6点)', bars, bars4h }
  }

  // 4h暴跌过滤
  const b4hPrev = bars4h[bars4h.length - 2]
  const b4hLast = bars4h[bars4h.length - 1]
  const drop4h = (b4hLast.close - b4hPrev.open) / b4hPrev.open * 100
  if (drop4h < -8) {
    return { type: 'filtered', reason: `4小时跌幅${drop4h.toFixed(1)}%`, bars, bars4h, drop4h }
  }

  // 用已完结K线（倒数第2根）作为插针候选，倒数第1根为确认K线
  const pin  = bars[bars.length - 2]
  const conf = bars[bars.length - 1]

  const body        = Math.abs(pin.close - pin.open) || 0.01
  const lowerShadow = Math.min(pin.open, pin.close) - pin.low
  const upperShadow = pin.high - Math.max(pin.open, pin.close)
  const kRange      = pin.high - pin.low

  // C1: 下影插针（做多）/ 上影插针（做空）
  const isLongPin  = lowerShadow >= body * 1.5 && pin.close > (pin.low  + kRange * 0.5)
  const isShortPin = upperShadow >= body * 1.5 && pin.close < (pin.high - kRange * 0.5)

  // C2: 低/高点确认
  const c2Long  = conf.low  > pin.low  && conf.close > conf.open
  const c2Short = conf.high < pin.high && conf.close < conf.open

  // C3: 放量
  const prev5vol = bars.slice(bars.length - 7, bars.length - 2).map(b => b.volume)
  const avgVol   = prev5vol.reduce((a, b) => a + b) / prev5vol.length
  const c3       = pin.volume >= avgVol * 1.3

  // 技术指标
  const closes   = bars.map(b => b.close)
  const highs    = bars.map(b => b.high)
  const lows     = bars.map(b => b.low)
  const macdData = macd(closes)
  const kdjData  = kdj(highs, lows, closes)
  const rsiArr   = rsi(closes)
  const wrArr    = wr(highs, lows, closes)
  const bollArr  = boll(closes)
  const n        = closes.length - 1

  const macdBar  = macdData.bar[n]
  const macdPrev = macdData.bar[n - 1]
  const jVal     = kdjData.J[n]
  const rsiVal   = rsiArr[n]
  const wrVal    = wrArr[n]
  const bollLast = bollArr[n]

  // C4: MACD（做多：柱线止跌或金叉；做空：柱线止涨或死叉）
  const c4Long  = macdBar > macdPrev || (macdData.dif[n] > macdData.dea[n] && macdData.dif[n-1] <= macdData.dea[n-1])
  const c4Short = macdBar < macdPrev || (macdData.dif[n] < macdData.dea[n] && macdData.dif[n-1] >= macdData.dea[n-1])

  // 判断方向和是否完整信号
  let signalType = null
  if (isLongPin  && c2Long  && c3 && c4Long)  signalType = 'long'
  if (isShortPin && c2Short && c3 && c4Short) signalType = 'short'

  // 多空条件详情（供界面展示）
  const longConditions = [
    { label: '下影插针', ok: isLongPin,  tip: `下影${lowerShadow.toFixed(0)} vs 实体${body.toFixed(0)}` },
    { label: '低点抬高', ok: c2Long,     tip: conf.low > pin.low ? `确认低${conf.low.toFixed(0)}>插针低${pin.low.toFixed(0)}` : '未确认' },
    { label: '放量',     ok: c3,         tip: `量比${(pin.volume/avgVol).toFixed(2)}x` },
    { label: 'MACD配合', ok: c4Long,     tip: macdBar > 0 ? 'MACD多头' : 'MACD止跌' },
  ]
  const shortConditions = [
    { label: '上影插针', ok: isShortPin, tip: `上影${upperShadow.toFixed(0)} vs 实体${body.toFixed(0)}` },
    { label: '高点压制', ok: c2Short,    tip: conf.high < pin.high ? `确认高${conf.high.toFixed(0)}<插针高${pin.high.toFixed(0)}` : '未确认' },
    { label: '放量',     ok: c3,         tip: `量比${(pin.volume/avgVol).toFixed(2)}x` },
    { label: 'MACD配合', ok: c4Short,    tip: macdBar < 0 ? 'MACD空头' : 'MACD止涨' },
  ]

  // 综合评分
  let score = 0
  if (signalType) {
    score = calcScore(bars, macdData, kdjData, rsiArr, wrArr, bollArr, signalType)
  }

  return {
    type: signalType,
    bars, bars4h,
    drop4h,
    pin, conf,
    score,
    // 条件详情
    longConditions,
    shortConditions,
    isLongPin, isShortPin,
    lowerShadow, upperShadow, body,
    c2Long, c2Short, c3, c4Long, c4Short,
    avgVol,
    // 指标值
    macdBar, macdPrev,
    dif: macdData.dif[n], dea: macdData.dea[n],
    kVal: kdjData.K[n], dVal: kdjData.D[n], jVal,
    rsiVal, wrVal,
    bollLast,
    // 原始指标数组
    macdData, kdjData, rsiArr, wrArr, bollArr
  }
}

module.exports = { fetchKlines, detectSignal }
