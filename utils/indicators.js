// ───────────────────────────────────────────────
// 技术指标计算库
// ───────────────────────────────────────────────

/** EMA */
function ema(arr, n) {
  const k = 2 / (n + 1)
  const res = []
  arr.forEach((v, i) => {
    if (i === 0) { res.push(v); return }
    res.push(v * k + res[i - 1] * (1 - k))
  })
  return res
}

/** MACD(12,26,9) → { dif, dea, bar } 数组 */
function macd(closes) {
  const ema12 = ema(closes, 12)
  const ema26 = ema(closes, 26)
  const dif = ema12.map((v, i) => v - ema26[i])
  const dea = ema(dif, 9)
  const bar = dif.map((v, i) => (v - dea[i]) * 2)
  return { dif, dea, bar }
}

/** KDJ(9,3,3) */
function kdj(highs, lows, closes) {
  const n = 9
  const K = [], D = [], J = []
  closes.forEach((c, i) => {
    const start = Math.max(0, i - n + 1)
    const hh = Math.max(...highs.slice(start, i + 1))
    const ll = Math.min(...lows.slice(start, i + 1))
    const rsv = hh === ll ? 50 : (c - ll) / (hh - ll) * 100
    const kPrev = i > 0 ? K[i - 1] : 50
    const dPrev = i > 0 ? D[i - 1] : 50
    const k = kPrev * 2 / 3 + rsv / 3
    const d = dPrev * 2 / 3 + k / 3
    K.push(k); D.push(d); J.push(3 * k - 2 * d)
  })
  return { K, D, J }
}

/** RSI(14) */
function rsi(closes, n = 14) {
  const res = []
  for (let i = 0; i < closes.length; i++) {
    if (i < n) { res.push(50); continue }
    let gain = 0, loss = 0
    for (let j = i - n + 1; j <= i; j++) {
      const d = closes[j] - closes[j - 1]
      if (d > 0) gain += d; else loss -= d
    }
    const rs = loss === 0 ? 100 : gain / loss
    res.push(100 - 100 / (1 + rs))
  }
  return res
}

/** WR(14) */
function wr(highs, lows, closes, n = 14) {
  return closes.map((c, i) => {
    const start = Math.max(0, i - n + 1)
    const hh = Math.max(...highs.slice(start, i + 1))
    const ll = Math.min(...lows.slice(start, i + 1))
    return hh === ll ? -50 : -((hh - c) / (hh - ll)) * 100
  })
}

/** BOLL(20,2) */
function boll(closes, n = 20, mult = 2) {
  return closes.map((_, i) => {
    const start = Math.max(0, i - n + 1)
    const slice = closes.slice(start, i + 1)
    const mid = slice.reduce((a, b) => a + b) / slice.length
    const std = Math.sqrt(slice.reduce((a, b) => a + (b - mid) ** 2, 0) / slice.length)
    return { mid, upper: mid + mult * std, lower: mid - mult * std }
  })
}

/** 综合评分（满分10分） */
function calcScore(bars, macdData, kdjData, rsiArr, wrArr, bollArr, pinDir) {
  let score = 0
  const last = bars.length - 1
  const prev = last - 1

  // 低点抬高 +2
  if (bars[last].low > bars[prev].low) score += 2

  // MACD金叉或柱线抬高 +2
  const bar = macdData.bar
  if (macdData.dif[last] > macdData.dea[last] && macdData.dif[prev] <= macdData.dea[prev]) {
    score += 2 // 金叉
  } else if (bar[last] > bar[prev]) {
    score += 1 // 柱线抬高
  }

  // KDJ +2
  const { K, D, J } = kdjData
  if (pinDir === 'long') {
    if (J[last] < 20) score += 2
    else if (K[last] > D[last] && K[prev] <= D[prev]) score += 2
    else if (K[last] > D[last]) score += 1
  } else {
    if (J[last] > 80) score += 2
    else if (K[last] < D[last] && K[prev] >= D[prev]) score += 2
    else if (K[last] < D[last]) score += 1
  }

  // RSI +1
  if (pinDir === 'long' && rsiArr[last] < 35) score += 1
  else if (pinDir === 'short' && rsiArr[last] > 65) score += 1

  // WR +1
  if (pinDir === 'long' && wrArr[last] < -80) score += 1
  else if (pinDir === 'short' && wrArr[last] > -20) score += 1

  // BOLL +1
  const boll_last = bollArr[last]
  if (pinDir === 'long' && bars[last].close <= boll_last.lower * 1.005) score += 1
  else if (pinDir === 'short' && bars[last].close >= boll_last.upper * 0.995) score += 1

  return Math.min(10, score)
}

module.exports = { ema, macd, kdj, rsi, wr, boll, calcScore }
