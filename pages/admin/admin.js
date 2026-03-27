// pages/admin/admin.js
// 管理员密码（你自己记住，不要告诉任何人）
const ADMIN_PWD = '8888'

// 各类型价格（用于统计收入）
const PRICE_MAP = { month: 68, quarter: 168, year: 498 }
// 各类型天数
const DAYS_MAP  = { month: 31, quarter: 92, year: 365 }
// 各类型中文
const LABEL_MAP = { month: '月卡', quarter: '季卡', year: '年卡' }

Page({
  data: {
    unlocked: false,
    pwd: '',
    pwdErr: '',

    genType: 'quarter',   // 默认季卡
    lastCode: '',
    lastCodeMeta: '',

    issuedCodes: [],      // 已发出的码列表
    totalRevenue: 0,
    unusedCount: 0,
    usedCount: 0,
  },

  onLoad() {
    // 已解锁过就不用重新输密码（当天有效）
    const unlockedToday = wx.getStorageSync('admin_unlocked_date')
    const today = new Date().toLocaleDateString('zh-CN')
    if (unlockedToday === today) {
      this.setData({ unlocked: true })
      this._loadIssuedCodes()
    }
  },

  // ── 密码 ──
  onPwdInput(e) {
    this.setData({ pwd: e.detail.value, pwdErr: '' })
  },
  submitPwd() {
    if (this.data.pwd === ADMIN_PWD) {
      const today = new Date().toLocaleDateString('zh-CN')
      wx.setStorageSync('admin_unlocked_date', today)
      this.setData({ unlocked: true, pwdErr: '' })
      this._loadIssuedCodes()
    } else {
      this.setData({ pwdErr: '密码错误' })
      wx.vibrateShort({ type: 'heavy' })
    }
  },

  // ── 类型选择 ──
  setGenType(e) {
    this.setData({ genType: e.currentTarget.dataset.type, lastCode: '', lastCodeMeta: '' })
  },

  // ── 生成激活码 ──
  generateCode() {
    const type = this.data.genType
    const now = new Date()
    const year = now.getFullYear()
    const month = String(now.getMonth() + 1).padStart(2, '0')
    const quarter = Math.ceil((now.getMonth() + 1) / 3)

    // 加随机4位尾号防碰撞（同一期可发多个）
    const rand = String(Math.floor(1000 + Math.random() * 9000))

    let code = ''
    if (type === 'month')   code = `BTC-M-${year}${month}-${rand}`
    if (type === 'quarter') code = `BTC-Q-${year}Q${quarter}-${rand}`
    if (type === 'year')    code = `BTC-Y-${year}-${rand}`

    const days = DAYS_MAP[type]
    const expireDate = new Date(Date.now() + days * 86400000).toLocaleDateString('zh-CN')
    const meta = `${LABEL_MAP[type]} · 有效期${days}天 · 到期${expireDate}`

    // 存到已发出列表
    const issued = wx.getStorageSync('admin_issued_codes') || []
    issued.unshift({
      code,
      type: LABEL_MAP[type],
      days,
      price: PRICE_MAP[type],
      used: false,
      createdAt: now.toLocaleDateString('zh-CN'),
    })
    wx.setStorageSync('admin_issued_codes', issued)

    // 同步到用户侧有效码（这样用户输入新生成的码也能验证）
    const validCodes = wx.getStorageSync('extra_valid_codes') || {}
    validCodes[code] = { type: LABEL_MAP[type], days }
    wx.setStorageSync('extra_valid_codes', validCodes)

    this.setData({ lastCode: code, lastCodeMeta: meta })
    this._loadIssuedCodes()
  },

  // ── 复制激活码 ──
  copyCode(e) {
    const code = e.currentTarget.dataset.code
    wx.setClipboardData({
      data: code,
      success() { wx.showToast({ title: '已复制', icon: 'success' }) }
    })
  },

  // ── 加载已发出列表 ──
  _loadIssuedCodes() {
    // 同步used状态（用户用过的码标记为已使用）
    const issued    = wx.getStorageSync('admin_issued_codes') || []
    const usedCodes = wx.getStorageSync('used_codes') || []

    issued.forEach(item => {
      if (usedCodes.includes(item.code)) item.used = true
    })
    wx.setStorageSync('admin_issued_codes', issued)

    const revenue = issued
      .filter(i => i.used)
      .reduce((sum, i) => sum + (i.price || 0), 0)

    const usedCount   = issued.filter(i => i.used).length
    const unusedCount = issued.length - usedCount

    this.setData({ issuedCodes: issued, totalRevenue: revenue, usedCount, unusedCount })
  },
})
