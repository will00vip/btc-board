// ───────────────────────────────────────────────
// 数据获取 + 信号检测  v4
// ───────────────────────────────────────────────
const { macd, kdj, rsi, wr, boll, calcScore } = require('./indicators')
const CONFIG = require('../config')

// 数据源列表使用配置中的DATA_SOURCES
const SOURCES = CONFIG.DATA_SOURCES || []

/** wx.request 封装成 Promise，带超时 */
function fetchJson(url, timeout = 6000) {
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

// 内存缓存（30s内复用，切换周期时清空）
const _cache = {}
function getCacheKey(interval) { return interval }
function getCached(interval) {
  const c = _cache[getCacheKey(interval)]
  if (c && Date.now() - c.ts < 30000) return c.data
  return null
}
function setCache(interval, data) {
  _cache[getCacheKey(interval)] = { ts: Date.now(), data }
}
function clearCache(interval) {
  if (interval) delete _cache[getCacheKey(interval)]
  else Object.keys(_cache).forEach(k => delete _cache[k])
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

/** 仓位计算器（根据止损距离计算最优仓位） */
function calcPositionSize(entryPrice, stopLoss, config = CONFIG) {
  const {
    ACCOUNT_BALANCE: account,
    RISK_PER_TRADE: riskPct,
    MAX_POSITION_PCT: maxPosPct,
    CONTRACT_SIZE: contractSize,
    DEFAULT_LEVERAGE: leverage,
  } = config
  
  const riskAmount = account * riskPct          // 本次愿意亏的最多U数
  let slDistance = Math.abs(entryPrice - stopLoss)
  if (slDistance <= 0) {
    slDistance = entryPrice * 0.005
  }

  // 每张合约价值（U本位）= entryPrice × contractSize
  const contractValue = entryPrice * contractSize

  // 不带杠杆时，N张止损亏损 = N × contractSize × slDistance
  // 带杠杆：所需保证金 = N × contractValue / leverage
  let lots = riskAmount / (contractSize * slDistance)
  lots = Math.max(1, Math.round(lots))  // 最少1张

  let margin = lots * contractValue / leverage
  let positionRatio = margin / account

  // 防止超过最大仓位限制
  const maxMargin = account * maxPosPct
  if (margin > maxMargin) {
    lots = Math.max(1, Math.floor(maxMargin * leverage / contractValue))
    margin = lots * contractValue / leverage
    positionRatio = margin / account
  }

  return {
    lots:           lots,
    margin:         Math.round(margin * 10) / 10,
    positionRatio:  Math.round(positionRatio * 100 * 10) / 10,
    leverage:       leverage,
    riskAmount:     Math.round(riskAmount * 10) / 10,
    slDistance:     Math.round(slDistance * 10) / 10,
  }
}

/** 主检测函数，返回完整分析对象 */
async function detectSignal(interval) {
  interval = interval || '15m'
  const limit = 150   // 150根足够指标计算+展示，比200快

  // 命中缓存直接返回（30s内）
  const cached = getCached(interval)
  if (cached) return cached

  // 4h额外数据：只在非4h以上周期时拉取，减少请求
  const need4h = !['4h','6h','12h','1d','3d','1w'].includes(interval)
  const reqs = [fetchKlines(interval, limit)]
  if (need4h) reqs.push(fetchKlines('4h', 10))
  
  const results = await Promise.all(reqs)
  const bars  = results[0]
  const bars4h = results[1] || bars.slice(-10)

  const now = new Date()
  const h = now.getHours()

  // 凌晨过滤（根据配置）
  if (CONFIG.FILTER_NIGHT_HOURS && h >= CONFIG.NIGHT_HOURS_START && h < CONFIG.NIGHT_HOURS_END) {
    return { type: 'filtered', reason: `凌晨时段(${CONFIG.NIGHT_HOURS_START}-${CONFIG.NIGHT_HOURS_END}点)`, bars, bars4h }
  }

  // 4h暴跌过滤（根据配置）
  const b4hPrev = bars4h[bars4h.length - 2]
  const b4hLast = bars4h[bars4h.length - 1]
  const drop4h = (b4hLast.close - b4hPrev.open) / b4hPrev.open * 100
  if (CONFIG.FILTER_4H_CRASH && drop4h < CONFIG.MAX_4H_DROP_PCT) {
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
  const isLongPin  = lowerShadow >= body * CONFIG.PIN_SHADOW_RATIO && pin.close > (pin.low  + kRange * 0.5)
  const isShortPin = upperShadow >= body * CONFIG.PIN_SHADOW_RATIO && pin.close < (pin.high - kRange * 0.5)

  // C2: 低/高点确认
  const c2Long  = conf.low  > pin.low  && conf.close > conf.open
  const c2Short = conf.high < pin.high && conf.close < conf.open

  // C3: 放量
  const prev5vol = bars.slice(bars.length - 7, bars.length - 2).map(b => b.volume)
  const avgVol   = prev5vol.reduce((a, b) => a + b) / prev5vol.length
  const c3       = pin.volume >= avgVol * CONFIG.VOLUME_AMPLIFY_RATIO

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

  // 仓位建议（如果有信号）
  let positionAdvice = null
  if (signalType && (signalType === 'long' || signalType === 'short')) {
    const entryPrice = conf.close
    const stopLoss = signalType === 'long' ? pin.low * 0.998 : pin.high * 1.002
    positionAdvice = calcPositionSize(entryPrice, stopLoss, CONFIG)
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
    // 仓位建议
    positionAdvice,
    // 原始指标数组
    macdData, kdjData, rsiArr, wrArr, bollArr
  }
  // 写入缓存
  setCache(interval, result)
  return result
}

module.exports = { fetchKlines, detectSignal, clearSignalCache: clearCache }
