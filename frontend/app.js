const { createApp, ref, reactive, onMounted, nextTick, computed, watch } = Vue;

const app = createApp({
  setup() {
    const API = '/api';
    const token = ref(localStorage.getItem('token') || '');
    const isLogin = ref(!!token.value);
    const loginLoading = ref(false);
    const showMonitor = ref(false);
    const currentPage = ref('home');
    const currentTime = ref('');
    const monitorTime = ref(new Date().toLocaleDateString('zh-CN'));

    const loginForm = reactive({ username: '', password: '' });
    const currentUser = reactive({ id: 0, username: '', role: '', role_name: '', company_name: '' });

    const today = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });

    const statusMap = { produced: '已生产', shipped: '已发货', installed: '已装车', in_use: '使用中', scrapped: '已报废', second_life: '梯次利用', recycled: '已回收拆解' };
    const statusOrder = ['produced', 'shipped', 'installed', 'in_use', 'scrapped', 'second_life', 'recycled'];

    const menus = [
      { title: '概览', items: [
        { key: 'home', label: '工作台', icon: '🏠' },
      ]},
      { title: '生产装车', items: [
        { key: 'battery', label: '电池生命周期', icon: '🔋' },
      ]},
      { title: '运行监控', items: [
        { key: 'bms', label: 'BMS实时监控', icon: '📡' },
        { key: 'charging', label: '智能充电管理', icon: '⚡' },
      ]},
      { title: '回收利用', items: [
        { key: 'assessment', label: '残值与梯次利用', icon: '♻️' },
        { key: 'recycling', label: '回收拆解管理', icon: '🧪' },
      ]},
      { title: '碳核算与监管', items: [
        { key: 'carbon', label: '碳足迹核算', icon: '🌱' },
        { key: 'users', label: '用户权限管理', icon: '👥', roles: ['regulator'] },
      ]},
    ];

    // ==================== Axios 封装 ====================
    const axiosInst = axios.create({ baseURL: API, timeout: 30000 });
    axiosInst.interceptors.request.use(c => {
      if (token.value) c.headers.Authorization = 'Bearer ' + token.value;
      return c;
    });
    axiosInst.interceptors.response.use(r => r.data, err => {
      if (err.response?.status === 401) {
        localStorage.removeItem('token');
        isLogin.value = false;
        ElementPlus.ElMessage.error('登录已过期，请重新登录');
      }
      return Promise.reject(err.response?.data || { message: '请求失败' });
    });

    // ==================== 登录 ====================
    function handleLogin() {
      if (!loginForm.username || !loginForm.password) {
        ElementPlus.ElMessage.warning('请输入用户名和密码');
        return;
      }
      loginLoading.value = true;
      axios.post(API + '/auth/login', loginForm).then(r => {
        const d = r.data.data;
        token.value = d.token;
        localStorage.setItem('token', d.token);
        Object.assign(currentUser, d.user);
        isLogin.value = true;
        loginLoading.value = false;
        ElementPlus.ElMessage.success('登录成功');
        afterLoginInit();
      }).catch(e => {
        loginLoading.value = false;
        ElementPlus.ElMessage.error(e.message || '登录失败');
      });
    }

    function handleCommand(cmd) {
      if (cmd === 'logout') {
        localStorage.removeItem('token');
        isLogin.value = false;
        token.value = '';
        ElementPlus.ElMessage.success('已退出登录');
      } else if (cmd === 'monitor') {
        openMonitor();
      }
    }

    function navigateTo(key) {
      currentPage.value = key;
      nextTick(() => {
        if (key === 'home') loadHome();
        if (key === 'battery') loadBatteriesPage();
        if (key === 'bms') loadBMSPage();
        if (key === 'charging') loadChargingPage();
        if (key === 'assessment') loadAssessmentPage();
        if (key === 'recycling') loadRecyclingPage();
        if (key === 'carbon') loadCarbonPage();
        if (key === 'users') loadUsers();
      });
    }

    // ==================== 图表实例管理 ====================
    const charts = {};
    function getChart(refName, key, dark) {
      const el = typeof refName === 'string' ? document.querySelector('[ref="' + refName + '"]') : refName;
      if (!el) return null;
      if (!charts[key]) charts[key] = echarts.init(el, dark ? 'dark' : null);
      else charts[key].resize();
      return charts[key];
    }
    function resizeCharts() { Object.values(charts).forEach(c => c && c.resize()); }
    window.addEventListener('resize', resizeCharts);

    watch(showMonitor, v => {
      if (v) { nextTick(() => { loadMonitorData(); loadMonitorCharts(); }); }
      else {
        ['mStatusChart','mFactoryChart','mSohChart','mAutomakerChart','mTrendChart','mCarbonChart','mCarbonBarChart'].forEach(k => {
          if (charts[k]) { charts[k].dispose(); delete charts[k]; }
        });
      }
    });

    // ==================== SOH 颜色 ====================
    function sohColor(v) {
      if (v >= 90) return '#15803d';
      if (v >= 80) return '#65a30d';
      if (v >= 70) return '#ca8a04';
      if (v >= 60) return '#ea580c';
      return '#dc2626';
    }

    // ==================== 首页 ====================
    const homeStats = reactive({});
    async function loadHome() {
      try {
        const r = await axiosInst.get('/dashboard/overview');
        Object.assign(homeStats, r.data.data);
        nextTick(() => renderHomeCharts());
      } catch(e) {}
    }
    async function renderHomeCharts() {
      const [r1, r2, r3, r4] = await Promise.all([
        axiosInst.get('/dashboard/status-chart'),
        axiosInst.get('/dashboard/automaker-chart'),
        axiosInst.get('/dashboard/trend?days=7'),
        axiosInst.get('/dashboard/soh-distribution'),
      ]);

      const c1 = echarts.init(document.querySelector('[ref="statusChart"]'));
      charts.statusChart = c1;
      c1.setOption({
        tooltip: { trigger: 'item' },
        legend: { bottom: 0, type: 'scroll' },
        series: [{ type: 'pie', radius: ['40%', '70%'], avoidLabelOverlap: false, itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, formatter: '{b}\n{c} ({d}%)' },
          data: r1.data.data.labels.map((l,i) => ({ name: l, value: r1.data.data.values[i], itemStyle: { color: ['#94a3b8','#3b82f6','#22c55e','#f97316','#a855f7','#06b6d4'][i] } })) }]
      });

      const c2 = echarts.init(document.querySelector('[ref="automakerChart"]'));
      charts.automakerChart = c2;
      const autoData = r2.data.data;
      c2.setOption({
        tooltip: {},
        grid: { left: 80, right: 20, top: 20, bottom: 30 },
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: autoData.map(d => d.automaker), axisLabel: { width: 100, overflow: 'truncate' } },
        series: [{ type: 'bar', data: autoData.map(d => d.count), barWidth: 22, itemStyle: { color: new echarts.graphic.LinearGradient(0,0,1,0,[{offset:0,color:'#60a5fa'},{offset:1,color:'#22d3ee'}]), borderRadius: [0,6,6,0] }, label: { show: true, position: 'right' } }]
      });

      const c3 = echarts.init(document.querySelector('[ref="trendChart"]'));
      charts.trendChart = c3;
      const td = r3.data.data;
      c3.setOption({
        tooltip: { trigger: 'axis' },
        legend: { top: 0, data: ['新增电池', '已回收', '故障预警'] },
        grid: { left: 40, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: td.labels },
        yAxis: { type: 'value' },
        series: [
          { name: '新增电池', type: 'line', smooth: true, data: td.new_batteries, areaStyle: { opacity: 0.15 }, itemStyle: { color: '#3b82f6' } },
          { name: '已回收', type: 'line', smooth: true, data: td.recycled, areaStyle: { opacity: 0.15 }, itemStyle: { color: '#22c55e' } },
          { name: '故障预警', type: 'bar', data: td.warnings, itemStyle: { color: '#f97316' }, barWidth: 14 },
        ]
      });

      const c4 = echarts.init(document.querySelector('[ref="sohChart"]'));
      charts.sohChart = c4;
      const sd = r4.data.data;
      c4.setOption({
        tooltip: { trigger: 'item' },
        xAxis: { type: 'category', data: sd.map(s => s.label.split(' ')[0]), axisLabel: { interval: 0, rotate: 20 } },
        yAxis: { type: 'value' },
        grid: { left: 40, right: 20, top: 20, bottom: 60 },
        series: [{ type: 'bar', data: sd.map((s,i) => ({ value: s.value, itemStyle: { color: ['#15803d','#65a30d','#ca8a04','#ea580c','#dc2626'][i] } })), barWidth: 36, label: { show: true, position: 'top' } }]
      });
    }

    // ==================== 电池管理 ====================
    const batteries = reactive({ list: [], total: 0 });
    const batteryPage = ref(1);
    const batterySize = ref(20);
    const bFilter = reactive({ keyword: '', status: '', automaker: '', factory: '' });
    const companyList = reactive({ automakers: [], factories: [] });
    const showCreateBattery = ref(false);
    const createForm = reactive({ serial_code: '', cell_model: '', capacity: 75, production_batch: '', production_date: new Date().toISOString().slice(0,10) });
    const showInstallDialog = ref(false);
    const installForm = reactive({ id: 0, serial_code: '', vehicle_plate: '' });
    const showBatteryDetail = ref(false);
    const batteryDetail = reactive({});

    async function loadBatteriesPage() {
      await loadCompanies();
      loadBatteries();
    }
    async function loadCompanies() {
      try {
        const r = await axiosInst.get('/battery/automakers');
        Object.assign(companyList, r.data.data);
      } catch(e) {}
    }
    async function loadBatteries() {
      try {
        const params = { page: batteryPage.value, page_size: batterySize.value, ...bFilter };
        const r = await axiosInst.get('/battery/list', { params });
        Object.assign(batteries, r.data.data);
      } catch(e) {}
    }
    async function submitCreateBattery() {
      for (const k of ['serial_code','cell_model','capacity','production_batch','production_date']) {
        if (!createForm[k]) { ElementPlus.ElMessage.warning('请完整填写表单'); return; }
      }
      try {
        await axiosInst.post('/battery/create', createForm);
        ElementPlus.ElMessage.success('电池创建成功，唯一编码已写入');
        showCreateBattery.value = false;
        Object.assign(createForm, { serial_code:'', cell_model:'', capacity:75, production_batch:'', production_date:new Date().toISOString().slice(0,10) });
        loadBatteries();
      } catch(e) { ElementPlus.ElMessage.error(e.message || '创建失败'); }
    }
    function installBattery(row) { installForm.id = row.id; installForm.serial_code = row.serial_code; installForm.vehicle_plate = ''; showInstallDialog.value = true; }
    async function submitInstall() {
      if (!installForm.vehicle_plate) { ElementPlus.ElMessage.warning('请填写车牌号'); return; }
      try {
        await axiosInst.post(`/battery/${installForm.id}/install`, { vehicle_plate: installForm.vehicle_plate });
        ElementPlus.ElMessage.success('装车成功');
        showInstallDialog.value = false;
        loadBatteries();
      } catch(e) { ElementPlus.ElMessage.error(e.message); }
    }
    async function startUse(row) {
      try {
        await axiosInst.post(`/battery/${row.id}/start-use`);
        ElementPlus.ElMessage.success('已启用');
        loadBatteries();
      } catch(e) { ElementPlus.ElMessage.error(e.message); }
    }
    async function assessBattery(row) {
      try {
        ElementPlus.ElMessageBox.confirm(`确认评估电池 ${row.serial_code} 残值？SOH：${row.current_soh}%`, '残值评估确认', { type: 'warning' });
        await axiosInst.post(`/battery/${row.id}/assess`);
        ElementPlus.ElMessage.success('残值评估完成');
        loadBatteries();
      } catch(e) { if (e !== 'cancel') ElementPlus.ElMessage.error(e.message); }
    }
    async function secondLife(row) {
      try {
        await axiosInst.post(`/battery/${row.id}/second-life`);
        ElementPlus.ElMessage.success('已转为梯次利用');
        loadBatteries();
      } catch(e) { ElementPlus.ElMessage.error(e.message); }
    }
    async function openBatteryDialog(row) {
      try {
        const r = await axiosInst.get(`/battery/${row.id}`);
        Object.assign(batteryDetail, r.data.data);
        showBatteryDetail.value = true;
      } catch(e) {}
    }
    function batteryStatusClass(cur, status) {
      const ci = statusOrder.indexOf(cur);
      const si = statusOrder.indexOf(status);
      if (si < ci) return 'done';
      if (si === ci) return 'current';
      return '';
    }

    // ==================== BMS ====================
    const bmsBatteryOptions = ref([]);
    const selectedBatteryId = ref(null);
    const bmsRealtime = reactive({ latest: null, history: [] });
    const warnings = reactive({ list: [], total: 0 });

    async function loadBMSPage() {
      try {
        const r = await axiosInst.get('/battery/list', { params: { page: 1, page_size: 200 } });
        bmsBatteryOptions.value = r.data.data.list.filter(b => ['installed','in_use'].includes(b.status));
        if (bmsBatteryOptions.value.length && !selectedBatteryId.value) {
          selectedBatteryId.value = bmsBatteryOptions.value[0].id;
          loadBMSRealtime();
        }
      } catch(e) {}
      loadWarnings();
    }
    async function loadBMSRealtime() {
      if (!selectedBatteryId.value) return;
      try {
        const r = await axiosInst.get(`/bms/realtime/${selectedBatteryId.value}?hours=24`);
        Object.assign(bmsRealtime, r.data.data);
        nextTick(renderBMSCharts);
      } catch(e) {}
    }
    async function simulateBMS() {
      if (!selectedBatteryId.value) { ElementPlus.ElMessage.warning('请选择电池'); return; }
      try {
        await axiosInst.post(`/bms/simulate/${selectedBatteryId.value}`);
        ElementPlus.ElMessage.success('模拟上传完成');
        loadBMSRealtime();
        loadWarnings();
      } catch(e) { ElementPlus.ElMessage.error(e.message); }
    }
    async function loadWarnings() {
      try {
        const r = await axiosInst.get('/bms/warnings', { params: { page: 1, page_size: 50 } });
        Object.assign(warnings, r.data.data);
      } catch(e) {}
    }
    function renderBMSCharts() {
      const hist = bmsRealtime.history || [];
      const times = hist.map(h => h.record_time.slice(11,16));
      if (times.length > 50) { const step = Math.ceil(times.length/50); for (let i=0;i<hist.length;i++) if (i%step) { times[i]=''; } }

      const c1 = echarts.init(document.querySelector('[ref="tempChart"]'));
      charts.tempChart = c1;
      c1.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 40, right: 20, top: 30, bottom: 40 },
        xAxis: { type: 'category', data: times, axisLabel: { rotate: 30 } },
        yAxis: { type: 'value', name: '℃' },
        series: [
          { name: '温度', type: 'line', smooth: true, data: hist.map(h => h.temperature),
            lineStyle: { color: '#ef4444', width: 3 }, areaStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(239,68,68,0.3)'},{offset:1,color:'rgba(239,68,68,0)'}]) },
            markLine: { data: [{ yAxis: 45, name: '断电阈值', lineStyle: { color: '#dc2626' } }, { yAxis: 40, name: '预警阈值', lineStyle: { color: '#f97316', type: 'dashed' } }] }
          }
        ]
      });

      const c2 = echarts.init(document.querySelector('[ref="voltChart"]'));
      charts.voltChart = c2;
      c2.setOption({
        tooltip: { trigger: 'axis' },
        legend: { top: 0, data: ['电压','SOC'] },
        grid: { left: 40, right: 50, top: 40, bottom: 40 },
        xAxis: { type: 'category', data: times, axisLabel: { rotate: 30 } },
        yAxis: [
          { type: 'value', name: 'V', position: 'left' },
          { type: 'value', name: '%', position: 'right', min: 0, max: 100 }
        ],
        series: [
          { name: '电压', type: 'line', smooth: true, data: hist.map(h => h.voltage), itemStyle: { color: '#3b82f6' } },
          { name: 'SOC', type: 'line', yAxisIndex: 1, smooth: true, data: hist.map(h => h.soc), itemStyle: { color: '#22c55e' }, areaStyle: { opacity: 0.1 } }
        ]
      });

      const latest = bmsRealtime.latest;
      let cellTemps = [], cellVolts = [];
      if (latest?.cell_temperatures) cellTemps = latest.cell_temperatures.split(',').map(Number);
      if (latest?.cell_voltages) cellVolts = latest.cell_voltages.split(',').map(Number);
      if (!cellTemps.length) cellTemps = Array.from({length:96}, () => 28 + Math.random()*8);
      if (!cellVolts.length) cellVolts = Array.from({length:96}, () => 3.5 + Math.random()*0.5);

      const c3 = echarts.init(document.querySelector('[ref="cellTempChart"]'));
      charts.cellTempChart = c3;
      const rows = 8, cols = 12;
      const tempData = [];
      for (let r=0;r<rows;r++) for (let c=0;c<cols;c++) { const idx = r*cols+c; tempData.push([c, rows-1-r, cellTemps[idx] || 30]); }
      c3.setOption({
        tooltip: { formatter: p => `电芯[${p.data[1]+1},${p.data[0]+1}]<br/>温度: ${p.data[2]}℃` },
        grid: { left: 20, right: 20, top: 20, bottom: 30 },
        xAxis: { type: 'category', data: Array.from({length:cols},(_,i)=>i+1), splitArea: { show: true } },
        yAxis: { type: 'category', data: Array.from({length:rows},(_,i)=>rows-i), splitArea: { show: true } },
        visualMap: { min: 22, max: 48, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#1d4ed8','#22c55e','#eab308','#f97316','#dc2626'] } },
        series: [{ type: 'heatmap', data: tempData, label: { show: false }, itemStyle: { borderColor: '#fff', borderWidth: 1 } }]
      });

      const c4 = echarts.init(document.querySelector('[ref="cellVoltChart"]'));
      charts.cellVoltChart = c4;
      c4.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 40, right: 20, top: 20, bottom: 40 },
        xAxis: { type: 'category', data: Array.from({length:cellVolts.length},(_,i)=>i+1), name: '电芯编号' },
        yAxis: { type: 'value', name: 'V' },
        dataZoom: [{ type: 'inside', start: 0, end: 100 }, { type: 'slider', height: 20, bottom: 5 }],
        series: [{ type: 'scatter', data: cellVolts, symbolSize: 8, itemStyle: { color: p => p.value[1] > 4.15 ? '#dc2626' : (p.value[1] < 3.3 ? '#3b82f6' : '#22c55e') },
          markLine: { data: [{ yAxis: 4.2, name: '上限', lineStyle: { color: '#dc2626' } }, { yAxis: 3.2, name: '下限', lineStyle: { color: '#3b82f6' } }] }
        }]
      });
    }

    // ==================== 充电管理 ====================
    const chargingStats = reactive({});
    const chargingBatteryOptions = ref([]);
    const chargingSerialCode = ref('');
    const currentCharging = ref(null);
    const chargingRecords = reactive({ list: [], total: 0 });
    const cFilter = reactive({ serial_code: '' });

    async function loadChargingPage() {
      try {
        const [s1, s2] = await Promise.all([
          axiosInst.get('/charging/stats'),
          axiosInst.get('/battery/list', { params: { page: 1, page_size: 200 } })
        ]);
        Object.assign(chargingStats, s1.data.data);
        chargingBatteryOptions.value = s2.data.data.list.filter(b => b.status === 'in_use');
      } catch(e) {}
      loadCharging();
      nextTick(renderChargingCharts);
    }
    async function loadCharging() {
      try {
        const params = { page: 1, page_size: 50, ...cFilter };
        const r = await axiosInst.get('/charging/list', { params });
        Object.assign(chargingRecords, r.data.data);
      } catch(e) {}
    }
    function renderChargingCharts() {
      const sd = chargingStats.strategy_distribution || [];
      if (!sd.length) return;
      const c = echarts.init(document.querySelector('[ref="strategyChart"]'));
      charts.strategyChart = c;
      c.setOption({
        tooltip: { trigger: 'item' },
        legend: { bottom: 0, type: 'scroll' },
        series: [{ type: 'pie', radius: ['35%', '65%'], roseType: 'radius',
          data: sd.map((s,i) => ({ name: s.strategy.split(' ')[0], value: s.count, itemStyle: { color: ['#3b82f6','#22c55e','#a855f7','#f97316','#06b6d4','#e11d48'][i%6] } })),
          label: { formatter: '{b}: {c}' }
        }]
      });
    }
    async function startCharging() {
      if (!chargingSerialCode.value) { ElementPlus.ElMessage.warning('请选择电池'); return; }
      try {
        const r = await axiosInst.post('/charging/start', { serial_code: chargingSerialCode.value });
        Object.assign(currentCharging, r.data.data);
        ElementPlus.ElMessage.success(r.data.message);
      } catch(e) { ElementPlus.ElMessage.error(e.message); }
    }
    async function stopCharging() {
      if (!currentCharging.value) return;
      try {
        const r = await axiosInst.post(`/charging/stop/${currentCharging.value.id}`);
        ElementPlus.ElMessage.success(r.data.message);
        if (r.data.data.is_alerted) ElementPlus.ElNotification({ title: '异常发热预警', message: r.data.data.alert_message, type: 'warning' });
        currentCharging.value = null;
        loadChargingPage();
      } catch(e) { ElementPlus.ElMessage.error(e.message); }
    }

    // ==================== 残值评估 ====================
    const assessments = reactive({ list: [], total: 0 });
    const assessCount = computed(() => (recyclingStats.scenario_distribution || []).reduce((s,x) => s + x.count, 0));
    function countScenario(keyword) {
      return (recyclingStats.scenario_distribution || []).filter(x => (x.scenario || '').includes(keyword)).reduce((s,x) => s + x.count, 0);
    }

    async function loadAssessmentPage() {
      try {
        await Promise.all([loadRecyclingStats(), loadAssessments()]);
        nextTick(renderAssessmentCharts);
      } catch(e) {}
    }
    async function loadAssessments() {
      try {
        const r = await axiosInst.get('/recycling/assessments', { params: { page: 1, page_size: 100 } });
        Object.assign(assessments, r.data.data);
      } catch(e) {}
    }
    function renderAssessmentCharts() {
      const sd = recyclingStats.scenario_distribution || [];
      if (!sd.length) return;
      const c = echarts.init(document.querySelector('[ref="scenarioChart"]'));
      charts.scenarioChart = c;
      c.setOption({
        tooltip: { trigger: 'axis' },
        legend: { top: 0 },
        grid: { left: 40, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: sd.map(s => s.scenario.split(' ')[0].slice(0,8)) },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: sd.map((s,i) => ({ value: s.count, itemStyle: { color: ['#3b82f6','#22c55e','#f97316','#a855f7'][i%4] }, borderRadius: [8,8,0,0] })), barWidth: 60, label: { show: true, position: 'top' } }]
      });
    }

    // ==================== 回收管理 ====================
    const recyclingStats = reactive({ metals: {}, scenario_distribution: [] });
    const scanCode = ref('');
    const recyclingList = reactive({ list: [], total: 0 });
    const rFilter = reactive({ status: '' });

    async function loadRecyclingPage() {
      await Promise.all([loadRecyclingStats(), loadRecycling()]);
      nextTick(renderRecyclingCharts);
    }
    async function loadRecyclingStats() {
      try { const r = await axiosInst.get('/recycling/stats'); Object.assign(recyclingStats, r.data.data); } catch(e) {}
    }
    async function loadRecycling() {
      try {
        const params = { page: 1, page_size: 50, ...rFilter };
        const r = await axiosInst.get('/recycling/list', { params });
        Object.assign(recyclingList, r.data.data);
      } catch(e) {}
    }
    function renderRecyclingCharts() {
      const m = recyclingStats.metals || {};
      const data = [
        { name: '锂 Li', value: m.lithium || 0, color: '#3b82f6' },
        { name: '钴 Co', value: m.cobalt || 0, color: '#a855f7' },
        { name: '镍 Ni', value: m.nickel || 0, color: '#22c55e' },
        { name: '锰 Mn', value: m.manganese || 0, color: '#f97316' },
        { name: '其他', value: m.other || 0, color: '#64748b' },
      ];
      const c = echarts.init(document.querySelector('[ref="metalsChart"]'));
      charts.metalsChart = c;
      c.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} kg ({d}%)' },
        legend: { top: 0, type: 'scroll' },
        series: [{ type: 'pie', radius: ['40%', '70%'], avoidLabelOverlap: true,
          itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, formatter: '{b}\n{c}kg' },
          data: data.map(d => ({ ...d, itemStyle: { color: d.color } }))
        }]
      });
    }
    async function scanInbound() {
      if (!scanCode.value) { ElementPlus.ElMessage.warning('请输入电池编码'); return; }
      try {
        const r = await axiosInst.post('/recycling/scan-inbound', { serial_code: scanCode.value });
        ElementPlus.ElMessage.success(r.data.message);
        scanCode.value = '';
        loadRecyclingPage();
      } catch(e) { ElementPlus.ElMessage.error(e.message); }
    }
    async function completeDisassembly(row) {
      try {
        const r = await axiosInst.post(`/recycling/complete/${row.id}`);
        ElementPlus.ElMessage.success(r.data.message);
        loadRecyclingPage();
      } catch(e) { ElementPlus.ElMessage.error(e.message); }
    }

    // ==================== 碳足迹 ====================
    const carbonStats = reactive({ stage_average: {} });
    const carbonList = reactive({ list: [], total: 0 });
    const cfFilter = reactive({ keyword: '' });
    const showCarbonReportDialog = ref(false);
    const carbonReport = ref('');
    let reportContext = null;

    async function loadCarbonPage() {
      try {
        const r = await axiosInst.get('/carbon/stats');
        Object.assign(carbonStats, r.data.data);
      } catch(e) {}
      loadCarbon();
      nextTick(renderCarbonCharts);
    }
    async function loadCarbon() {
      try {
        const params = { page: 1, page_size: 50, ...cfFilter };
        const r = await axiosInst.get('/carbon/list', { params });
        Object.assign(carbonList, r.data.data);
      } catch(e) {}
    }
    function renderCarbonCharts() {
      const s = carbonStats.stage_average || {};
      const data = [
        { name: '生产', value: s.production || 0, color: '#ef4444' },
        { name: '运输', value: s.transport || 0, color: '#f97316' },
        { name: '使用', value: s.usage || 0, color: '#eab308' },
        { name: '回收', value: s.recycling || 0, color: '#22c55e' },
      ];
      const c = echarts.init(document.querySelector('[ref="carbonStageChart"]'));
      charts.carbonStageChart = c;
      c.setOption({
        tooltip: { trigger: 'item' },
        legend: { top: 0 },
        series: [{ type: 'pie', radius: '65%', center: ['50%','55%'],
          label: { formatter: '{b}\n{c}kg\n{d}%' },
          data: data.map(d => ({ ...d, itemStyle: { color: d.color } }))
        }]
      });
    }
    function showCarbonReport(row) {
      carbonReport.value = row.compliance_report || '暂无报告，请点击「重算」生成';
      reportContext = row;
      showCarbonReportDialog.value = true;
    }
    async function calculateCarbon(row) {
      try {
        const r = await axiosInst.post(`/carbon/calculate/${row.battery_id}`);
        ElementPlus.ElMessage.success(r.data.message);
        showCarbonReport(r.data.data);
        loadCarbon();
      } catch(e) { ElementPlus.ElMessage.error(e.message); }
    }
    function downloadReport() {
      if (!reportContext) return;
      const blob = new Blob([carbonReport.value], { type: 'text/plain;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `碳足迹报告_${reportContext.serial_code}.txt`;
      a.click();
    }

    // ==================== 用户管理 ====================
    const usersList = ref([]);
    async function loadUsers() {
      try { const r = await axiosInst.get('/auth/users'); usersList.value = r.data.data.list || []; } catch(e) {}
    }

    // ==================== 监管大屏 ====================
    const monitorData = reactive({ recycled_metals: {} });
    const monitorWarnings = ref([]);
    const monitorFilter = ref('');
    const monitorAutomakers = ref([]);
    let monitorTimer = null;

    function openMonitor() {
      showMonitor.value = true;
      if (!monitorTimer) monitorTimer = setInterval(() => {
        const now = new Date();
        currentTime.value = now.toLocaleString('zh-CN', { hour12: false });
        if (Math.random() > 0.6) loadMonitorData();
      }, 5000);
      currentTime.value = new Date().toLocaleString('zh-CN', { hour12: false });
    }

    async function loadMonitorData() {
      try {
        const params = monitorFilter.value ? { automaker: monitorFilter.value } : {};
        if (!monitorAutomakers.value.length) {
          try { const ar = await axiosInst.get('/dashboard/automakers'); monitorAutomakers.value = ar.data.data; } catch(e) {}
        }
        const [o, w] = await Promise.all([
          axiosInst.get('/dashboard/overview', { params }),
          axiosInst.get('/dashboard/warnings-realtime', { params })
        ]);
        Object.assign(monitorData, o.data.data);
        monitorWarnings.value = w.data.data;
        nextTick(loadMonitorCharts);
      } catch(e) {}
    }

    function loadMonitorCharts() {
      const dark = { backgroundColor: 'transparent', textStyle: { color: '#cbd5e1' } };
      Promise.all([
        axiosInst.get('/dashboard/status-chart', monitorFilter.value ? { params: { automaker: monitorFilter.value } } : {}),
        axiosInst.get('/dashboard/factory-chart'),
        axiosInst.get('/dashboard/soh-distribution'),
        axiosInst.get('/dashboard/automaker-chart'),
        axiosInst.get('/dashboard/trend?days=7'),
        axiosInst.get('/carbon/stats'),
      ]).then(([r1, r2, r3, r4, r5, r6]) => {

        const el1 = document.querySelector('[ref="mStatusChart"]');
        if (el1) {
          if (charts.mStatusChart) charts.mStatusChart.dispose();
          charts.mStatusChart = echarts.init(el1, null, dark);
          charts.mStatusChart.setOption({
            tooltip: { trigger: 'item' }, legend: { bottom: 0, textStyle: { color: '#94a3b8', fontSize: 10 } },
            series: [{ type: 'pie', radius: ['35%','65%'],
              label: { color: '#cbd5e1', fontSize: 10, formatter: '{b}\n{c}' },
              data: r1.data.data.labels.map((l,i) => ({ name: l, value: r1.data.data.values[i], itemStyle: { color: ['#64748b','#60a5fa','#4ade80','#fbbf24','#a78bfa','#22d3ee'][i] } })) }]
          });
        }

        const el2 = document.querySelector('[ref="mFactoryChart"]');
        if (el2) {
          if (charts.mFactoryChart) charts.mFactoryChart.dispose();
          charts.mFactoryChart = echarts.init(el2, null, dark);
          const fd = r2.data.data;
          charts.mFactoryChart.setOption({
            tooltip: {}, grid: { left: 70, right: 10, top: 10, bottom: 20 },
            xAxis: { type: 'value', axisLabel: { color: '#64748b', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.1)' } } },
            yAxis: { type: 'category', data: fd.map(d=>d.factory), axisLabel: { color: '#94a3b8', fontSize: 10, width: 65, overflow: 'truncate' } },
            series: [{ type: 'bar', data: fd.map(d => ({ value: d.count, itemStyle: { color: new echarts.graphic.LinearGradient(0,0,1,0,[{offset:0,color:'rgba(34,211,238,.3)'},{offset:1,color:'#22d3ee'}]) } })), barWidth: 10, label: { show: true, position: 'right', color: '#22d3ee', fontSize: 10 } }]
          });
        }

        const el3 = document.querySelector('[ref="mSohChart"]');
        if (el3) {
          if (charts.mSohChart) charts.mSohChart.dispose();
          charts.mSohChart = echarts.init(el3, null, dark);
          charts.mSohChart.setOption({
            tooltip: {}, grid: { left: 40, right: 10, top: 10, bottom: 20 },
            xAxis: { type: 'category', data: r3.data.data.map(s => s.label.split(' ')[0].replace(/[（(]/g,'\n(')), axisLabel: { color: '#64748b', fontSize: 10, interval: 0, lineHeight: 14 } },
            yAxis: { type: 'value', axisLabel: { color: '#64748b', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.1)' } } },
            series: [{ type: 'bar', barWidth: 20, data: r3.data.data.map((s,i) => ({ value: s.value, itemStyle: { color: ['#4ade80','#a3e635','#facc15','#fb923c','#f87171'][i], borderRadius: [4,4,0,0] } })), label: { show: true, position: 'top', color: '#e2e8f0', fontSize: 11 } }]
          });
        }

        const el4 = document.querySelector('[ref="mAutomakerChart"]');
        if (el4) {
          if (charts.mAutomakerChart) charts.mAutomakerChart.dispose();
          charts.mAutomakerChart = echarts.init(el4, null, dark);
          const ad = r4.data.data;
          charts.mAutomakerChart.setOption({
            tooltip: {}, grid: { left: 75, right: 20, top: 10, bottom: 20 },
            xAxis: { type: 'value', axisLabel: { color: '#64748b', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.1)' } } },
            yAxis: { type: 'category', data: ad.map(d=>d.automaker).reverse(), axisLabel: { color: '#94a3b8', fontSize: 11 } },
            series: [{ type: 'bar', data: ad.map(d => d.count).reverse().map((v,i) => ({ value: v, itemStyle: { color: new echarts.graphic.LinearGradient(0,0,1,0,[{offset:0,color:'rgba(96,165,250,.2)'},{offset:1,color:`hsl(${200+i*20},70%,60%)`}]), borderRadius: [0,6,6,0] } })), barWidth: 14, label: { show: true, position: 'right', color: '#cbd5e1', fontSize: 11 } }]
          });
        }

        const el5 = document.querySelector('[ref="mTrendChart"]');
        if (el5) {
          if (charts.mTrendChart) charts.mTrendChart.dispose();
          charts.mTrendChart = echarts.init(el5, null, dark);
          const td = r5.data.data;
          charts.mTrendChart.setOption({
            tooltip: { trigger: 'axis' }, legend: { top: 0, textStyle: { color: '#94a3b8', fontSize: 11 }, data: ['新增','回收','预警'] },
            grid: { left: 40, right: 10, top: 30, bottom: 20 },
            xAxis: { type: 'category', data: td.labels, axisLabel: { color: '#64748b', fontSize: 10 } },
            yAxis: { type: 'value', axisLabel: { color: '#64748b', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.1)' } } },
            series: [
              { name: '新增', type: 'line', smooth: true, data: td.new_batteries, itemStyle: { color: '#60a5fa' }, areaStyle: { opacity: 0.15 } },
              { name: '回收', type: 'line', smooth: true, data: td.recycled, itemStyle: { color: '#4ade80' }, areaStyle: { opacity: 0.15 } },
              { name: '预警', type: 'bar', data: td.warnings, itemStyle: { color: '#f87171' }, barWidth: 8 }
            ]
          });
        }

        const el6 = document.querySelector('[ref="mCarbonChart"]');
        if (el6) {
          if (charts.mCarbonChart) charts.mCarbonChart.dispose();
          charts.mCarbonChart = echarts.init(el6, null, dark);
          const s = r6.data.data.stage_average || {};
          charts.mCarbonChart.setOption({
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            legend: { top: 0, textStyle: { color: '#94a3b8' } },
            grid: { left: 50, right: 20, top: 30, bottom: 30 },
            xAxis: { type: 'category', data: ['生产阶段','运输阶段','使用阶段','回收阶段'], axisLabel: { color: '#94a3b8' } },
            yAxis: { type: 'value', name: 'kgCO₂e', axisLabel: { color: '#64748b' }, nameTextStyle: { color: '#64748b' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.1)' } } },
            series: [{ type: 'bar', stack: 'total', name: '碳排放量', data: [s.production||0, s.transport||0, s.usage||0, s.recycling||0].map((v,i) => ({ value: v, itemStyle: { color: ['#ef4444','#f97316','#eab308','#22c55e'][i], borderRadius: i===3?[8,8,0,0]:[0,0,0,0] } })), barWidth: 50, label: { show: true, position: 'top', color: '#cbd5e1', formatter: '{c} kg' } }]
          });
        }

        const el7 = document.querySelector('[ref="mCarbonBarChart"]');
        if (el7) {
          if (charts.mCarbonBarChart) charts.mCarbonBarChart.dispose();
          charts.mCarbonBarChart = echarts.init(el7, null, dark);
          charts.mCarbonBarChart.setOption({
            tooltip: {}, legend: { top: 0, textStyle: { color: '#94a3b8' } },
            grid: { left: 40, right: 10, top: 30, bottom: 20 },
            xAxis: { type: 'category', data: ['碳排放量', '碳减排量', '净排放'], axisLabel: { color: '#94a3b8' } },
            yAxis: { type: 'value', axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.1)' } } },
            series: [{ type: 'bar', barWidth: 30,
              data: [
                { value: Math.round((monitorData.carbon?.total_emission||0)/1), itemStyle: { color: '#f87171', borderRadius: [8,8,0,0] } },
                { value: Math.round((monitorData.carbon?.total_saved||0)/1), itemStyle: { color: '#4ade80', borderRadius: [8,8,0,0] } },
                { value: Math.round((monitorData.carbon?.net_emission||0)/1), itemStyle: { color: '#fbbf24', borderRadius: [8,8,0,0] } }
              ],
              label: { show: true, position: 'top', color: '#cbd5e1' }
            }]
          });
        }
      });
    }

    // ==================== 初始化 ====================
    function afterLoginInit() {
      loadHome();
    }

    onMounted(() => {
      if (isLogin.value) {
        axiosInst.get('/auth/me').then(r => {
          Object.assign(currentUser, r.data.data);
          afterLoginInit();
        }).catch(() => {
          localStorage.removeItem('token');
          isLogin.value = false;
        });
      }
      setInterval(() => { currentTime.value = new Date().toLocaleString('zh-CN', { hour12: false }); }, 1000);
      currentTime.value = new Date().toLocaleString('zh-CN', { hour12: false });
    });

    return {
      token, isLogin, loginLoading, loginForm, currentUser, today, menus, currentPage,
      showMonitor, currentTime, monitorTime, statusMap,
      handleLogin, handleCommand, navigateTo, sohColor,
      // 首页
      homeStats, loadHome,
      // 电池
      batteries, batteryPage, batterySize, bFilter, companyList, loadBatteries, loadBatteriesPage,
      showCreateBattery, createForm, submitCreateBattery,
      showInstallDialog, installForm, installBattery, submitInstall,
      startUse, assessBattery, secondLife,
      showBatteryDetail, batteryDetail, openBatteryDialog, batteryStatusClass,
      // BMS
      bmsBatteryOptions, selectedBatteryId, bmsRealtime, warnings,
      loadBMSPage, loadBMSRealtime, simulateBMS, loadWarnings,
      // 充电
      chargingStats, chargingBatteryOptions, chargingSerialCode, currentCharging, chargingRecords, cFilter,
      loadChargingPage, loadCharging, startCharging, stopCharging,
      // 残值
      assessments, assessCount, countScenario, loadAssessmentPage,
      // 回收
      recyclingStats, scanCode, recyclingList, rFilter,
      loadRecyclingPage, scanInbound, completeDisassembly,
      // 碳足迹
      carbonStats, carbonList, cfFilter, loadCarbonPage, loadCarbon,
      showCarbonReportDialog, carbonReport, showCarbonReport, calculateCarbon, downloadReport,
      // 用户
      usersList, loadUsers,
      // 大屏
      monitorData, monitorWarnings, monitorFilter, monitorAutomakers,
    };
  }
});

for (const [k, v] of Object.entries(ElementPlusIconsVue)) app.component(k, v);
app.use(ElementPlus, { locale: ElementPlusLocaleZhCn });
app.mount('#app');
