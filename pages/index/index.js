// pages/index/index.js  v6.1 - bugfix：去重import，清理dead code，止盈方向色修正，24h采样按周期动态计算
const { fetchKlines, detectSignal, detectMacdCross } = require('../../utils/detector')
const { macd: calcMACD, boll: calcBOLL, ema: calcEMA } = require('../../utils/indicators')

// 完整周期列表（对标交易所风格）
const PERIODS = [
  { iv: '1s',  label: '1秒',   limit: 500 },
  { iv: '1m',  label: '1分',   limit: 500 },
  { iv: '3m',  label: '3分',   limit: 500 },
  { iv: '5m',  label: '5分',   limit: 500 },
  { iv: '15m', label: '15分',  limit: 480 },
  { iv: '30m', label: '30分',  limit: 480 },
  { iv: '1h',  label: '1时',   limit: 480 },
  { iv: '2h',  label: '2时',   limit: 480 },
  { iv: '4h',  label: '4时',   limit: 300 },
  { iv: '6h',  label: '6时',   limit: 300 },
  { iv: '12h', label: '12时',  limit: 240 },
  { iv: '1d',  label: '1日',   limit: 240 },
  { iv: '3d',  label: '3日',   limit: 120 },
  { iv: '1w',  label: '1周',   limit: 100 },
]

const TIPS = [
  {
    icon: '🦐', title: '插针长啥样？',
    body: '下影线 ≥ 实体1.5倍\n像小龙虾伸出长须\n影线越长支撑越强 🎣',
    cls: 'tip-pin', tag: '形态识别'
  },
  {
    icon: '💥', title: '放量才算数',
    body: '量比 ≥ 1.3x 才有效\n无量插针 = 假动作\n量大 = 主力在接货 🐋',
    cls: 'tip-vol', tag: '放量确认'
  },
  {
    icon: '🚀', title: '做多三步走',
    body: '①下影插针K线收盘\n②下根低点不破前低\n③MACD柱不再创新低',
    cls: 'tip-long', tag: '做多策略'
  },
  {
    icon: '🔻', title: '做空三步走',
    body: '①上影插针K线收盘\n②下根高点不破前高\n③MACD柱不再创新高',
    cls: 'tip-short', tag: '做空策略'
  },
  {
    icon: '🛑', title: '止损怎么设',
    body: '做多：止损插针最低下方\n做空：止损插针最高上方\n超过0.5%亏损立刻出！',
    cls: 'tip-stop', tag: '风控必看'
  },
  {
    icon: '⚡', title: '评分这样看',
    body: '≥8分 🔥 强信号直接打\n5~7分 ⚠️ 轻仓谨慎进\n<5分 🚫 看书等机会',
    cls: 'tip-score', tag: '评分指南'
  },
  {
    icon: '⏰', title: '最佳交易时段',
    body: '14:00~22:00(北京时间)\n欧美重叠量最大最稳\n凌晨0~6点信号自动过滤',
    cls: 'tip-time', tag: '时段提示'
  },
  {
    icon: '⚖️', title: '盈亏比要够',
    body: 'TP1 = 止损距离 × 1倍\nTP2 = × 1.5倍（主目标）\nTP3 = × 2.5倍（留底仓）',
    cls: 'tip-rr', tag: '盈亏比'
  },
]

/**
 * 大趋势判断（基于4h K线数据）
 * 返回 { trend, trendLabel, trendColor, supportZone, resistZone, trendDesc }
 */
function calcTrend(bars) {
  if (!bars || bars.length < 20) return null
  const closes = bars.map(b => b.close)
  const n = closes.length

  // MA20 / MA60 简易计算
  const ma20 = closes.slice(-20).reduce((s,v)=>s+v,0)/20
  const ma60slice = closes.slice(-Math.min(60,n))
  const ma60 = ma60slice.reduce((s,v)=>s+v,0)/ma60slice.length
  const last = closes[n-1]

  // 近20根高低点
  const recent = bars.slice(-20)
  const highs = recent.map(b=>b.high)
  const lows  = recent.map(b=>b.low)
  const recentHigh = Math.max(...highs)
  const recentLow  = Math.min(...lows)

  // 支撑/压力区：取近20根的低点聚集区±0.3%
  const supportBase = recentLow
  const resistBase  = recentHigh

  // 判断趋势
  let trend = 'sideways', trendLabel = '震荡', trendColor = 'neutral'
  let trendDesc = ''

  if (last > ma20 && ma20 > ma60) {
    trend = 'up'; trendLabel = '多头趋势'; trendColor = 'bull'
    trendDesc = 'MA20>MA60 价格站上均线，多头占优'
  } else if (last < ma20 && ma20 < ma60) {
    trend = 'down'; trendLabel = '空头趋势'; trendColor = 'bear'
    trendDesc = 'MA20<MA60 价格跌破均线，空头占优'
  } else if (last > ma20) {
    trend = 'up_weak'; trendLabel = '偏多震荡'; trendColor = 'bull_weak'
    trendDesc = '价格站上MA20，但MA20/60交叉不明确'
  } else {
    trend = 'down_weak'; trendLabel = '偏空震荡'; trendColor = 'bear_weak'
    trendDesc = '价格跌破MA20，短期偏弱'
  }

  // 支撑区间（近低点±0.3%）
  const supportLo = (supportBase * 0.997).toFixed(0)
  const supportHi = (supportBase * 1.003).toFixed(0)
  // 压力区间
  const resistLo  = (resistBase  * 0.997).toFixed(0)
  const resistHi  = (resistBase  * 1.003).toFixed(0)

  return {
    trend, trendLabel, trendColor, trendDesc,
    supportZone: `${supportLo}~${supportHi}`,
    resistZone:  `${resistLo}~${resistHi}`,
    ma20: ma20.toFixed(0),
    ma60: ma60.toFixed(0),
  }
}

/**
 * 多空能量对比
 * 返回 { bullPower, bearPower, bullPct, bearPct, dominance }
 * bullPct/bearPct: 0~100，用于进度条
 */
function calcEnergyBalance(bars) {
  if (!bars || bars.length < 10) return null
  const recent = bars.slice(-20)

  let bullEnergy = 0, bearEnergy = 0
  recent.forEach(b => {
    const body = Math.abs(b.close - b.open)
    const range = b.high - b.low || 1
    const vol = b.volume || 1
    if (b.close >= b.open) {
      bullEnergy += body * vol
    } else {
      bearEnergy += body * vol
    }
  })

  const total = bullEnergy + bearEnergy || 1
  const bullPct = Math.round(bullEnergy / total * 100)
  const bearPct = 100 - bullPct

  let dominance = 'neutral', domLabel = '多空均衡'
  if (bullPct >= 65) { dominance = 'bull'; domLabel = '多头强势' }
  else if (bullPct >= 55) { dominance = 'bull_weak'; domLabel = '多头偏强' }
  else if (bearPct >= 65) { dominance = 'bear'; domLabel = '空头强势' }
  else if (bearPct >= 55) { dominance = 'bear_weak'; domLabel = '空头偏强' }

  return { bullPct, bearPct, dominance, domLabel }
}

function winRateFromScore(s) {
  return ({0:28,1:30,2:32,3:35,4:38,5:48,6:55,7:63,8:72,9:80,10:85})[Math.min(10,Math.max(0,s))] || 35
}
function toStars(s) {
  const f = Math.min(5, Math.round(s / 2))
  return '★'.repeat(f) + '☆'.repeat(5 - f)
}
function fmtPrice(v) { return v >= 10000 ? v.toFixed(1) : v.toFixed(2) }
function fmtVol(v)   { return v >= 1000 ? (v/1000).toFixed(1)+'k' : v.toFixed(1) }
function timeStr(ts) {
  const d = new Date(ts)
  return `${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} `
       + `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)) }

// 进度条宽度（0~100）
function rsiProgress(v)  { return clamp(v, 0, 100) }
function wrProgress(v)   { return clamp(v + 100, 0, 100) }   // WR -100~0 → 0~100
function kdjProgress(v)  { return clamp(v, 0, 100) }
function bollProgress(close, upper, lower) {
  if (!upper || upper === lower) return 50
  return clamp((close - lower) / (upper - lower) * 100, 0, 100)
}

Page({
  data: {
    interval: '15m',
    intervalLabel: '15分',
    periods: PERIODS,
    tips: TIPS,

    // 大趋势折叠状态
    trendExpanded: false,

    // 价格
    curPrice: '--', priceChange: '--', priceDir: '',
    price4hChange: '--', price24hChange: '--', vol24h: '--',

    // 决策卡
    decisionState: 'wait',
    decisionFace: '😐',
    decisionVerdict: '加载中…',
    decisionSub: '正在获取数据',
    score: 0,
    scoreBar: 0,   // 0~100 for progress bar
    scoreStars: '',
    scoreLabel: '观望',

    // 信号详情
    hasSignal: false,
    signalDir: '',
    pinTime: '--',
    stopLoss: '--',
    tp1: '--', tp2: '--', tp3: '--',
    rrRatio: '--',
    winRate: '--',
    
    // 仓位建议
    posLots: 0,
    posMargin: 0,
    posRatio: 0,
    posLeverage: 0,
    posRiskU: 0,

    // 多空条件感知
    longConditions: [],
    shortConditions: [],
    longOk: 0, shortOk: 0,
    longScore: 0, shortScore: 0,

    // 指标卡
    indCards: [],

    // 市场概况
    macdBarVal: '--', kdjJVal: '--', fundingRate: 'N/A',
    rsiVal: '--', wrVal: '--', bollPos: '--',
    rsiProgress: 50, wrProgress: 50, bollProgress: 50,

    // K线列表
    klineRows: [],

    // 状态
    updateTime: '--',
    loading: false,
    errorMsg: '',
    showTips: false,
    klineView: 120,   // 当前K线视窗根数，初始120根
    
    // 风控状态
    riskStatus: 'normal',        // 'normal'正常, 'cooldown'冷却中, 'max_loss'超日亏限
    riskMsg: '',                 // 风控说明
    todayLossU: 0,               // 今日已亏损U数
    dailyMaxLossU: 0,            // 单日最大亏损U数
    cooldownUntil: '--',         // 冷却截止时间
    
    // canvas 触摸查价
    touchIdx: -1, tooltipLeft: 8,
    touchTime: '', touchO: '', touchH: '', touchL: '', touchC: '', touchV: '',
    touchMACD: '', touchDIF: '', touchDEA: '',

    // MACD金叉/死叉通知条
    macdCross: null,
    macdCrossShow: false,

    // 大趋势判断
    trendLabel: '--', trendColor: 'neutral', trendDesc: '--',
    supportZone: '--', resistZone: '--',
    trendMa20: '--', trendMa60: '--',

    // 多空能量对比
    bullPct: 50, bearPct: 50, domLabel: '均衡',
    energyDominance: 'neutral',
  },

  onLoad() {
    this._canvasReady = false
    this._dragOffset  = 0
    this._dragStartX  = 0
    this._dragStartOff= 0
    this._isDragging  = false
    this._view        = 120    // 默认120根
    this._pinchStartDist = 0
    this._pinchStartView = 120
    this._isPinching  = false
    this._kvCache     = {}     // 多周期缓存: { '15m': { sig, ts }, ... }
    wx.createSelectorQuery()
      .select('#klineCanvas')
      .fields({ node: true, size: true })
      .exec(res => {
        if (!res[0]) return
        const canvas = res[0].node
        const ctx    = canvas.getContext('2d')
        const dpr    = (wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync()).pixelRatio
        canvas.width  = res[0].width  * dpr
        canvas.height = res[0].height * dpr
        ctx.scale(dpr, dpr)
        this._canvas      = canvas
        this._ctx         = ctx
        this._canvasW     = res[0].width
        this._canvasH     = res[0].height
        this._canvasDpr   = dpr
        this._canvasReady = true
        if (this._pendingBars) { this._drawChart(this._pendingBars); this._pendingBars = null }
      })
    this.loadData(false)
    this._timer = setInterval(() => this.loadData(true), 60 * 1000)  // true=静默刷新
  },
  onUnload() { clearInterval(this._timer) },
  onPullDownRefresh() { this.loadData().finally(() => wx.stopPullDownRefresh()) },

  // ══════════════════════════════════════════
  //  Canvas 绘制（火币风格三分区）
  //  主图(62%): K线实体+影线 + BOLL + MA5/10
  //  量图(12%): 成交量柱
  //  副图(26%): MACD柱 + DIF + DEA
  // ══════════════════════════════════════════
  _drawChart(bars) {
    if (!this._canvasReady) { this._pendingBars = bars; return }
    const ctx = this._ctx
    const W   = this._canvasW
    const H   = this._canvasH

    if (bars) this._allBars = bars
    if (!this._allBars) return

    const VIEW   = this._view || 60
    const total  = this._allBars.length
    const maxOff = Math.max(0, total - VIEW)
    const off    = Math.max(0, Math.min(Math.round(this._dragOffset), maxOff))
    const startIdx = Math.max(0, total - VIEW - off)
    const data   = this._allBars.slice(startIdx, startIdx + VIEW)
    const n      = data.length
    if (n < 2) return
    this._chartData = data

    // ── 布局（火币风：左边留窄，右边留宽放价签，底部留时间轴）──
    const padL   = 4
    const padR   = 56
    const padTop = 18
    const padBot = 20
    const innerW = W - padL - padR
    const totalH = H - padTop - padBot

    const mainH  = totalH * 0.62
    const volH   = totalH * 0.12
    const macdH  = totalH * 0.26
    const gap    = 1

    const mainY  = padTop
    const volY   = mainY + mainH + gap
    const macdY  = volY  + volH  + gap

    // 每根K线宽度（barW）和实体宽度（bodyW），实体占约70%，两侧留缝隙
    const barW   = innerW / n
    const bodyW  = Math.max(1, barW * 0.72 - 0.5)  // 火币实体较粗
    const wickW  = Math.max(0.8, barW * 0.12)        // 影线细

    // ── 指标计算 ──
    const closes = data.map(b => b.close)
    const highs  = data.map(b => b.high)
    const lows   = data.map(b => b.low)
    const vols   = data.map(b => b.volume)

    const ma5    = calcEMA(closes, 5)
    const ma10   = calcEMA(closes, 10)
    const bollArr = calcBOLL(closes, 20, 2)
    const macdObj = calcMACD(closes)

    // ── 价格范围（留5%上下边距，让图不贴边）──
    let priceHi = -Infinity, priceLo = Infinity
    data.forEach((b, i) => {
      priceHi = Math.max(priceHi, b.high)
      priceLo = Math.min(priceLo, b.low)
      // BOLL只作为参考线，不强制撑开
      if (bollArr[i].upper < b.high * 1.005) priceHi = Math.max(priceHi, bollArr[i].upper)
      if (bollArr[i].lower > b.low  * 0.995) priceLo = Math.min(priceLo, bollArr[i].lower)
    })
    const pad5 = (priceHi - priceLo) * 0.05 || 1
    priceHi += pad5; priceLo -= pad5
    const priceRange = priceHi - priceLo || 1
    const py = p => mainY + (1 - (p - priceLo) / priceRange) * mainH

    // ── 成交量范围 ──
    const volMax = Math.max(...vols) || 1
    const vy = v => volY + volH - (v / volMax) * volH * 0.92

    // ── MACD范围 ──
    const macdVals = [...macdObj.bar, ...macdObj.dif, ...macdObj.dea].filter(v => isFinite(v))
    const macdMax  = Math.max(...macdVals.map(Math.abs)) || 1
    const macdMidY = macdY + macdH / 2
    const macdPad  = macdH * 0.05
    const my = v => {
      const ratio = v / macdMax
      return macdMidY - ratio * (macdH / 2 - macdPad)
    }

    // ═══════════════ 绘制开始 ═══════════════

    // 背景（火币：纯黑#111）
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#131722'
    ctx.fillRect(0, 0, W, H)

    // ── 网格（水平线，颜色很浅，火币风格）──
    ctx.strokeStyle = '#1e2030'
    ctx.lineWidth   = 0.5
    for (let i = 0; i <= 4; i++) {
      const y = mainY + i * mainH / 4
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke()
    }
    // 成交量区域上边框
    ctx.strokeStyle = '#1a1f33'
    ctx.beginPath(); ctx.moveTo(padL, volY); ctx.lineTo(W - padR, volY); ctx.stroke()
    // MACD区域上边框
    ctx.beginPath(); ctx.moveTo(padL, macdY); ctx.lineTo(W - padR, macdY); ctx.stroke()
    // MACD零线
    ctx.strokeStyle = '#2a3050'; ctx.lineWidth = 0.8
    ctx.beginPath(); ctx.moveTo(padL, macdMidY); ctx.lineTo(W - padR, macdMidY); ctx.stroke()

    // ── 竖向网格（时间轴对应的竖线）──
    ctx.strokeStyle = '#1a1e2e'; ctx.lineWidth = 0.5
    const gridStep = n > 80 ? 20 : n > 40 ? 10 : 5
    data.forEach((b, i) => {
      if (i % gridStep !== 0) return
      const x = padL + i * barW + barW / 2
      ctx.beginPath(); ctx.moveTo(x, mainY); ctx.lineTo(x, macdY + macdH); ctx.stroke()
    })

    // ── 右轴价格标签（火币：白色数字，右侧对齐）──
    ctx.fillStyle    = '#787b86'
    ctx.font         = '9px -apple-system, sans-serif'
    ctx.textAlign    = 'left'
    for (let i = 0; i <= 4; i++) {
      const p = priceHi - i * (priceHi - priceLo) / 4
      const y = mainY + i * mainH / 4
      const label = p >= 10000 ? p.toFixed(0) : p.toFixed(2)
      ctx.fillText(label, W - padR + 4, y + 3)
    }

    // 最新价标记（右轴高亮）
    const lastClose = data[n - 1].close
    const lastY = py(lastClose)
    ctx.fillStyle = data[n-1].close >= data[n-1].open ? '#26a69a' : '#ef5350'
    ctx.fillRect(W - padR + 1, lastY - 7, padR - 2, 14)
    ctx.fillStyle = '#fff'; ctx.font = 'bold 9px -apple-system, sans-serif'; ctx.textAlign = 'left'
    ctx.fillText(lastClose >= 10000 ? lastClose.toFixed(0) : lastClose.toFixed(2), W - padR + 4, lastY + 3)

    // ── 底部时间轴 ──
    ctx.fillStyle = '#535965'; ctx.font = '9px -apple-system, sans-serif'; ctx.textAlign = 'center'
    const tStep = n > 100 ? 20 : n > 50 ? 10 : n > 25 ? 5 : 3
    data.forEach((b, i) => {
      if (i % tStep !== 0) return
      const x = padL + i * barW + barW / 2
      const d = new Date(b.time)
      const label = `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
      ctx.fillText(label, x, H - 4)
    })

    // ── BOLL 三线（火币：上轨蓝、中轨灰虚线、下轨蓝）──
    const drawLine = (arr, color, lw = 1, dash = []) => {
      ctx.strokeStyle = color; ctx.lineWidth = lw
      ctx.setLineDash(dash)
      ctx.beginPath()
      let started = false
      arr.forEach((v, i) => {
        if (!isFinite(v)) { started = false; return }
        const x = padL + i * barW + barW / 2
        if (!started) { ctx.moveTo(x, py(v)); started = true }
        else ctx.lineTo(x, py(v))
      })
      ctx.stroke()
      ctx.setLineDash([])
    }
    drawLine(bollArr.map(b => b.upper), 'rgba(90,131,198,0.7)',  0.8)
    drawLine(bollArr.map(b => b.mid),   'rgba(90,131,198,0.4)',  0.8, [3, 2])
    drawLine(bollArr.map(b => b.lower), 'rgba(90,131,198,0.7)',  0.8)

    // BOLL区域填充（上下轨之间半透明）
    ctx.beginPath()
    bollArr.forEach((b, i) => {
      const x = padL + i * barW + barW / 2
      i === 0 ? ctx.moveTo(x, py(b.upper)) : ctx.lineTo(x, py(b.upper))
    })
    for (let i = n - 1; i >= 0; i--) {
      const x = padL + i * barW + barW / 2
      ctx.lineTo(x, py(bollArr[i].lower))
    }
    ctx.closePath()
    ctx.fillStyle = 'rgba(90,131,198,0.04)'
    ctx.fill()

    // MA 线
    drawLine(ma5,  '#f0b90b', 0.9)   // 金色MA5（火币风）
    drawLine(ma10, '#5088c8', 0.9)   // 蓝色MA10

    // ── 蜡烛图（火币风格：实体粗，影线细，颜色鲜艳）──
    data.forEach((b, i) => {
      const x    = padL + i * barW + barW / 2
      const isUp = b.close >= b.open
      // 火币：上涨=绿色#26a69a，下跌=红色#ef5350
      const upCol   = '#26a69a'
      const dnCol   = '#ef5350'
      const col     = isUp ? upCol : dnCol
      const oY      = py(b.open)
      const cY      = py(b.close)
      const hY      = py(b.high)
      const lY      = py(b.low)
      const bodyTop = Math.min(oY, cY)
      const bodyH   = Math.max(1, Math.abs(cY - oY))

      // 影线（细，颜色同实体）
      ctx.strokeStyle = col
      ctx.lineWidth   = wickW
      ctx.beginPath(); ctx.moveTo(x, hY); ctx.lineTo(x, bodyTop); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(x, bodyTop + bodyH); ctx.lineTo(x, lY); ctx.stroke()

      // 实体（填充 + 边框）
      if (bodyH > 1.5) {
        // 实心
        ctx.fillStyle = col
        ctx.fillRect(x - bodyW / 2, bodyTop, bodyW, bodyH)
      } else {
        // 十字星：只画横线
        ctx.strokeStyle = col; ctx.lineWidth = 1
        ctx.beginPath(); ctx.moveTo(x - bodyW / 2, bodyTop); ctx.lineTo(x + bodyW / 2, bodyTop); ctx.stroke()
      }
    })

    // ── 成交量柱（上涨=半透明绿，下跌=半透明红，对应实体颜色）──
    data.forEach((b, i) => {
      const x   = padL + i * barW + barW / 2
      const isUp = b.close >= b.open
      ctx.fillStyle = isUp ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)'
      const top = vy(b.volume)
      ctx.fillRect(x - bodyW / 2, top, bodyW, volY + volH - top)
    })

    // ── MACD 柱（红绿颜色同K线）──
    data.forEach((b, i) => {
      const x   = padL + i * barW + barW / 2
      const v   = macdObj.bar[i]
      if (!isFinite(v)) return
      const isPos = v >= 0
      const yTop = isPos ? my(v) : macdMidY
      const yBot = isPos ? macdMidY : my(v)
      const bh   = Math.max(1, Math.abs(yBot - yTop))
      ctx.fillStyle = isPos ? 'rgba(38,166,154,0.75)' : 'rgba(239,83,80,0.75)'
      ctx.fillRect(x - bodyW / 2, yTop, bodyW, bh)
    })

    // ── DIF / DEA 线 ──
    const drawMACDLine = (arr, color, lw = 1) => {
      ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.setLineDash([])
      ctx.beginPath()
      let started = false
      arr.forEach((v, i) => {
        if (!isFinite(v)) { started = false; return }
        const x = padL + i * barW + barW / 2
        if (!started) { ctx.moveTo(x, my(v)); started = true }
        else ctx.lineTo(x, my(v))
      })
      ctx.stroke()
    }
    drawMACDLine(macdObj.dif, '#f0b90b', 0.8)
    drawMACDLine(macdObj.dea, '#5088c8', 0.8)

    // ── 插针信号标记（更简洁，只在真正插针K线上标小三角）──
    data.forEach((b, i) => {
      const x       = padL + i * barW + barW / 2
      const body    = Math.abs(b.close - b.open)
      const kRange  = b.high - b.low || 0.001
      const lowerSh = Math.min(b.open, b.close) - b.low
      const upperSh = b.high - Math.max(b.open, b.close)
      const minBody = b.close * 0.0003
      const minSh   = b.close * 0.001
      const isLong  = body >= minBody && lowerSh >= body * 1.5 && lowerSh >= minSh && b.close > b.low + kRange * 0.5
      const isShort = body >= minBody && upperSh >= body * 1.5 && upperSh >= minSh && b.close < b.high - kRange * 0.5
      const sz      = Math.max(8, Math.min(13, barW * 1.2))
      if (isLong) {
        const ay = py(b.low) + sz + 4
        ctx.fillStyle = '#26a69a'
        ctx.font = `${sz}px sans-serif`; ctx.textAlign = 'center'
        ctx.fillText('▲', x, ay)
      } else if (isShort) {
        const ay = py(b.high) - sz - 4
        ctx.fillStyle = '#ef5350'
        ctx.font = `${sz}px sans-serif`; ctx.textAlign = 'center'
        ctx.fillText('▼', x, ay)
      }
    })

    // ── 区域标签（左上角）──
    ctx.font = '8px -apple-system, sans-serif'; ctx.textAlign = 'left'; ctx.fillStyle = '#535965'
    ctx.fillText(`MA5  MA10  BOLL`, padL + 2, mainY + 11)
    ctx.fillText('VOL', padL + 2, volY + 9)
    ctx.fillText(`MACD`, padL + 2, macdY + 9)

    // ── 右上角视窗根数 ──
    ctx.fillStyle = 'rgba(88,166,255,0.55)'; ctx.font = '8px sans-serif'; ctx.textAlign = 'right'
    ctx.fillText(`${n}根`, W - padR - 2, mainY + 11)

    // 存指标和布局备触摸用
    this._chartIndicators = { bollArr, ma5, ma10, macdObj }
    this._chartLayout = { padL, padR, mainY, mainH, volH, macdH,
                          volY, macdY, barW, n, priceHi, priceLo }
  },

  // ── 触摸交互：双指缩放 + 单指拖动 + 单指查价 ──
  onKlineTouch(e) {
    if (!this._chartLayout) return
    const touches = e.touches

    // ══ 双指：捏合缩放 ══
    if (touches.length === 2) {
      const dx = touches[0].x - touches[1].x
      const dy = touches[0].y - touches[1].y
      const dist = Math.sqrt(dx * dx + dy * dy)

      if (e.type === 'touchstart') {
        this._isPinching     = true
        this._isDragging     = false
        this._touchMoved     = false
        this._pinchStartDist = dist
        this._pinchStartView = this._view || 120
        this.setData({ touchIdx: -1 })
        return
      }
      if (e.type === 'touchmove' && this._isPinching) {
        if (this._pinchStartDist < 10) return
        // 两指拉开 → dist变大 → 放大 → VIEW变小（看更少根，更细节）
        // 两指靠拢 → dist变小 → 缩小 → VIEW变大（看更多根，更全局）
        const scale   = this._pinchStartDist / dist  // <1拉开，>1靠拢
        const newView = Math.round(this._pinchStartView * scale)
        this._view = Math.max(10, Math.min(480, newView))
        this.setData({ klineView: this._view })
        this._drawChart(null)
        return
      }
      return
    }

    // ══ 单指逻辑 ══
    this._isPinching = false
    const touch = touches[0]

    if (e.type === 'touchstart') {
      this._isDragging   = false
      this._dragStartX   = touch.x
      this._dragStartOff = this._dragOffset
      this._touchStartX  = touch.x
      this._touchMoved   = false
    } else if (e.type === 'touchmove') {
      const dx = touch.x - this._dragStartX
      const { barW } = this._chartLayout
      if (Math.abs(touch.x - this._touchStartX) > 3) this._touchMoved = true
      if (this._touchMoved) {
        this._isDragging  = true
        const rawOff = this._dragStartOff - dx / barW
        const maxOff = Math.max(0, (this._allBars ? this._allBars.length : 40) - (this._view || 40))
        // 橡皮筋阻尼：超出边界时有0.25倍阻尼，给手指继续滑动的感觉
        let newOff
        if (rawOff < 0) {
          newOff = rawOff * 0.25   // 右边界：允许轻微过冲但阻尼
        } else if (rawOff > maxOff) {
          newOff = maxOff + (rawOff - maxOff) * 0.25  // 左边界：阻尼
        } else {
          newOff = rawOff
        }
        this._dragOffset = Math.round(newOff)
        this._dragOffsetRaw = newOff  // 保存浮点数用于弹回动画
        this.setData({ touchIdx: -1 })
        this._drawChart(null)
        return
      }
    }

    if (this._isDragging) return
    this._showCrosshair(touch.x)
  },

  _showCrosshair(touchX) {
    if (!this._chartData || !this._chartLayout) return
    const { padL, padR, mainY, mainH, macdY, macdH, barW, n, priceHi, priceLo } = this._chartLayout
    const ind = this._chartIndicators
    const W   = this._canvasW

    const idx = Math.min(n - 1, Math.max(0, Math.floor((touchX - padL) / barW)))
    const b   = this._chartData[idx]
    const d   = new Date(b.time)
    const tStr = `${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} `
               + `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`

    // 先重绘干净底图再画准星
    this._drawChart(null)
    const ctx = this._ctx
    const cx  = padL + idx * barW + barW / 2
    const priceRange = priceHi - priceLo || 1
    const cy  = mainY + (1 - (b.close - priceLo) / priceRange) * mainH

    ctx.strokeStyle = 'rgba(88,166,255,0.5)'; ctx.lineWidth = 0.8; ctx.setLineDash([3, 3])
    ctx.beginPath(); ctx.moveTo(cx, mainY); ctx.lineTo(cx, macdY + macdH); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(padL, cy);  ctx.lineTo(W - padR, cy);       ctx.stroke()
    ctx.setLineDash([])

    const isUp = b.close >= b.open
    ctx.fillStyle = isUp ? '#26a69a' : '#ef5350'
    ctx.fillRect(W - padR + 1, cy - 7, padR - 2, 14)
    ctx.fillStyle = '#fff'; ctx.font = 'bold 9px -apple-system, sans-serif'; ctx.textAlign = 'left'
    ctx.fillText(b.close >= 10000 ? b.close.toFixed(0) : b.close.toFixed(2), W - padR + 4, cy + 3)

    const macdV = (ind.macdObj.bar[idx] || 0)
    const difV  = (ind.macdObj.dif[idx] || 0)
    const deaV  = (ind.macdObj.dea[idx] || 0)
    const tooltipLeft = cx > W / 2 ? 8 : Math.round(cx + 10)

    this.setData({
      touchIdx: idx, tooltipLeft,
      touchTime: tStr,
      touchO: fmtPrice(b.open),  touchH: fmtPrice(b.high),
      touchL: fmtPrice(b.low),   touchC: fmtPrice(b.close),
      touchV: fmtVol(b.volume),
      touchMACD: (macdV >= 0 ? '+' : '') + macdV.toFixed(2),
      touchDIF:  (difV  >= 0 ? '+' : '') + difV.toFixed(2),
      touchDEA:  (deaV  >= 0 ? '+' : '') + deaV.toFixed(2),
    })
  },

  onKlineTouchEnd(e) {
    this._isDragging = false
    this._touchMoved = false
    this.setData({ touchIdx: -1 })
    // 弹回：如果拖过了边界，平滑动画回到边界
    const maxOff = Math.max(0, (this._allBars ? this._allBars.length : 40) - (this._view || 40))
    const target = Math.max(0, Math.min(Math.round(this._dragOffsetRaw ?? this._dragOffset), maxOff))
    if (this._dragOffset !== target) {
      this._animateTo(target)
    } else {
      this._drawChart(null)
    }
  },

  // 弹回动画：平滑过渡到目标offset
  _animateTo(target) {
    const STEP = 6
    const tick = () => {
      const cur = this._dragOffset
      const diff = target - cur
      if (Math.abs(diff) < 0.8) {
        this._dragOffset = target
        this._drawChart(null)
        return
      }
      this._dragOffset = cur + diff * 0.35
      this._drawChart(null)
      setTimeout(tick, 16)
    }
    tick()
  },

  // 大趋势详情折叠/展开
  toggleTrendDetail() {
    this.setData({ trendExpanded: !this.data.trendExpanded })
  },

  switchInterval(e) {
    const iv    = e.currentTarget.dataset.iv
    const label = e.currentTarget.dataset.label
    // 重置拖动偏移和视窗
    this._dragOffset = 0
    this._allBars    = null
    this._chartData  = null
    this._view       = 120

    this.setData({ interval: iv, intervalLabel: label, klineView: 120 })

    // 有缓存且 < 2分钟：立即渲染，后台静默更新
    const cache = this._kvCache[iv]
    const cacheAge = cache ? (Date.now() - cache.ts) : Infinity
    if (cache && cacheAge < 120000) {
      this._renderAll(cache.sig)          // 秒切：先显示缓存
      this._silentRefresh(iv)             // 后台刷新
    } else {
      this.loadData(false)                // 无缓存：正常拉
    }
  },

  // 后台静默刷新（不显示loading）
  async _silentRefresh(iv) {
    try {
      const sig = await detectSignal(iv)
      this._kvCache[iv] = { sig, ts: Date.now() }
      if (this.data.interval === iv) this._renderAll(sig)  // 仍在这个周期才更新
    } catch(e) { /* 静默忽略 */ }
  },



  refresh() { this.loadData(false) },
  toggleTips() { this.setData({ showTips: !this.data.showTips }) },

  async loadData(silent = false) {
    if (!silent && this.data.loading) return
    if (!silent) this.setData({ loading: true, errorMsg: '' })
    try {
      const iv  = this.data.interval
      const sig = await detectSignal(iv)
      this._kvCache[iv] = { sig, ts: Date.now() }  // 存缓存
      this._renderAll(sig)
    } catch (e) {
      if (!silent) this.setData({ errorMsg: e.message || '数据获取失败，请检查网络' })
    } finally {
      if (!silent) this.setData({ loading: false })
    }
  },

  _renderAll(sig) {
    const bars   = sig.bars
    const last   = bars[bars.length - 1]
    const prev   = bars[bars.length - 2]

    // 价格
    const chg = (last.close - prev.close) / prev.close * 100
    const dir = chg >= 0 ? 'up' : 'down'

    // 24h / 4h 概况（按当前周期动态换算 bars 数量）
    const ivMinMap = { '1s':1/60, '1m':1, '3m':3, '5m':5, '15m':15, '30m':30, '1h':60, '2h':120, '4h':240, '6h':360, '12h':720, '1d':1440, '3d':4320, '1w':10080 }
    const ivMin    = ivMinMap[this.data.interval] || 15
    const bars24h  = Math.round(24 * 60 / ivMin)   // 24h对应多少根
    const bars4h   = Math.round(4  * 60 / ivMin)   // 4h对应多少根
    const bar24hAgo = bars[Math.max(0, bars.length - bars24h)]
    const bar4hAgo  = bars[Math.max(0, bars.length - bars4h)]
    const chg24h    = (last.close - bar24hAgo.close) / bar24hAgo.close * 100
    const chg4h     = sig.drop4h !== undefined ? sig.drop4h : (last.close - bar4hAgo.close) / bar4hAgo.close * 100
    const vol24hSum = bars.slice(-bars24h).reduce((s,b) => s + b.volume, 0)

    // 指标值
    const n        = bars.length - 1
    const macdBar  = sig.macdBar ?? 0
    const macdPrev = sig.macdPrev ?? 0
    const jVal     = sig.jVal ?? 50
    const rsiV     = sig.rsiVal ?? 50
    const wrV      = sig.wrVal ?? -50
    const boll     = sig.bollLast ?? { upper: last.close*1.02, mid: last.close, lower: last.close*0.98 }

    // 指标卡（2行×4列）—— try/catch防止任何字段缺失导致崩溃
    let indCards = []
    try { indCards = [
      {
        name: 'MACD', 
        val: macdBar > 0 ? '+'+macdBar.toFixed(0) : macdBar.toFixed(0),
        tip: 'DIF ' + ((sig.dif??0)>=0?'+':'') + (sig.dif??0).toFixed(0),
        cls: sig.dif > sig.dea ? 'long' : sig.dif < sig.dea ? 'short' : '',
        dot: sig.dif > sig.dea ? 'red' : sig.dif < sig.dea ? 'green' : 'gray',
        state: sig.dif > sig.dea ? '金叉↑多头' : sig.dif < sig.dea ? '死叉↓空头' : '中性',
        progress: clamp(50 + macdBar / last.close * 5000, 0, 100)
      },
      {
        name: 'KDJ·J', 
        val: jVal.toFixed(1),
        tip: `K:${(sig.kVal||0).toFixed(0)} D:${(sig.dVal||0).toFixed(0)}`,
        cls: jVal < 20 ? 'long' : jVal > 80 ? 'short' : '',
        dot: jVal < 20 ? 'red' : jVal > 80 ? 'green' : 'gray',
        state: jVal < 20 ? '超卖↑做多' : jVal > 80 ? '超买↓做空' : '中性区',
        progress: kdjProgress(jVal)
      },
      {
        name: 'RSI(14)', 
        val: rsiV.toFixed(1),
        tip: rsiV < 30 ? '超卖 进多区' : rsiV > 70 ? '超买 进空区' : '中性区间',
        cls: rsiV < 30 ? 'long' : rsiV > 70 ? 'short' : '',
        dot: rsiV < 30 ? 'red' : rsiV > 70 ? 'green' : 'gray',
        state: rsiV < 30 ? '超卖 做多' : rsiV > 70 ? '超买 做空' : '观望',
        progress: rsiProgress(rsiV)
      },
      {
        name: 'W&R', 
        val: wrV.toFixed(0),
        tip: wrV < -80 ? '极度超卖' : wrV > -20 ? '极度超买' : '震荡区间',
        cls: wrV < -80 ? 'long' : wrV > -20 ? 'short' : '',
        dot: wrV < -80 ? 'red' : wrV > -20 ? 'green' : 'gray',
        state: wrV < -80 ? '超卖↑做多' : wrV > -20 ? '超买↓做空' : '观望',
        progress: wrProgress(wrV)
      },
      {
        name: 'BOLL', 
        val: last.close <= boll.lower*1.005 ? '触下轨' : last.close >= boll.upper*0.995 ? '触上轨' : '轨道中',
        tip: `上:${boll.upper.toFixed(0)} 下:${boll.lower.toFixed(0)}`,
        cls: last.close <= boll.lower*1.005 ? 'long' : last.close >= boll.upper*0.995 ? 'short' : '',
        dot: last.close <= boll.lower*1.005 ? 'red' : last.close >= boll.upper*0.995 ? 'green' : 'gray',
        state: last.close <= boll.lower*1.005 ? '下轨↑做多' : last.close >= boll.upper*0.995 ? '上轨↓做空' : '中轨观望',
        progress: bollProgress(last.close, boll.upper, boll.lower)
      },
      {
        name: '插针', 
        val: sig.isLongPin ? '下影针' : sig.isShortPin ? '上影针' : '无形态',
        tip: sig.isLongPin ? `下影${(sig.lowerShadow??0).toFixed(0)}pts` : sig.isShortPin ? `上影${(sig.upperShadow??0).toFixed(0)}pts` : `等待插针形态`,
        cls: sig.isLongPin ? 'long' : sig.isShortPin ? 'short' : '',
        dot: sig.isLongPin ? 'red' : sig.isShortPin ? 'green' : 'gray',
        state: sig.isLongPin ? '做多信号' : sig.isShortPin ? '做空信号' : '等待插针',
        progress: 50
      },
      {
        name: '量比', 
        val: (() => {
          const vol5avg = bars.slice(-7,-2).reduce((s,b)=>s+b.volume,0)/5
          const lastVol = bars[bars.length-2]?.volume ?? 0
          return vol5avg > 0 ? (lastVol/vol5avg).toFixed(2)+'x' : '--'
        })(),
        tip: sig.c3 ? '✅ 已放量 进场有效' : '❌ 量不足 信号偏弱',
        cls: sig.c3 ? 'long' : '',
        dot: sig.c3 ? 'red' : 'gray',
        state: sig.c3 ? '放量有效' : '量能不足',
        progress: (() => {
          const vol5avg = bars.slice(-7,-2).reduce((s,b)=>s+b.volume,0)/5
          const lastVol = bars[bars.length-2]?.volume ?? 0
          return vol5avg > 0 ? clamp(lastVol/vol5avg/2*100, 0, 100) : 50
        })()
      },
      {
        name: '4h趋势', 
        val: chg4h >= 0 ? '+'+chg4h.toFixed(2)+'%' : chg4h.toFixed(2)+'%',
        tip: chg4h > 3 ? '强势上涨中' : chg4h < -3 ? '强势下跌中' : '震荡行情',
        cls: chg4h > 2 ? 'long' : chg4h < -2 ? 'short' : '',
        dot: chg4h > 2 ? 'red' : chg4h < -2 ? 'green' : 'gray',
        state: chg4h > 2 ? '多头市场' : chg4h < -2 ? '空头市场' : '震荡观望',
        progress: clamp(50 + chg4h * 3, 0, 100)
      },
    ] } catch(e) { console.error('indCards build error:', e) }

    // 决策
    let decisionState = 'wait', decisionFace = '😐'
    let decisionVerdict = '等待信号中', decisionSub = '暂无插针形态，持续监控中…'
    let hasSignal = false, score = 0, scoreStars = '', scoreBar = 0, scoreLabel = '观望'
    let signalDir = '', pinTime = '--', stopLoss = '--', tp1='--', tp2='--', tp3='--', rrRatio='--', winRate='--'
    let posLots = 0, posMargin = 0, posRatio = 0, posLeverage = 0, posRiskU = 0

    if (sig.type === 'filtered') {
      decisionSub = `已过滤：${sig.reason}`
    } else if (sig.type === 'long' || sig.type === 'short') {
      hasSignal = true
      score      = sig.score
      scoreStars = toStars(score)
      scoreBar   = score * 10
      signalDir  = sig.type
      pinTime    = timeStr(sig.pin.time)
      winRate    = winRateFromScore(score)

      const entry = last.close
      if (sig.type === 'long') {
        const sl   = sig.pin.low * 0.9995
        const dist = entry - sl
        tp1 = fmtPrice(entry + dist * 1.0)
        tp2 = fmtPrice(entry + dist * 1.5)
        tp3 = fmtPrice(entry + dist * 2.5)
        stopLoss = fmtPrice(sl)
        rrRatio  = `1.5:1`
      } else {
        const sl   = sig.pin.high * 1.0005
        const dist = sl - entry
        tp1 = fmtPrice(entry - dist * 1.0)
        tp2 = fmtPrice(entry - dist * 1.5)
        tp3 = fmtPrice(entry - dist * 2.5)
        stopLoss = fmtPrice(sl)
        rrRatio  = `1.5:1`
      }

      // 仓位建议
      if (sig.positionAdvice) {
        posLots = sig.positionAdvice.lots
        posMargin = sig.positionAdvice.margin
        posRatio = sig.positionAdvice.positionRatio
        posLeverage = sig.positionAdvice.leverage
        posRiskU = sig.positionAdvice.riskAmount
      }

      if (score >= 8) {
        decisionState   = sig.type === 'long' ? 'buy' : 'short_s'
        decisionFace    = sig.type === 'long' ? '🚀' : '📉'
        decisionVerdict = sig.type === 'long' ? '强烈推荐做多！' : '强烈推荐做空！'
        decisionSub     = sig.type === 'long' ? '多指标共振，优先把握机会' : '上影插针确认，注意控仓'
        scoreLabel      = '强烈推荐'
      } else if (score >= 6) {
        decisionState   = 'ok'
        decisionFace    = sig.type === 'long' ? '📈' : '📉'
        decisionVerdict = '✅ 建议做' + (sig.type === 'long' ? '多' : '空')
        decisionSub     = '信号中等，轻仓跟进，严控止损'
        scoreLabel      = '建议做'
      } else if (score >= 5) {
        decisionState   = 'watch'; decisionFace = '⚠️'
        decisionVerdict = '谨慎观望'; decisionSub = '信号偏弱，可观望或超轻仓'
        scoreLabel      = '谨慎'
      } else {
        decisionState   = 'no'; decisionFace = '🚫'
        decisionVerdict = '不建议入场'; decisionSub = '指标配合不足，耐心等待更好机会'
        scoreLabel      = '不建议'
      }
    }

    // K线列表（最近12根）
    const klineRows = bars.slice(-12).reverse().map(b => {
      const p = (b.close - b.open) / b.open * 100
      return {
        time: b.time,
        timeStr: timeStr(b.time),
        close: fmtPrice(b.close),
        chg: (p >= 0 ? '+' : '') + p.toFixed(2),
        vol: fmtVol(b.volume),
        dir: p >= 0 ? 'up' : 'dn'
      }
    })

    const now = new Date()
    const updateTime = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`

    const longConds  = sig.longConditions  || []
    const shortConds = sig.shortConditions || []
    const longOkN    = longConds.filter(c => c.ok).length
    const shortOkN   = shortConds.filter(c => c.ok).length

    // 风控状态（小程序简化版，无法持久化存储）
    // 这里只是模拟展示，实际需要配合后端或本地存储
    const dailyMaxLossU = 1000 * 0.05  // 账户1000U * 5% = 50U
    const todayLossU = 0               // 实际应用需要从存储中读取
    const riskStatus = 'normal'        // normal, cooldown, max_loss
    let riskMsg = '', cooldownUntil = '--'
    
    if (riskStatus === 'cooldown') {
      riskMsg = `连亏3笔，冷却2小时`
      cooldownUntil = `14:30`
    } else if (riskStatus === 'max_loss') {
      riskMsg = `今日已亏${todayLossU}U，达单日上限`
    } else {
      riskMsg = `风控正常，今日已亏${todayLossU}U/${dailyMaxLossU}U`
    }

    // ── 大趋势判断 ────────────────────────────────────────────
    const trendInfo  = calcTrend(bars)
    const energyInfo = calcEnergyBalance(bars)

    // ── MACD金叉/死叉检测 ──────────────────────────────────────
    const macdCross = detectMacdCross(bars)

    this.setData({
      curPrice: fmtPrice(last.close),
      priceChange: (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%',
      priceDir: dir,
      price4hChange: (chg4h >= 0 ? '+' : '') + chg4h.toFixed(2) + '%',
      price24hChange: (chg24h >= 0 ? '+' : '') + chg24h.toFixed(2) + '%',
      vol24h: fmtVol(vol24hSum),

      decisionState, decisionFace, decisionVerdict, decisionSub,
      score, scoreBar, scoreStars, scoreLabel,
      hasSignal, signalDir, pinTime, stopLoss, tp1, tp2, tp3, rrRatio, winRate,
      posLots, posMargin, posRatio, posLeverage, posRiskU,

      longConditions:  longConds,
      shortConditions: shortConds,
      longOk: longOkN, shortOk: shortOkN,
      longScore: longOkN * 25, shortScore: shortOkN * 25,

      indCards,

      macdBarVal: macdBar > 0 ? '+'+macdBar.toFixed(0) : macdBar.toFixed(0),
      kdjJVal: jVal.toFixed(1),
      rsiVal: rsiV.toFixed(1),
      wrVal: wrV.toFixed(0),
      bollPos: last.close <= boll.lower*1.005 ? '下轨' : last.close >= boll.upper*0.995 ? '上轨' : '中轨',
      rsiProgress: rsiProgress(rsiV),
      wrProgress: wrProgress(wrV),
      bollProgress: bollProgress(last.close, boll.upper, boll.lower),

      klineRows,
      updateTime,
      touchIdx: -1,
      
      // MACD金叉/死叉通知条
      macdCross: macdCross,
      macdCrossShow: !!macdCross,

      // 大趋势
      trendLabel:  trendInfo ? trendInfo.trendLabel : '--',
      trendColor:  trendInfo ? trendInfo.trendColor  : 'neutral',
      trendDesc:   trendInfo ? trendInfo.trendDesc   : '--',
      supportZone: trendInfo ? trendInfo.supportZone : '--',
      resistZone:  trendInfo ? trendInfo.resistZone  : '--',
      trendMa20:   trendInfo ? trendInfo.ma20 : '--',
      trendMa60:   trendInfo ? trendInfo.ma60 : '--',

      // 多空能量
      bullPct:         energyInfo ? energyInfo.bullPct   : 50,
      bearPct:         energyInfo ? energyInfo.bearPct   : 50,
      domLabel:        energyInfo ? energyInfo.domLabel  : '均衡',
      energyDominance: energyInfo ? energyInfo.dominance : 'neutral',

      // 风控状态
      riskStatus,
      riskMsg,
      todayLossU,
      dailyMaxLossU,
      cooldownUntil,
    })

    // 画 K线图
    this._drawChart(bars)
  }
})
