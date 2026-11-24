import type { Dict } from '../../i18n'

export type RunStrings = {
  title: string
  lead: string
  assistant: string
  assistantNote: string
  loading: string
  empty: string
  emptyHow: string
  error: string
  question: string
  asOf: string
  rules: string
  ruleRank: string
  ruleFilter: string
  ruleHold: string
  ruleSharia: string
  rulePeriod: string
  ruleCosts: string
  asc: string
  desc: string
  freq_D: string
  freq_W: string
  freq_M: string
  freq_Q: string
  freq_A: string
  result: string
  annual: string
  drawdown: string
  sharpe: string
  turnover: string
  curve: string
  curveRange: string
  holdings: string
  weight: string
  shariaCompliant: string
  shariaNon: string
  shariaUnknown: string
  receipt: string
  receiptLead: string
  specHash: string
  dataVersion: string
  engine: string
  notes: string
  notesCount: string
  example1: string
  example2: string
  example3: string
  askLabel: string
  askPlaceholder: string
  askButton: string
  asking: string
  askInvalid: string
  askUnavailable: string
  askFailed: string
  refusal_execution: string
  refusal_guarantee: string
  refusal_advice: string
  explanation: string
  explanationNote: string
  claimsDropped: string
  claimsError: string
  // One key per factor the engine registers; an id with no key is shown as itself.
  factor_debt_ratio: string
  factor_dividend_yield: string
  factor_momentum_6m: string
  factor_momentum_12_1: string
  factor_return_1m: string
  factor_volatility_60d: string
}

export const strings: Dict<RunStrings> = {
  zh: {
    title: '提问',
    lead: '用日常语言提问。引擎在历史数据上测试，下面的每个数字都来自引擎，没有估算。',
    assistant: '研究助手',
    assistantNote: '通用聊天，没有经过引擎检查。数字不可信。',
    loading: '正在读取结果…',
    empty: '还没有运行结果。',
    emptyHow: '用引擎生成一份：',
    error: '无法读取这份结果。',
    question: '问题',
    asOf: '截至 {date}',
    rules: '规则',
    ruleRank: '按 {list} 排名',
    ruleFilter: '只保留 {list}',
    ruleHold: '持有 {k} 只；每次调仓最多换 {n} 只；{freq}调仓',
    ruleSharia: '先过 Sharia 筛选：只有合规的名字才参与排名',
    rulePeriod: '区间 {start} 至 {end}',
    ruleCosts: '成本：每单位成交，手续费 {fee}，滑点 {slip}',
    asc: '越低越靠前',
    desc: '越高越靠前',
    freq_D: '每日',
    freq_W: '每周',
    freq_M: '每月',
    freq_Q: '每季',
    freq_A: '每年',
    result: '结果',
    annual: '年化收益',
    drawdown: '最大回撤',
    sharpe: '夏普',
    turnover: '年换手',
    curve: '净值曲线（已扣成本）',
    curveRange: '从 {from} 到 {to}',
    holdings: '持仓',
    weight: '权重',
    shariaCompliant: '合规',
    shariaNon: '不合规',
    shariaUnknown: '未验证',
    receipt: '凭证',
    receiptLead: '同一份规则、同一份数据、同一版引擎，会得到同一个结果。',
    specHash: '规则哈希',
    dataVersion: '数据版本',
    engine: '引擎',
    notes: '注意',
    notesCount: '{n} 条数据限制，点开查看',
    example1: '负债低、股息高的公司',
    example2: '过去六个月涨得最好的前 10 只',
    example3: '符合 Sharia 的低波动股票',
    askLabel: '用你自己的话提问',
    askPlaceholder: '负债低、股息高',
    askButton: '运行',
    asking: '处理中…',
    askInvalid: '模型没能把这句话变成引擎能运行的规则。换个说法再试。',
    askUnavailable: '这台服务器还没有设置提问功能。',
    askFailed: '这个问题没有得到回答，请重试。',
    refusal_execution: '这个工具不下单。请描述你想测试的规则。',
    refusal_guarantee: '没有任何策略能保证结果。请描述你想测试的规则。',
    refusal_advice: '这个工具不说该买还是该卖。请描述你想测试的规则。',
    explanation: '文字说明',
    explanationNote: '文字由模型写成，其中每个数字都来自下面的结果。',
    claimsDropped: '有 {n} 句因为自带数字而被略去。',
    claimsError: '说明没能写成。运行结果在下面。',
    factor_debt_ratio: '负债率',
    factor_dividend_yield: '股息率',
    factor_momentum_6m: '6 个月动量',
    factor_momentum_12_1: '12 减 1 个月动量',
    factor_return_1m: '近 1 个月收益',
    factor_volatility_60d: '60 日波动率',
  },
  en: {
    title: 'Ask',
    lead: 'Ask in plain words. The engine tests it on history; every number below came from the engine and nothing here is estimated.',
    assistant: 'Research assistant',
    assistantNote: 'A general chat. The engine has not checked it, so do not trust its numbers.',
    loading: 'Reading the run…',
    empty: 'No run yet.',
    emptyHow: 'Write one with the engine:',
    error: 'This result could not be read.',
    question: 'Question',
    asOf: 'As of {date}',
    rules: 'Rules',
    ruleRank: 'Rank by {list}',
    ruleFilter: 'Keep only {list}',
    ruleHold: 'Hold {k} names; replace at most {n} at each rebalance; rebalance {freq}',
    ruleSharia: 'Sharia screen first: only compliant names are ranked',
    rulePeriod: 'Period {start} to {end}',
    ruleCosts: 'Costs: fee {fee}, slippage {slip}, per unit traded',
    asc: 'lower first',
    desc: 'higher first',
    freq_D: 'daily',
    freq_W: 'weekly',
    freq_M: 'monthly',
    freq_Q: 'quarterly',
    freq_A: 'yearly',
    result: 'Result',
    annual: 'Annual return',
    drawdown: 'Max drawdown',
    sharpe: 'Sharpe',
    turnover: 'Turnover a year',
    curve: 'Equity curve, net of costs',
    curveRange: 'From {from} to {to}',
    holdings: 'Holdings',
    weight: 'Weight',
    shariaCompliant: 'Compliant',
    shariaNon: 'Not compliant',
    shariaUnknown: 'Unproven',
    receipt: 'Receipt',
    receiptLead: 'The same spec on the same data with the same engine gives the same result.',
    specHash: 'Spec',
    dataVersion: 'Data',
    engine: 'Engine',
    notes: 'Notes',
    notesCount: '{n} limits on the data. Tap to read.',
    example1: 'Low debt and a high dividend',
    example2: 'Top 10 by six-month momentum',
    example3: 'Sharia-compliant, low volatility',
    askLabel: 'Ask in your own words',
    askPlaceholder: 'Low debt, high dividend',
    askButton: 'Run',
    asking: 'Working…',
    askInvalid: 'The model could not turn this into rules the engine can run. Try saying it differently.',
    askUnavailable: 'Questions are not set up on this server yet.',
    askFailed: 'The question could not be answered. Try again.',
    refusal_execution: 'This tool does not place orders. Describe the rules you want to test instead.',
    refusal_guarantee: 'No strategy has a guaranteed result. Describe the rules you want to test instead.',
    refusal_advice: 'This tool does not say what to buy or sell. Describe the rules you want to test instead.',
    explanation: 'In words',
    explanationNote: 'The model wrote the words. Every number in them comes from the result below.',
    claimsDropped: '{n} sentences were left out because they carried a number of their own.',
    claimsError: 'The explanation could not be written. The run itself is below.',
    factor_debt_ratio: 'Debt ratio',
    factor_dividend_yield: 'Dividend yield',
    factor_momentum_6m: '6-month momentum',
    factor_momentum_12_1: '12-1 month momentum',
    factor_return_1m: '1-month return',
    factor_volatility_60d: '60-day volatility',
  },
  ar: {
    title: 'اسأل',
    lead: 'اسأل بكلمات بسيطة. يختبر المحرك السؤال على بيانات الماضي، وكل رقم أدناه جاء من المحرك ولا شيء هنا مقدَّر.',
    assistant: 'مساعد البحث',
    assistantNote: 'محادثة عامة لم يفحصها المحرك، فلا تثق بأرقامها.',
    loading: 'جارٍ قراءة النتيجة…',
    empty: 'لا توجد نتيجة بعد.',
    emptyHow: 'أنشئ واحدة بالمحرك:',
    error: 'تعذّرت قراءة هذه النتيجة.',
    question: 'السؤال',
    asOf: 'حتى {date}',
    rules: 'القواعد',
    ruleRank: 'الترتيب حسب {list}',
    ruleFilter: 'الإبقاء فقط على {list}',
    ruleHold: 'الاحتفاظ بـ {k} سهمًا؛ استبدال {n} كحدٍّ أقصى عند كل إعادة توازن؛ إعادة التوازن {freq}',
    ruleSharia: 'الفحص الشرعي أولًا: لا يُرتَّب إلا ما كان متوافقًا',
    rulePeriod: 'الفترة من {start} إلى {end}',
    ruleCosts: 'التكاليف: رسوم {fee} وانزلاق {slip} لكل وحدة منفَّذة',
    asc: 'الأقل أولًا',
    desc: 'الأعلى أولًا',
    freq_D: 'يوميًا',
    freq_W: 'أسبوعيًا',
    freq_M: 'شهريًا',
    freq_Q: 'ربع سنويًا',
    freq_A: 'سنويًا',
    result: 'النتيجة',
    annual: 'العائد السنوي',
    drawdown: 'أقصى تراجع',
    sharpe: 'نسبة شارب',
    turnover: 'الدوران السنوي',
    curve: 'منحنى القيمة بعد التكاليف',
    curveRange: 'من {from} إلى {to}',
    holdings: 'المراكز',
    weight: 'الوزن',
    shariaCompliant: 'متوافق',
    shariaNon: 'غير متوافق',
    shariaUnknown: 'غير مثبت',
    receipt: 'الإيصال',
    receiptLead: 'نفس القواعد على نفس البيانات بنفس المحرك تعطي نفس النتيجة.',
    specHash: 'القواعد',
    dataVersion: 'البيانات',
    engine: 'المحرك',
    notes: 'ملاحظات',
    notesCount: '{n} قيود على البيانات. اضغط للقراءة.',
    example1: 'ديون قليلة وتوزيعات عالية',
    example2: 'أفضل 10 أسهم في الزخم لستة أشهر',
    example3: 'متوافق مع الشريعة وتقلب منخفض',
    askLabel: 'اسأل بكلماتك',
    askPlaceholder: 'ديون قليلة وتوزيعات عالية',
    askButton: 'شغّل',
    asking: 'جارٍ العمل…',
    askInvalid: 'تعذّر على النموذج تحويل هذا إلى قواعد يستطيع المحرك تشغيلها. جرّب صياغة أخرى.',
    askUnavailable: 'لم يُهيَّأ هذا الخادم للأسئلة بعد.',
    askFailed: 'تعذّرت الإجابة عن السؤال. حاول مرة أخرى.',
    refusal_execution: 'لا تنفّذ هذه الأداة أوامر. صِف القواعد التي تريد اختبارها.',
    refusal_guarantee: 'لا توجد استراتيجية نتيجتها مضمونة. صِف القواعد التي تريد اختبارها.',
    refusal_advice: 'لا تقول هذه الأداة ماذا تشتري أو تبيع. صِف القواعد التي تريد اختبارها.',
    explanation: 'بالكلمات',
    explanationNote: 'كتب النموذج الكلمات. كل رقم فيها يأتي من النتيجة أدناه.',
    claimsDropped: 'حُذفت جمل بعدد {n} لأنها حملت أرقامًا خاصة بها.',
    claimsError: 'تعذّرت كتابة الشرح. نتيجة التشغيل أدناه.',
    factor_debt_ratio: 'نسبة الدين',
    factor_dividend_yield: 'عائد التوزيعات',
    factor_momentum_6m: 'الزخم لستة أشهر',
    factor_momentum_12_1: 'زخم 12 شهرًا دون آخر شهر',
    factor_return_1m: 'عائد شهر واحد',
    factor_volatility_60d: 'تقلب 60 يومًا',
  },
}
