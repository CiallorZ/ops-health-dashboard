(() => {
  'use strict';
  const domains = {
    host: { name: '基础设施', icon: '▤', color: 'blue', unit: '台主机', description: '主机资源与运行状态' },
    network: { name: '网络与服务', icon: '⌁', color: 'green', unit: '项检测', description: '连通性与服务可用性' },
    database: { name: '数据库', icon: '▱', color: 'amber', unit: '个实例', description: '连接与关键运行指标' },
    middleware: { name: '中间件', icon: '◇', color: 'red', unit: '个服务', description: '消息与应用组件' },
    cloud: { name: '云原生', icon: '⬡', color: 'blue', unit: '个资源', description: '集群与工作负载' },
  };
  const initial = [
    {id:'h1',name:'生产主机 · web-01',target:'10.20.1.11',domain:'host',status:'ok',metric:'CPU 使用率',value:'36%',history:'oooooooooooooooooooo',note:'主机资源使用处于正常范围',last:'刚刚'},
    {id:'n1',name:'核心业务 API',target:'api.example.test /health',domain:'network',status:'ok',metric:'响应延迟',value:'48 ms',history:'oooooooooooooooooooo',note:'HTTP 200 · 响应正常',last:'刚刚'},
    {id:'db1',name:'PostgreSQL · 主库',target:'db-primary.example.test:5432',domain:'database',status:'warn',metric:'连接使用率',value:'82%',history:'oooooooooooooooowwww',note:'连接使用率超过模拟预警阈值 80%',last:'2 分钟前'},
    {id:'c1',name:'生产集群 · east-1',target:'cluster-east.example.test',domain:'cloud',status:'ok',metric:'就绪节点',value:'12 / 12',history:'oooooooooooooooooooo',note:'节点均处于就绪状态',last:'刚刚'},
    {id:'m1',name:'Kafka · 消息队列',target:'kafka-01.example.test:9092',domain:'middleware',status:'fail',metric:'消费积压',value:'12,840',history:'ooooooooooooowwfffff',note:'消费者延迟超过模拟失败阈值',last:'5 分钟前'},
    {id:'h2',name:'存储节点 · disk-02',target:'10.20.1.12 /data',domain:'host',status:'warn',metric:'磁盘使用率',value:'86%',history:'oooooooooooooooowwww',note:'磁盘使用率超过模拟预警阈值 85%',last:'8 分钟前'},
    {id:'n2',name:'公网入口 · HTTPS',target:'gateway.example.test:443',domain:'network',status:'ok',metric:'证书剩余',value:'64 天',history:'oooooooooooooooooooo',note:'证书有效 · TLS 握手成功',last:'刚刚'},
    {id:'db2',name:'Redis · 缓存服务',target:'redis.example.test:6379',domain:'database',status:'ok',metric:'内存使用',value:'4.2 GB',history:'oooooooooooooooooooo',note:'缓存服务响应正常',last:'刚刚'},
    {id:'m2',name:'Nginx · 入口代理',target:'proxy.example.test:443',domain:'middleware',status:'ok',metric:'请求速率',value:'2.4k /s',history:'oooooooooooooooooooo',note:'代理服务状态正常',last:'刚刚'},
    {id:'c2',name:'订单服务 · Deployment',target:'production / orders',domain:'cloud',status:'ok',metric:'可用副本',value:'6 / 6',history:'oooooooooooooooooooo',note:'工作负载副本均可用',last:'刚刚'},
    {id:'h3',name:'生产主机 · worker-02',target:'10.20.1.21',domain:'host',status:'ok',metric:'内存使用率',value:'58%',history:'oooooooooooooooooooo',note:'内存资源使用处于正常范围',last:'刚刚'},
    {id:'n3',name:'内网 DNS 解析',target:'dns.example.test',domain:'network',status:'ok',metric:'解析耗时',value:'12 ms',history:'oooooooooooooooooooo',note:'DNS 返回模拟解析结果',last:'刚刚'},
  ];
  const statuses = {ok:'正常',warn:'预警',fail:'异常',unknown:'未知'};
  const icons = {
    overview:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    all:'<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    host:'<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M11 6.5h7M11 17.5h7"/>',
    network:'<circle cx="12" cy="12" r="9"/><path d="M3.5 12h17M12 3c3 3 4 6 4 9s-1 6-4 9c-3-3-4-6-4-9s1-6 4-9Z"/>',
    database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/>',
    middleware:'<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/><path d="M14 6h2a3 3 0 0 1 3 3v1M10 18H8a3 3 0 0 1-3-3v-1"/>',
    cloud:'<path d="M12 2.5 20.5 7v10L12 21.5 3.5 17V7L12 2.5Z"/><path d="M3.5 7 12 12l8.5-5M12 12v9.5"/>',
    events:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  };
  const icon = key => `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${icons[key] || icons.all}</svg>`;
  const trends = {
    '6h': {value:'99.96', points:'0,38 25,34 50,39 75,27 100,32 125,24 150,31 175,22 200,26 225,17 250,21 280,13', labels:['6 小时前','4 小时前','2 小时前','现在']},
    '24h': {value:'99.82', points:'0,58 24,54 47,57 70,45 94,48 117,38 140,43 163,35 186,39 210,28 233,31 256,23 280,25', labels:['00:00','06:00','12:00','18:00','现在']},
    '7d': {value:'99.74', points:'0,48 25,38 50,46 75,35 100,43 125,29 150,34 175,24 200,33 225,25 250,19 280,22', labels:['7 天前','5 天前','3 天前','1 天前','现在']},
  };
  let items = structuredClone(initial);
  let view = 'overview';
  let filter = 'all';
  let query = '';
  let period = '24h';
  let sampledAt = new Date();
  let toastTimer;
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const statusDot = status => `<i class="status-dot ${esc(status)}-dot"></i>`;
  const statusChip = status => `<span class="status ${esc(status)}">${statusDot(status)}${statuses[status] || '未知'}</span>`;
  const heartbeat = history => `<span class="heartbeat" aria-label="模拟历史状态">${[...history].map(ch => `<i class="${({w:'warn',f:'fail',u:'unknown'})[ch] || ''}"></i>`).join('')}</span>`;
  const toast = message => { const el = $('#toast'); el.textContent = message; el.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 2300); };
  document.querySelectorAll('.nav-item[data-view]').forEach(button => {
    button.querySelector('.nav-symbol').innerHTML = icon(button.dataset.view);
  });

  function setView(next) {
    view = next;
    filter = 'all';
    query = '';
    $('#search').value = '';
    document.querySelectorAll('[data-filter]').forEach(button => { const selected = button.dataset.filter === 'all'; button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected)); });
    document.querySelectorAll('.nav-item').forEach(button => { const selected = button.dataset.view === next; button.classList.toggle('active', selected); if (selected) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); });
    const label = domains[next]?.name || ({overview:'总览',all:'全部监控',events:'事件中心'})[next] || '总览';
    $('#breadcrumb').textContent = label;
    $('#page-title').textContent = next === 'overview' ? '监控总览' : label;
    $('#page-subtitle').textContent = next === 'events' ? '查看模拟事件和受影响的监控对象。' : '从服务状态出发，快速找到需要处理的问题。';
    render();
    if (next !== 'overview') $('#list-title').scrollIntoView({
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block:'start',
    });
  }

  function render() {
    const counts = Object.fromEntries(['ok','warn','fail','unknown'].map(s => [s, items.filter(item => item.status === s).length]));
    $('#signal-total').textContent = items.length;
    Object.entries(counts).forEach(([status, count]) => {
      $(`#signal-${status}`).textContent = count;
      $(`[data-segment="${status}"]`).style.flexGrow = count;
    });
    $('#stat-total').textContent = items.length;
    $('#stat-total-note').textContent = counts.unknown ? `${counts.unknown} 项状态未知` : '覆盖 5 个监控领域';
    $('#stat-ok').textContent = counts.ok;
    $('#stat-warn').textContent = counts.warn;
    $('#stat-fail').textContent = counts.fail;
    $('#nav-total').textContent = items.length;
    $('#nav-alerts').textContent = counts.warn + counts.fail;
    document.querySelectorAll('[data-count]').forEach(node => { node.textContent = items.filter(item => item.domain === node.dataset.count).length; });
    $('#last-updated').textContent = new Intl.DateTimeFormat('zh-CN', {hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(sampledAt);
    $('#health-number').textContent = trends[period].value;
    $('#domain-grid').innerHTML = Object.entries(domains).map(([key, domain]) => {
      const group = items.filter(item => item.domain === key);
      const failed = group.filter(item => item.status === 'fail').length;
      const warnings = group.filter(item => item.status === 'warn').length;
      const unknown = group.filter(item => item.status === 'unknown').length;
      const tone = failed ? 'fail' : warnings ? 'warn' : unknown ? 'unknown' : 'ok';
      const label = failed ? `${failed} 项异常` : warnings ? `${warnings} 项预警` : unknown ? `${unknown} 项未知` : group.length ? '运行正常' : '暂无对象';
      return `<button class="domain-card" data-goto="${key}"><div class="domain-top"><span class="domain-icon ${domain.color}">${icon(key)}</span><span class="domain-name">${domain.name}</span><span class="domain-arrow">↗</span></div><div class="domain-numbers"><strong>${group.length}</strong><span>${domain.unit}</span></div><div class="domain-bottom"><span>${domain.description}</span><b>${statusDot(tone)}${label}</b></div></button>`;
    }).join('');
    const selected = items.filter(item => {
      if (domains[view] && item.domain !== view) return false;
      if (view === 'events' && !['warn','fail'].includes(item.status)) return false;
      if (filter !== 'all' && item.status !== filter) return false;
      return `${item.name} ${item.target} ${domains[item.domain].name} ${item.metric}`.toLocaleLowerCase().includes(query.toLocaleLowerCase());
    });
    $('#list-title').firstChild.textContent = view === 'events' ? '需关注对象 ' : domains[view] ? `${domains[view].name} ` : '监控对象 ';
    $('#list-count').textContent = selected.length;
    $('#monitor-body').innerHTML = selected.map(item => `<tr data-detail="${esc(item.id)}" tabindex="0" role="button" aria-label="查看 ${esc(item.name)} 详情"><td><div class="asset"><span class="asset-icon ${domains[item.domain].color}">${icon(item.domain)}</span><span><strong>${esc(item.name)}</strong><small>${esc(item.target)}</small></span></div></td><td>${statusChip(item.status)}</td><td><span class="metric-value">${esc(item.value)}</span><span class="metric-label">${esc(item.metric)}</span></td><td>${heartbeat(item.history)}</td><td class="row-arrow">↗</td></tr>`).join('');
    $('#empty').classList.toggle('hidden', selected.length !== 0);
    $('#table-summary').textContent = `显示 ${selected.length} / ${items.length} 个对象`;
    const alerts = items.filter(item => ['fail','warn'].includes(item.status));
    $('#event-list').innerHTML = alerts.length ? alerts.slice(0, 4).map(item => `<button class="event" data-detail="${esc(item.id)}" aria-label="查看 ${esc(item.name)} 事件详情"><span class="event-icon ${item.status === 'fail' ? 'red' : 'amber'}">${item.status === 'fail' ? '!' : '↗'}</span><span class="event-body"><strong>${esc(item.name)}</strong><span>${esc(item.note)}</span></span><time>${esc(item.last)}</time></button>`).join('') : '<div class="empty">暂无模拟事件</div>';
    const trend = trends[period];
    $('#health-chart').setAttribute('aria-label', `模拟 ${period} 服务健康趋势`);
    $('#health-chart').innerHTML = `<svg viewBox="0 0 280 96" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop stop-color="#6884f0" stop-opacity=".28"/><stop offset="1" stop-color="#6884f0" stop-opacity="0"/></linearGradient></defs><polygon points="${trend.points} 280,96 0,96" fill="url(#area)"/><polyline points="${trend.points}" fill="none" stroke="#637ef0" stroke-width="2.5" vector-effect="non-scaling-stroke"/></svg>`;
    $('#chart-labels').innerHTML = trend.labels.map(label => `<span>${label}</span>`).join('');
  }

  function renderCommands() {
    const term = $('#command-input').value.trim().toLocaleLowerCase();
    const matches = items.filter(item => `${item.name} ${item.target} ${domains[item.domain].name}`.toLocaleLowerCase().includes(term)).slice(0, 7);
    $('#command-results').innerHTML = matches.length ? matches.map(item => `<button class="command-result" data-command-detail="${esc(item.id)}"><span class="asset-icon ${domains[item.domain].color}">${icon(item.domain)}</span><span><strong>${esc(item.name)}</strong><small>${esc(domains[item.domain].name)} · ${esc(item.target)}</small></span>${statusChip(item.status)}<span class="command-arrow">↗</span></button>`).join('') : '<div class="empty">没有找到匹配的模拟对象</div>';
  }

  function detail(id) {
    const item = items.find(entry => entry.id === id);
    if (!item) return;
    $('#detail-content').innerHTML = `<div class="detail-inner"><div class="dialog-head"><div><p class="section-eyebrow">MONITOR DETAIL / DEMO</p><h2>${esc(item.name)}</h2><p>${esc(item.target)}</p></div><button class="close-dialog" data-close="detail-dialog" aria-label="关闭">×</button></div><div class="detail-grid"><div class="detail-cell"><small>当前状态</small>${statusChip(item.status)}</div><div class="detail-cell"><small>监控领域</small><strong>${domains[item.domain].name}</strong></div><div class="detail-cell"><small>${esc(item.metric)}</small><strong>${esc(item.value)}</strong></div><div class="detail-cell"><small>模拟采样</small><strong>${esc(item.last)}</strong></div></div><div class="form-note">${esc(item.note)}</div><p class="detail-note">此详情和指标为演示数据，不代表真实采集或已接入该类型的数据源。</p><div class="dialog-actions"><button class="button-secondary" data-close="detail-dialog">关闭</button></div></div>`;
    $('#detail-dialog').showModal();
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('button, [data-detail]');
    if (!button) return;
    if (button.dataset.signalFilter) {
      setView('all');
      const target = document.querySelector(`[data-filter="${button.dataset.signalFilter}"]`);
      target.click();
    }
    else if (button.dataset.view) setView(button.dataset.view);
    else if (button.dataset.goto) setView(button.dataset.goto);
    else if (button.dataset.detail) detail(button.dataset.detail);
    else if (button.dataset.filter) { filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach(el => { const selected = el === button; el.classList.toggle('selected', selected); el.setAttribute('aria-pressed', String(selected)); }); render(); }
    else if (button.dataset.period) { period = button.dataset.period; document.querySelectorAll('[data-period]').forEach(el => { const selected = el === button; el.classList.toggle('selected', selected); el.setAttribute('aria-pressed', String(selected)); }); render(); }
    else if (button.dataset.commandDetail) { $('#command-dialog').close(); detail(button.dataset.commandDetail); }
    else if (button.dataset.close) document.getElementById(button.dataset.close).close();
  });
  $('#monitor-body').addEventListener('keydown', event => { if ((event.key === 'Enter' || event.key === ' ') && event.target.dataset.detail) { event.preventDefault(); detail(event.target.dataset.detail); } });
  $('#search').addEventListener('input', event => { query = event.target.value.trim(); render(); });
  $('#view-all').addEventListener('click', () => setView('all'));
  $('.brand').addEventListener('click', event => { event.preventDefault(); setView('overview'); });
  $('#add-monitor').addEventListener('click', () => $('#add-dialog').showModal());
  $('#command-open').addEventListener('click', () => { $('#command-input').value = ''; renderCommands(); $('#command-dialog').showModal(); $('#command-input').focus(); });
  $('#command-input').addEventListener('input', renderCommands);
  $('#add-form').addEventListener('submit', event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const name = String(data.get('name')).trim();
    const target = String(data.get('target')).trim();
    const domain = String(data.get('domain'));
    if (!name || !target || !domains[domain]) { toast('请填写名称和示例地址'); return; }
    items.unshift({id:`custom-${Date.now()}`,name,target,domain,status:'unknown',metric:'等待数据',value:'--',history:'uuuuuuuuuuuuuuuuuuuu',note:'演示对象未连接真实数据源',last:'未采样'});
    event.currentTarget.reset(); $('#add-dialog').close(); setView('all'); toast('已添加模拟对象，不会连接目标');
  });
  $('#refresh').addEventListener('click', () => { sampledAt = new Date(); render(); toast('模拟数据已刷新，未发起监测请求'); });
  $('#reset-demo').addEventListener('click', () => { items = structuredClone(initial); sampledAt = new Date(); setView('overview'); toast('已恢复初始演示数据'); });
  document.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) { event.preventDefault(); $('#command-open').click(); } else if (event.key === '/' && !event.target.matches('input,textarea,select') && !document.querySelector('dialog[open]')) { event.preventDefault(); $('#search').focus(); } });
  document.querySelector('.nav-item.active').setAttribute('aria-current', 'page');
  render();
})();
