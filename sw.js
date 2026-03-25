// BTC监控 Service Worker v1.0
// 负责：后台运行、定时扫描信号、推送系统通知

const CACHE_NAME = 'btc-monitor-v1';
const SCAN_INTERVAL = 15 * 60 * 1000; // 15分钟扫描一次
const API_BASE = 'https://data-api.binance.vision';
const SYMBOL = 'BTCUSDT';

// ─── 安装 ───
self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(clients.claim());
  // 启动后台定时扫描
  startBackgroundScan();
});

// ─── 接收主页面消息 ───
self.addEventListener('message', e => {
  if (e.data && e.data.type === 'START_SCAN') {
    startBackgroundScan();
  }
  if (e.data && e.data.type === 'TEST_NOTIFY') {
    sendNotification('🔔 通知测试', 'BTC监控已成功开启推送！信号出现时会震动通知你 📳', { test: true });
  }
});

// ─── 后台定时扫描 ───
let scanTimer = null;
function startBackgroundScan() {
  if (scanTimer) clearInterval(scanTimer);
  // 立即扫描一次
  scanSignal();
  // 每15分钟扫描
  scanTimer = setInterval(scanSignal, SCAN_INTERVAL);
}

// ─── 核心扫描逻辑 ───
async function scanSignal() {
  try {
    const now = new Date();
    const hour = now.getHours();
    // 凌晨过滤
    if (hour >= 0 && hour < 6) return;

    const resp = await fetch(`${API_BASE}/api/v3/klines?symbol=${SYMBOL}&interval=15m&limit=100`);
    if (!resp.ok) return;
    const klines = await resp.json();

    const pin_k  = klines[klines.length - 2];
    const next_k = klines[klines.length - 1];

    const o = +pin_k[1], h = +pin_k[2], l = +pin_k[3], c = +pin_k[4], v = +pin_k[5];
    const n_o = +next_k[1], n_l = +next_k[3], n_c = +next_k[4];

    const body = Math.abs(c - o);
    const lower = Math.min(o, c) - l;
    const upper = h - Math.max(o, c);
    const rng = h - l;
    const closePos = rng > 0 ? (c - l) / rng : 0.5;

    const prev5vol = klines.slice(-7, -2).reduce((s, k) => s + (+k[5]), 0) / 5;

    // 条件1: 下影插针
    const cond1 = ((body > 0 && lower >= body * 1.5) || (body === 0 && lower > upper * 2)) && closePos >= 0.5;
    // 条件2: 低点抬高+收涨
    const cond2 = n_l > l && n_c > n_o;
    // 条件3: 放量
    const cond3 = v >= prev5vol * 1.3;

    // MACD
    const closes = klines.map(k => +k[4]);
    const emaFn = (arr, p) => {
      const k = 2 / (p + 1); let e = [arr[0]];
      for (let i = 1; i < arr.length; i++) e.push(arr[i] * k + e[i-1] * (1 - k));
      return e;
    };
    const ef = emaFn(closes, 12), es = emaFn(closes, 26);
    const dif = ef.map((v, i) => v - es[i]);
    const dea = emaFn(dif, 9);
    const bar = dif.map((v, i) => 2 * (v - dea[i]));
    const n = bar.length - 1;
    const macdGold = dif[n-1] < dea[n-1] && dif[n] >= dea[n];
    const barUp = bar[n] > bar[n-1];
    const cond4 = macdGold || barUp;

    // 4H跌幅过滤
    const resp4h = await fetch(`${API_BASE}/api/v3/klines?symbol=${SYMBOL}&interval=4h&limit=3`);
    const kl4h = await resp4h.json();
    const p4hAgo = +kl4h[0][1];
    const curP = closes[closes.length - 1];
    const ch4h = (curP - p4hAgo) / p4hAgo * 100;
    const filterDrop = ch4h <= -8;

    const hasSignal = cond1 && cond2 && cond3 && cond4 && !filterDrop;

    // 通知主页面当前状态
    const allClients = await clients.matchAll({ type: 'window' });
    const score = (cond1?2:0)+(cond2?2:0)+(cond3?1:0)+(cond4?2:0);
    allClients.forEach(client => {
      client.postMessage({
        type: 'SCAN_RESULT',
        hasSignal,
        score,
        price: curP,
        pinLow: l,
        cond1, cond2, cond3, cond4,
        ch4h: ch4h.toFixed(2),
        scanTime: now.toLocaleTimeString('zh-CN')
      });
    });

    if (hasSignal) {
      const dt = new Date(+pin_k[0]);
      const timeStr = `${dt.getMonth()+1}月${dt.getDate()}日 ${dt.getHours().toString().padStart(2,'0')}:${dt.getMinutes().toString().padStart(2,'0')}`;
      sendNotification(
        '🚀 BTC插针买入信号！',
        `时间：${timeStr}\n当前价：${curP.toLocaleString()} USDT\n止损参考：${l.toLocaleString()} USDT\n评分：${score}/10 请核对SOP后操作！`,
        { price: curP, pinLow: l, score, vibrate: [200, 100, 200, 100, 400] }
      );
    }

  } catch (err) {
    console.error('[SW] 扫描出错:', err);
  }
}

// ─── 发送系统通知 ───
function sendNotification(title, body, data = {}) {
  const vibrate = data.vibrate || [300, 100, 300];
  self.registration.showNotification(title, {
    body,
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    vibrate,
    requireInteraction: !data.test, // 信号通知不自动消失
    tag: data.test ? 'test' : 'btc-signal-' + Date.now(),
    data,
    actions: [
      { action: 'open', title: '📊 查看看板' },
      { action: 'dismiss', title: '知道了' }
    ]
  });
}

// ─── 点击通知 ───
self.addEventListener('notificationclick', e => {
  e.notification.close();
  if (e.action === 'open' || !e.action) {
    e.waitUntil(
      clients.matchAll({ type: 'window' }).then(list => {
        if (list.length > 0) { list[0].focus(); return; }
        return clients.openWindow('/btc_dashboard.html');
      })
    );
  }
});
