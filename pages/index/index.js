// pages/index/index.js  v3
const { fetchKlines, detectSignal, clearSignalCache } = require('../../utils/detector')
const { macd: calcMACD, boll: calcBOLL, ema: calcEMA } = require('../../utils/indicators')

const PERIODS = [
  { iv: '1s',  label: '1s秒线',    limit: 500, base: true  },
  { iv: '1m',  label: '1m超短线',  limit: 500, base: true  },
  { iv: '3m',  label: '3m短线',    limit: 480, base: false },
  { iv: '5m',  label: '5m短线',    limit: 480, base: false },
  { iv: '15m', label: '15m主策略', limit: 480, base: true  },
  { iv: '30m', label: '30m中线',   limit: 480, base: false },
  { iv: '1h',  label: '1h趋势',    limit: 480, base: true  },
  { iv: '2h',  label: '2h趋势',    limit: 480, base: false },
  { iv: '4h',  label: '4h大趋势',  limit: 480, base: true  },
  { iv: '6h',  label: '6h趋势',    limit: 480, base: false },
  { iv: '12h', label: '12h趋势',   limit: 480, base: false },
  { iv: '1d',  label: '1d日线',    limit: 480, base: true  },
  { iv: '3d',  label: '3d三日线',  limit: 480, base: false },
  { iv: '1w',  label: '1w周线',    limit: 480, base: false },
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
    body: '≥80分 🔥 强信号直接打\n50~79分 ⚠️ 轻仓谨慎进\n<30分 🚫 看书等机会',
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

function winRateFromScore(s) {
  return ({0:28,1:30,2:32,3:35,4:38,5:48,6:55,7:63,8:72,9:80,10:85})[Math.min(10,Math.max(0,s))] || 35
}
function toStars(s) {
  const f = Math.min(5, Math.round(s / 20))
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
    intervalLabel: '15m · 主策略',
    periods: PERIODS,
    tips: TIPS,

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
    // 无信号时的参考位
    refSL: '--', refSLPct: '',
    refTP1: '--', refTP1Pct: '',
    refTP2: '--', refTP2Pct: '',
    refTP3: '--', refTP3Pct: '',
    
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
    showMorePeriods: false,   // 展开更多周期
    klineView: 120,   // 当前K线视窗根数
    
    // 会员 & 体验
    isVip: false,
    inTrial: false,
    trialSecs: 120,
    trialTotal: 120,
    trialMin: 2,   // 分钟显示
    trialSec: 0,   // 秒显示（0-59）
    codeInput: '',
    pwdInput: '',
    showPwdDialog: false,
    showVipDrawer: false,

    // 空头趋势锁定
    isBearTrend: false,

    // AI标签（营销用）
    aiLabel: 'AI量化 · 实时分析中',

    // 趋势判断
    trendColor: 'sideways', trendLabel: '分析中', trendIcon: '🐸',
    trendMa20: '--', trendMa60: '--', trendMa20Dir: 'gray', trendMa60Dir: 'gray',
    trendSupport: '--', trendResist: '--',

    // 免责声明
    showDisclaimer: false,

    // canvas 触摸查价
    touchIdx: -1, tooltipLeft: 8,
    touchTime: '', touchO: '', touchH: '', touchL: '', touchC: '', touchV: '',
    touchMACD: '', touchDIF: '', touchDEA: '',
  },

  onLoad() {
    this._canvasReady = false
    this._dragOffset  = 0
    this._dragStartX  = 0
    this._dragStartOff= 0
    this._isDragging  = false
    this._view        = 120
    this._pinchStartDist = 0
    this._pinchStartView = 120
    this._isPinching  = false

    // ══ 免费体验2分钟倒计时（每次进入重置） ══
    const TRIAL_SECS = 120
    // 检查会员有效期
    // 【开发调试用，上线前删掉这行】
    // wx.setStorageSync('isVip', true); wx.setStorageSync('vip_exp', 9999999999999)
    let isVip = wx.getStorageSync('isVip') === true
    if (isVip) {
      const exp = wx.getStorageSync('vip_exp') || 0
      if (exp < Date.now()) {
        // 会员过期，降级
        isVip = false
        wx.removeStorageSync('isVip')
      }
    }
    // 每次打开都重置体验时间（2分钟重新开始）
    const trialEnd = Date.now() + TRIAL_SECS * 1000
    wx.setStorageSync('trial_end_ts', trialEnd)
    const inTrial = !isVip
    this.setData({ isVip, inTrial, trialSecs: TRIAL_SECS, trialTotal: TRIAL_SECS,
      trialMin: Math.floor(TRIAL_SECS / 60), trialSec: TRIAL_SECS % 60 })

    // ══ 免责声明（首次进入显示） ══
    const agreed = wx.getStorageSync('disclaimer_agreed')
    if (!agreed) {
      this.setData({ showDisclaimer: true })
    }

    if (!isVip) {
      this._trialTimer = setInterval(() => {
        const now = Date.now()
        const secs = Math.max(0, Math.ceil((wx.getStorageSync('trial_end_ts') - now) / 1000))
        const stillTrial = secs > 0
        const tMin = Math.floor(secs / 60)
        const tSec = secs % 60
        this.setData({ inTrial: stillTrial, trialSecs: secs, trialMin: tMin, trialSec: tSec })
        if (!stillTrial) {
          clearInterval(this._trialTimer)
          // 体验结束后延迟1s自动弹出升级抽屉（温和提示，而非直接跳付费墙）
          setTimeout(() => {
            if (!this.data.isVip) this.setData({ showVipDrawer: true })
          }, 1000)
        }
      }, 1000)
    }

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
    this.loadData()
    this._timer = setInterval(() => this.loadData(), 30 * 1000)  // 30s自动刷新
  },
  onUnload() { 
    clearInterval(this._timer)
    clearInterval(this._trialTimer)
  },
  onPullDownRefresh() { this.loadData().finally(() => wx.stopPullDownRefresh()) },

  // ══════════════════════════════════════════
  //  Canvas 绘制（交易所风格三分区）
  //  主图(60%): K线 + BOLL(上中下) + MA5 + MA10
  //  量图(14%): 成交量柱
  //  副图(26%): MACD 柱 + DIF线 + DEA线
  // ══════════════════════════════════════════
  // 切换周期时立刻在canvas画loading占位，让用户感知响应
  _drawLoading(label) {
    if (!this._canvasReady) return
    const ctx = this._ctx
    const W = this._canvasW
    const H = this._canvasH
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#07090f'
    ctx.fillRect(0, 0, W, H)
    ctx.fillStyle = 'rgba(59,130,246,0.15)'
    ctx.fillRect(0, 0, W, H)
    ctx.font = `bold ${Math.round(W * 0.045)}px sans-serif`
    ctx.fillStyle = '#60a5fa'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(`${label || ''} 加载中...`, W / 2, H / 2)
    ctx.font = `${Math.round(W * 0.03)}px sans-serif`
    ctx.fillStyle = '#475569'
    ctx.fillText('正在拉取最新K线数据', W / 2, H / 2 + W * 0.065)
    ctx.draw && ctx.draw()
  },

  _drawChart(bars) {
    if (!this._canvasReady) { this._pendingBars = bars; return }
    const ctx = this._ctx
    const W   = this._canvasW
    const H   = this._canvasH

    // 全量数据存起来，供拖动复用；传 null 时复用已有数据
    if (bars) this._allBars = bars
    if (!this._allBars) return

    // 每屏显示VIEW根，拖动偏移控制从哪里切窗口
    const VIEW  = this._view || 120
    const total = this._allBars.length
    const maxOff = Math.max(0, total - VIEW)
    const off   = Math.max(0, Math.min(Math.round(this._dragOffset), maxOff))
    // 从右往左截：offset=0 → 最新VIEW根；offset增大 → 往左看历史
    const startIdx = Math.max(0, total - VIEW - off)
    const data  = this._allBars.slice(startIdx, startIdx + VIEW)
    const n     = data.length
    if (n < 2) return
    this._chartData = data   // 存备触摸/重绘用

    // 布局
    const padL = 16, padR = 42, padTop = 10, padBot = 22
    const innerW = W - padL - padR
    const totalH = H - padTop - padBot

    const mainH = totalH * 0.60
    const volH  = totalH * 0.14
    const macdH = totalH * 0.26
    const gap   = 2

    const mainY = padTop
    const volY  = mainY + mainH + gap
    const macdY = volY  + volH  + gap

    const barW  = innerW / n
    const bBody = Math.max(1.5, barW * 0.6)

    // ── 计算指标 ──
    const closes = data.map(b => b.close)
    const highs  = data.map(b => b.high)
    const lows   = data.map(b => b.low)
    const vols   = data.map(b => b.volume)

    const ma5   = calcEMA(closes, 5)
    const ma10  = calcEMA(closes, 10)
    const bollArr = calcBOLL(closes, 20, 2)
    const macdObj = calcMACD(closes)   // { dif, dea, bar }

    // ── 价格范围 ──
    let priceHi = -Infinity, priceLo = Infinity
    data.forEach((b, i) => {
      priceHi = Math.max(priceHi, b.high, bollArr[i].upper)
      priceLo = Math.min(priceLo, b.low,  bollArr[i].lower)
    })
    const priceRange = priceHi - priceLo || 1
    const py = p => mainY + (1 - (p - priceLo) / priceRange) * mainH

    // ── 成交量范围 ──
    const volMax = Math.max(...vols) || 1
    const vy = v => volY + volH - (v / volMax) * volH

    // ── MACD范围 ──
    const macdVals = [...macdObj.bar, ...macdObj.dif, ...macdObj.dea]
    const macdMax  = Math.max(...macdVals.map(Math.abs)) || 1
    const macdMidY = macdY + macdH / 2
    const my = v => macdMidY - (v / macdMax) * (macdH / 2)

    // ── 清背景 ──
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#0d1117'
    ctx.fillRect(0, 0, W, H)

    // ── 分区分割线 ──
    ctx.strokeStyle = '#21262d'; ctx.lineWidth = 0.5
    ;[mainY, volY, macdY, macdY + macdH].forEach(y => {
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke()
    })

    // ── 主图网格 ──
    ctx.strokeStyle = '#161b22'; ctx.lineWidth = 0.5
    for (let i = 1; i < 4; i++) {
      const y = mainY + i * mainH / 4
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke()
    }
    // MACD 零线
    ctx.strokeStyle = '#30363d'; ctx.lineWidth = 0.5
    ctx.beginPath(); ctx.moveTo(padL, macdMidY); ctx.lineTo(W - padR, macdMidY); ctx.stroke()

    // ── 右轴价格标签 ──
    ctx.fillStyle = '#484f58'; ctx.font = '9px sans-serif'; ctx.textAlign = 'left'
    for (let i = 0; i <= 4; i++) {
      const p = priceHi - i * priceRange / 4
      const y = mainY + i * mainH / 4
      ctx.fillText(p >= 10000 ? p.toFixed(0) : p.toFixed(1), W - padR + 3, y + 3)
    }

    // ── 底部时间轴 ──
    ctx.fillStyle = '#484f58'; ctx.font = '9px sans-serif'; ctx.textAlign = 'center'
    data.forEach((b, i) => {
      if (i % 8 !== 0) return
      const x = padL + i * barW + barW / 2
      const d = new Date(b.time)
      ctx.fillText(
        `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`,
        x, H - 4
      )
    })

    // ── BOLL 三线 ──
    const drawLine = (arr, color, lw=1) => {
      ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.beginPath()
      arr.forEach((v, i) => {
        const x = padL + i * barW + barW / 2
        i === 0 ? ctx.moveTo(x, py(v)) : ctx.lineTo(x, py(v))
      })
      ctx.stroke()
    }
    drawLine(bollArr.map(b => b.upper), '#bb86fc', 0.8)
    drawLine(bollArr.map(b => b.mid),   '#666',    0.7)
    drawLine(bollArr.map(b => b.lower), '#03dac6', 0.8)

    // ── MA 线 ──
    drawLine(ma5,  '#ffa657', 1)
    drawLine(ma10, '#58a6ff', 1)

    // ── 蜡烛图 ──
    data.forEach((b, i) => {
      const x    = padL + i * barW + barW / 2
      const isUp = b.close >= b.open
      const col  = isUp ? '#ff4d6d' : '#00d68f'
      const oY   = py(b.open), cY = py(b.close)
      const hY   = py(b.high), lY = py(b.low)

      // 影线
      ctx.strokeStyle = col; ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(x, hY); ctx.lineTo(x, lY); ctx.stroke()

      // 实体
      const top  = Math.min(oY, cY)
      const bh   = Math.max(1, Math.abs(cY - oY))
      ctx.fillStyle = col
      ctx.fillRect(x - bBody / 2, top, bBody, bh)
    })

    // ── 成交量柱 ──
    data.forEach((b, i) => {
      const x   = padL + i * barW + barW / 2
      const col = b.close >= b.open ? '#ff4d6d' : '#00d68f'
      const top = vy(b.volume)
      ctx.fillStyle = col + '99'  // 半透明
      ctx.fillRect(x - bBody / 2, top, bBody, volY + volH - top)
    })

    // ── MACD 柱 ──
    data.forEach((b, i) => {
      const x   = padL + i * barW + barW / 2
      const v   = macdObj.bar[i]
      const top = v >= 0 ? my(v) : macdMidY
      const bh  = Math.max(1, Math.abs(my(v) - macdMidY))
      ctx.fillStyle = v >= 0 ? '#ff4d6d99' : '#00d68f99'
      ctx.fillRect(x - bBody / 2, top, bBody, bh)
    })

    // ── DIF / DEA 线 ──
    const drawMACDLine = (arr, color) => {
      ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.beginPath()
      arr.forEach((v, i) => {
        const x = padL + i * barW + barW / 2
        i === 0 ? ctx.moveTo(x, my(v)) : ctx.lineTo(x, my(v))
      })
      ctx.stroke()
    }
    drawMACDLine(macdObj.dif, '#ffa657')
    drawMACDLine(macdObj.dea, '#58a6ff')

    // ── 插针信号标记箭头（只标真实插针，过滤十字星和微小波动） ──
    data.forEach((b, i) => {
      const x = padL + i * barW + barW / 2
      const body    = Math.abs(b.close - b.open)
      const kRange  = b.high - b.low
      const lowerSh = Math.min(b.open, b.close) - b.low
      const upperSh = b.high - Math.max(b.open, b.close)
      const minBody = b.close * 0.0003   // 实体至少0.03%，过滤十字星
      const minSh   = b.close * 0.001    // 影线至少0.1%，过滤微波动
      const isLong  = body >= minBody && lowerSh >= body * 1.5 && lowerSh >= minSh && b.close > (b.low + kRange * 0.5)
      const isShort = body >= minBody && upperSh >= body * 1.5 && upperSh >= minSh && b.close < (b.high - kRange * 0.5)
      if (isLong) {
        const ay = py(b.low) + 6
        ctx.fillStyle = '#00e676'
        ctx.font = `bold ${Math.max(9, barW)}px sans-serif`; ctx.textAlign = 'center'
        ctx.fillText('▲', x, ay + 10)
        if (barW > 5) {
          ctx.fillStyle = 'rgba(0,230,118,0.6)'
          ctx.font = '7px sans-serif'
          ctx.fillText('多', x, ay + 20)
        }
      } else if (isShort) {
        const ay = py(b.high) - 6
        ctx.fillStyle = '#ff4d6d'
        ctx.font = `bold ${Math.max(9, barW)}px sans-serif`; ctx.textAlign = 'center'
        ctx.fillText('▼', x, ay - 6)
        if (barW > 5) {
          ctx.fillStyle = 'rgba(255,77,109,0.6)'
          ctx.font = '7px sans-serif'
          ctx.fillText('空', x, ay - 16)
        }
      }
    })

    // ── 右上角显示当前根数 ──
    ctx.fillStyle = 'rgba(88,166,255,0.7)'; ctx.font = '9px sans-serif'; ctx.textAlign = 'right'
    ctx.fillText(`${n}根`, W - padR - 2, mainY + 12)

    // ── 区域标签 ──
    ctx.fillStyle = '#484f58'; ctx.font = '9px sans-serif'; ctx.textAlign = 'left'
    ctx.fillText('VOL', padL + 2, volY + 10)
    ctx.fillText('MACD(12,26,9)', padL + 2, macdY + 11)

    // 存指标备触摸
    this._chartIndicators = { bollArr, ma5, ma10, macdObj }
    this._chartLayout = { padL, padR, padTop, padBot, innerW, mainH, volH, macdH,
                          mainY, volY, macdY, barW, n, priceHi, priceLo }
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
        this._view = Math.max(10, Math.min(240, newView))
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
        const maxOff = Math.max(0, (this._allBars ? this._allBars.length : 120) - (this._view || 120))
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

    ctx.strokeStyle = '#58a6ff88'; ctx.lineWidth = 0.8; ctx.setLineDash([3, 3])
    ctx.beginPath(); ctx.moveTo(cx, mainY); ctx.lineTo(cx, macdY + macdH); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(padL, cy);  ctx.lineTo(W - padR, cy);       ctx.stroke()
    ctx.setLineDash([])

    ctx.fillStyle = '#58a6ff'
    ctx.fillRect(W - padR + 1, cy - 7, padR - 2, 14)
    ctx.fillStyle = '#0d1117'; ctx.font = 'bold 9px sans-serif'; ctx.textAlign = 'left'
    ctx.fillText(b.close >= 10000 ? b.close.toFixed(0) : b.close.toFixed(1), W - padR + 3, cy + 3)

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
    const maxOff = Math.max(0, (this._allBars ? this._allBars.length : 120) - (this._view || 120))
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

  switchInterval(e) {
    const iv    = e.currentTarget.dataset.iv
    const label = e.currentTarget.dataset.label
    if (iv === this.data.interval) return  // 同一周期不重复加载

    clearSignalCache(iv)        // 清该周期缓存，保证拿最新
    this._loadAborted = true    // 标记中断旧请求（loadData 里判断）
    this._dragOffset  = 0
    this._allBars     = null
    this._chartData   = null
    this._view        = 120
    // 先强制清loading状态，再同步切周期+立即开始新请求
    this.setData({ loading: false, interval: iv, intervalLabel: label, klineView: 120 })
    this._drawLoading(iv)       // 立刻在canvas画"加载中"，用户有即时反馈
    this._loadAborted = false   // 复位中断标记
    this._loadData(iv)          // 直接传入iv，不依赖异步setData
  },
  refresh() { clearSignalCache(this.data.interval); this._loadData(this.data.interval) },
  toggleTips() { this.setData({ showTips: !this.data.showTips }) },
  toggleMorePeriods() { this.setData({ showMorePeriods: !this.data.showMorePeriods }) },

  // 公开入口（定时器/下拉刷新用）
  loadData() { this._loadData(this.data.interval) },

  async _loadData(iv) {
    // 用传入的iv而不是this.data.interval，避免setData异步未完成时读到旧值
    if (this._loading) {
      // 如果已有请求在跑，先取消它的结果（通过_loadSeq版本号）
    }
    const seq = (this._loadSeq = (this._loadSeq || 0) + 1)
    this.setData({ loading: true, errorMsg: '' })
    try {
      const sig = await detectSignal(iv)
      // 版本号不对说明又切换了周期，丢弃这次结果
      if (seq !== this._loadSeq) return
      this._renderAll(sig)
    } catch (e) {
      if (seq !== this._loadSeq) return
      this.setData({ errorMsg: e.message || '数据获取失败，请检查网络' })
    } finally {
      if (seq === this._loadSeq) this.setData({ loading: false })
    }
  },

  _renderAll(sig) {
    const bars   = sig.bars
    const last   = bars[bars.length - 1]
    const prev   = bars[bars.length - 2]

    // 价格
    const chg = (last.close - prev.close) / prev.close * 100
    const dir = chg >= 0 ? 'up' : 'down'

    // 24h / 4h 概况（用已有bars估算）
    const bar24hAgo = bars[Math.max(0, bars.length - 96)]  // 15m×96=24h
    const bar4hAgo  = bars[Math.max(0, bars.length - 16)]
    const chg24h    = (last.close - bar24hAgo.close) / bar24hAgo.close * 100
    const chg4h     = sig.drop4h !== undefined ? sig.drop4h : (last.close - bar4hAgo.close) / bar4hAgo.close * 100
    const vol24hSum = bars.slice(-96).reduce((s,b) => s + b.volume, 0)

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
      score      = sig.score          // 现在是0~100
      scoreStars = toStars(score)
      scoreBar   = score              // 直接用，0~100即为百分比
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

      if (score >= 80) {
        decisionState   = sig.type === 'long' ? 'buy' : 'short_s'
        decisionFace    = sig.type === 'long' ? '🚀' : '📉'
        decisionVerdict = sig.type === 'long' ? '强烈推荐做多！' : '强烈推荐做空！'
        decisionSub     = sig.type === 'long' ? '多指标共振，优先把握机会' : '上影插针确认，注意控仓'
        scoreLabel      = '强烈推荐'
      } else if (score >= 60) {
        decisionState   = 'ok'
        decisionFace    = sig.type === 'long' ? '📈' : '📉'
        decisionVerdict = '✅ 建议做' + (sig.type === 'long' ? '多' : '空')
        decisionSub     = '信号中等，轻仓跟进，严控止损'
        scoreLabel      = '建议做'
      } else if (score >= 40) {
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


    // 趋势信息（MA20/MA60计算）
    const closes = bars.map(b => b.close)
    const ma = (arr, n) => {
      if (arr.length < n) return arr[arr.length - 1]
      return arr.slice(-n).reduce((s, v) => s + v, 0) / n
    }
    const ma20v = ma(closes, 20)
    const ma60v = ma(closes, 60)
    const lastClose = bars[bars.length - 1].close
    // 支撑/压力：近20根最低/最高
    const recentLows  = bars.slice(-20).map(b => b.low)
    const recentHighs = bars.slice(-20).map(b => b.high)
    const trendSupport = fmtPrice(Math.min(...recentLows))
    const trendResist  = fmtPrice(Math.max(...recentHighs))
    const trendMa20    = fmtPrice(ma20v)
    const trendMa60    = fmtPrice(ma60v)
    const trendMa20Dir = lastClose > ma20v ? 'red' : 'green'
    const trendMa60Dir = lastClose > ma60v ? 'red' : 'green'
    // 趋势判断
    let trendColor, trendLabel, trendIcon
    if (lastClose > ma20v && ma20v > ma60v) {
      trendColor = 'bull';     trendLabel = '多头趋势'; trendIcon = '🐂'
    } else if (lastClose > ma20v && ma20v <= ma60v) {
      trendColor = 'bull_w';   trendLabel = '弱多趋势'; trendIcon = '🐸'
    } else if (lastClose < ma20v && ma20v < ma60v) {
      trendColor = 'bear';     trendLabel = '空头趋势'; trendIcon = '🐻'
    } else if (lastClose < ma20v && ma20v >= ma60v) {
      trendColor = 'bear_w';   trendLabel = '弱空趋势'; trendIcon = '😬'
    } else {
      trendColor = 'sideways'; trendLabel = '震荡盘整'; trendIcon = '🐸'
    }
    const isBearTrend = trendColor === 'bear' || trendColor === 'bear_w'

    const trendInfo = sig.trendInfo || null
    // aiLabel: 有信号时显示方向，无信号时空白
    const aiLabel = hasSignal
      ? (sig.type === 'long' ? '📈 做多信号' : '📉 做空信号')
      : ''

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

      // AI & 趋势
      isBearTrend,
      aiLabel,
      trendColor, trendLabel, trendIcon,
      trendMa20, trendMa60, trendMa20Dir, trendMa60Dir,
      trendSupport, trendResist,

      // 无信号时的参考止盈止损（基于当前价±0.3%）
      ...(() => {
        const p = last.close
        const dist = p * 0.003   // 0.3% 作为参考止损距离
        const sl  = fmtPrice(p - dist)
        const tp1r = fmtPrice(p + dist * 1.0)
        const tp2r = fmtPrice(p + dist * 1.5)
        const tp3r = fmtPrice(p + dist * 2.5)
        return {
          refSL:     sl,    refSLPct:  '-0.30%',
          refTP1:    tp1r,  refTP1Pct: '+0.30%',
          refTP2:    tp2r,  refTP2Pct: '+0.45%',
          refTP3:    tp3r,  refTP3Pct: '+0.75%',
        }
      })(),
    })

    // 画 K线图
    this._drawChart(bars)
  },

  // ══ 激活码 / 会员 ══
  onCodeInput(e) { this.setData({ codeInput: e.detail.value.trim().toUpperCase() }) },
  submitCode() {
    const code = (this.data.codeInput || '').toUpperCase().trim()
    if (!code) return wx.showToast({ title: '请输入激活码', icon: 'none' })
    const used = wx.getStorageSync('used_codes') || []
    if (used.includes(code)) return wx.showToast({ title: '该码已使用过', icon: 'none' })
    const now = new Date()
    // 格式验证（不验证日期，避免跨月/跨年失效）
    // 月卡：BTC-M-YYYYMM-XXXX
    const isMonth = /^BTC-M-\d{6}-.+$/.test(code)
    // 年卡：BTC-Y-YYYY-XXXX
    const isYear  = /^BTC-Y-\d{4}-.+$/.test(code)
    // 永久：BTC-LT-XXXX（任意长度尾号）
    const isLife  = /^BTC-LT-.+$/.test(code)
    if (!isMonth && !isYear && !isLife) return wx.showToast({ title: '激活码无效，请检查', icon: 'none' })
    used.push(code)
    wx.setStorageSync('used_codes', used)
    wx.setStorageSync('isVip', true)
    if (isMonth) {
      const exp = new Date(now); exp.setMonth(exp.getMonth()+1)
      wx.setStorageSync('vip_exp', exp.getTime())
      wx.setStorageSync('vip_type', '月卡')
    } else if (isYear) {
      const exp = new Date(now); exp.setFullYear(exp.getFullYear()+1)
      wx.setStorageSync('vip_exp', exp.getTime())
      wx.setStorageSync('vip_type', '年卡')
    } else {
      wx.setStorageSync('vip_exp', 9999999999999)
      wx.setStorageSync('vip_type', '永久会员')
    }
    clearInterval(this._trialTimer)
    const vipType = isMonth ? '月卡(30天)' : isYear ? '年卡(365天)' : '永久会员'
    this.setData({ isVip: true, inTrial: true, codeInput: '' })
    wx.showModal({
      title: '🎉 激活成功！',
      content: `已开通 ${vipType}\n祝您交易顺利，稳定盈利！`,
      showCancel: false
    })
  },
  // 隐藏入口：footer连点5次 → 管理后台
  _footerTaps: 0,
  onFooterTap() {
    this._footerTaps = (this._footerTaps || 0) + 1
    if (this._footerTaps >= 5) { this._footerTaps = 0; wx.navigateTo({ url: '/pages/admin/admin' }) }
    setTimeout(() => { this._footerTaps = 0 }, 3000)  // 3s内完成5次点击
  },
  // 密码输入（弹框，6666=临时体验，8888=管理后台）
  onPasswordInput(e) { this.setData({ pwdInput: e.detail.value }) },
  submitPassword() {
    const pwd = this.data.pwdInput || ''
    if (pwd === '6666') {
      this.setData({ isVip: true, inTrial: true, pwdInput: '', showPwdDialog: false })
      wx.showToast({ title: '体验模式已开启', icon: 'success' })
    } else if (pwd === '8888') {
      this.setData({ pwdInput: '', showPwdDialog: false })
      wx.navigateTo({ url: '/pages/admin/admin' })
    } else {
      wx.showToast({ title: '密码错误', icon: 'none' })
    }
  },
  showPwdEntry() { this.setData({ showPwdDialog: true, pwdInput: '' }) },
  closePwdDialog() { this.setData({ showPwdDialog: false }) },

  // ══ 会员升级抽屉 ══
  showVipDrawer() { this.setData({ showVipDrawer: true }) },
  hideVipDrawer() { this.setData({ showVipDrawer: false }) },

  // ══ 免责声明 ══
  agreeDisclaimer() {
    wx.setStorageSync('disclaimer_agreed', true)
    this.setData({ showDisclaimer: false })
  },
  rejectDisclaimer() {
    wx.showModal({
      title: '提示',
      content: '您需要同意风险提示才能继续使用',
      showCancel: false,
      success: () => {
        // 再次显示免责声明，不允许跳过
        this.setData({ showDisclaimer: true })
      }
    })
  },

  // ══ CTA联系按钮 ══
  onCtaContact() {
    // 将微信号复制到剪贴板
    wx.setClipboardData({
      data: 'weber00vip',   // ← 替换为你的真实微信号
      success: () => {
        wx.showModal({
          title: '微信号已复制 ✅',
          content: '微信号：weber00vip\n\n请添加好友，告知需要哪个套餐，付款后发送激活码给您',
          showCancel: false
        })
      }
    })
  },
})
