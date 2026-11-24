(() => {
  'use strict';

  const state = { page: 1, pageSize: 20, charts: {}, toastTimer: null, loading: false };
  const palette = ['#3971e8', '#22a991', '#ecaa49', '#e56470', '#8068d9', '#48a8c5', '#91a7c7', '#bb7c45'];
  const severityColors = { high: '#e56470', medium: '#e7a33d', low: '#7990b0' };
  const $ = (id) => document.getElementById(id);
  const numberFormat = new Intl.NumberFormat('zh-CN');

  function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
  }

  function showToast(message, isError = false) {
    const toast = $('toast');
    toast.textContent = message;
    toast.style.background = isError ? '#9f3946' : '#233149';
    toast.classList.add('visible');
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => toast.classList.remove('visible'), 3200);
  }

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : {};
    if (!response.ok) throw new Error(payload.error || `请求失败 (${response.status})`);
    return payload;
  }

  function makeChart(id) {
    const element = $(id);
    if (!element || !window.echarts) return null;
    if (!state.charts[id]) state.charts[id] = echarts.init(element, null, { renderer: 'canvas' });
    return state.charts[id];
  }

  function renderMetrics(data) {
    const stats = data.stats || {};
    $('totalRequests').textContent = numberFormat.format(stats.total_requests || 0);
    $('uniqueIps').textContent = numberFormat.format(stats.unique_ips || 0);
    $('anomalyCount').textContent = numberFormat.format(stats.anomaly_count || 0);
    $('errorRate').textContent = Number(stats.error_rate || 0).toFixed(2);
    $('parsedLines').textContent = `有效解析 ${numberFormat.format(stats.parsed_lines || 0)} 行`;
    $('highRiskCount').textContent = `高风险 ${numberFormat.format(stats.high_anomalies || 0)} 项`;
    $('sourceName').textContent = data.source_name || '未知来源';
    $('sourceName').title = data.source_name || '';
    $('timeRange').textContent = stats.time_range || '暂无有效日志';
    $('timeRange').title = stats.time_range || '';

    const select = $('categoryFilter');
    const current = select.value;
    select.replaceChildren(new Option('全部类别', ''));
    (data.categories || []).forEach((category) => select.add(new Option(category, category)));
    if ((data.categories || []).includes(current)) select.value = current;
  }

  function renderTrend(data) {
    const chart = makeChart('trendChart');
    if (!chart) return;
    const labels = (data || []).map((item) => item.time.slice(5));
    const values = (data || []).map((item) => item.value);
    chart.setOption({
      animationDuration: 450,
      color: [palette[0]],
      grid: { left: 48, right: 18, top: 22, bottom: 46 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#1e2d46', borderWidth: 0, textStyle: { color: '#fff', fontSize: 11 },
        formatter: (items) => {
          const item = items[0];
          return `<span style="color:#b9c8df">${escapeHTML(item.axisValueLabel)}</span><br><strong>${numberFormat.format(item.value)} 次请求</strong>`;
        }
      },
      xAxis: {
        type: 'category', boundaryGap: false, data: labels,
        axisLine: { lineStyle: { color: '#e7ecf3' } }, axisTick: { show: false },
        axisLabel: { color: '#8794a7', fontSize: 9, interval: labels.length > 18 ? 'auto' : 0, rotate: labels.length > 30 ? 24 : 0 }
      },
      yAxis: {
        type: 'value', min: 0, minInterval: 1,
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: '#8794a7', fontSize: 9 },
        splitLine: { lineStyle: { color: '#eef1f5', type: 'dashed' } }
      },
      dataZoom: labels.length > 36 ? [{ type: 'inside' }, { type: 'slider', height: 10, bottom: 8, borderColor: 'transparent', fillerColor: 'rgba(50,104,232,.12)', handleStyle: { color: '#9eb5f0' } }] : [],
      series: [{
        name: '请求数', type: 'line', smooth: .28, showSymbol: labels.length < 30,
        symbolSize: 5, data: values,
        lineStyle: { width: 2.5, color: palette[0] },
        itemStyle: { color: palette[0], borderColor: '#fff', borderWidth: 2 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(57,113,232,.22)' }, { offset: 1, color: 'rgba(57,113,232,.015)' }
        ]) },
        markPoint: values.length ? { symbolSize: 34, itemStyle: { color: '#6688dd' }, label: { color: '#fff', fontSize: 9 }, data: [{ type: 'max', name: '峰值' }] } : undefined
      }]
    }, true);
  }

  function renderDonut(id, data, centerText, colors = palette) {
    const chart = makeChart(id);
    if (!chart) return;
    const items = data || [];
    chart.setOption({
      color: colors,
      tooltip: {
        trigger: 'item', backgroundColor: '#1e2d46', borderWidth: 0,
        textStyle: { color: '#fff', fontSize: 11 },
        formatter: (item) => `${escapeHTML(item.name)}<br><strong>${numberFormat.format(item.value)}</strong> 次 · ${Number(item.percent).toFixed(1)}%`
      },
      legend: {
        type: 'scroll', orient: 'vertical', right: 5, top: 'middle', width: '42%',
        itemWidth: 8, itemHeight: 8, itemGap: 11, icon: 'circle',
        textStyle: { color: '#78869a', fontSize: 10 },
        formatter: (name) => name.length > 12 ? `${name.slice(0, 11)}…` : name
      },
      graphic: [{
        type: 'text', left: '28%', top: 'center', style: {
          text: centerText, textAlign: 'center', fill: '#738198', fontSize: 10,
          fontFamily: 'Noto Sans SC, sans-serif', lineHeight: 17
        }
      }],
      series: [{
        type: 'pie', radius: ['48%', '72%'], center: ['30%', '52%'],
        avoidLabelOverlap: true, padAngle: 2,
        itemStyle: { borderColor: '#fff', borderWidth: 3, borderRadius: 4 },
        label: { show: false }, emphasis: { scale: true, scaleSize: 5 },
        data: items
      }]
    }, true);
  }

  function renderHorizontalBar(id, data, options = {}) {
    const chart = makeChart(id);
    if (!chart) return;
    const items = (data || []).slice().reverse();
    const names = items.map((item) => item.name);
    const values = items.map((item) => item.value);
    const color = options.color || palette[0];
    chart.setOption({
      color: [color],
      grid: { left: options.left || 100, right: 36, top: 10, bottom: 12, containLabel: false },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        backgroundColor: '#1e2d46', borderWidth: 0, textStyle: { color: '#fff', fontSize: 11 },
        formatter: (itemsAtAxis) => {
          const item = itemsAtAxis[0];
          return `${escapeHTML(item.name)}<br><strong>${numberFormat.format(item.value)}</strong> 次请求`;
        }
      },
      xAxis: {
        type: 'value', min: 0, minInterval: 1,
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: '#8996a8', fontSize: 9 },
        splitLine: { lineStyle: { color: '#eff2f6', type: 'dashed' } }
      },
      yAxis: {
        type: 'category', data: names, inverse: false,
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: {
          color: '#738198', fontSize: 9, width: options.labelWidth || 140, overflow: 'truncate',
          formatter: options.formatter || ((value) => value)
        }
      },
      series: [{
        type: 'bar', data: values, barMaxWidth: 14,
        itemStyle: { borderRadius: [0, 5, 5, 0], color },
        label: { show: true, position: 'right', color: '#718099', fontSize: 9, distance: 6 },
        emphasis: { itemStyle: { color: options.emphasis || '#2453cb' } }
      }]
    }, true);
  }

  function renderCharts(data) {
    renderTrend(data.trend);
    renderDonut('statusChart', data.status_distribution, 'HTTP\n状态码', ['#3672e9', '#21a88f', '#a6b7ce', '#efaa4a', '#e86b73', '#9276d8', '#bd85a5', '#5facc3']);
    renderHorizontalBar('ipChart', data.top_ips, { left: 100, color: '#4777e7', labelWidth: 125 });
    renderDonut('methodChart', data.method_distribution, '请求\n方法', ['#22a991', '#4382e6', '#e9a443', '#9b81df', '#e46d78', '#60a9be']);
    renderHorizontalBar('categoryChart', data.anomaly_categories, { left: 90, color: '#e4a03b', emphasis: '#c9831d', labelWidth: 100 });
    renderHorizontalBar('urlChart', data.top_urls, {
      left: 155, color: '#6887d9', labelWidth: 175,
      formatter: (value) => value.length > 30 ? `${value.slice(0, 27)}…` : value
    });
  }

  function createCell(text, className) {
    const cell = document.createElement('td');
    if (className) cell.className = className;
    cell.textContent = text ?? '';
    return cell;
  }

  function renderRows(payload) {
    const body = $('anomalyRows');
    body.replaceChildren();
    const items = payload.items || [];
    $('resultCount').textContent = `${numberFormat.format(payload.total || 0)} 条记录`;
    $('pageSummary').textContent = items.length
      ? `显示 ${numberFormat.format((payload.page - 1) * payload.page_size + 1)}–${numberFormat.format((payload.page - 1) * payload.page_size + items.length)} 条，共 ${numberFormat.format(payload.total)} 条`
      : '没有符合条件的异常记录';
    $('pageNumber').textContent = `${payload.page || 1} / ${payload.pages || 1}`;
    $('previousPage').disabled = (payload.page || 1) <= 1;
    $('nextPage').disabled = (payload.page || 1) >= (payload.pages || 1);

    if (!items.length) {
      const row = document.createElement('tr');
      const cell = createCell('当前筛选条件下没有记录。可以调整筛选条件或导入其他日志。', 'empty-cell');
      cell.colSpan = 6;
      row.append(cell);
      body.append(row);
      return;
    }

    items.forEach((item) => {
      const row = document.createElement('tr');
      const riskCell = document.createElement('td');
      const badge = document.createElement('span');
      badge.className = `risk-badge risk-${item.severity}`;
      badge.textContent = `${item.severity_label || '未知'}风险`;
      riskCell.append(badge);
      row.append(riskCell);

      row.append(createCell(item.rule_name, 'rule-cell'));
      row.append(createCell(item.ip, 'ip-cell'));

      const requestCell = document.createElement('td');
      requestCell.className = 'request-cell';
      const method = document.createElement('span');
      method.className = 'request-method';
      method.textContent = item.method;
      const path = document.createElement('span');
      path.className = 'request-path';
      path.textContent = item.path;
      path.title = `${item.timestamp} · ${item.user_agent}`;
      requestCell.append(method, path);
      row.append(requestCell);

      row.append(createCell(String(item.status), 'status-code'));
      row.append(createCell(item.reason, 'reason-cell'));
      body.append(row);
    });
  }

  async function loadAnomalies() {
    const params = new URLSearchParams({ page: String(state.page), page_size: String(state.pageSize) });
    const severity = $('severityFilter').value;
    const category = $('categoryFilter').value;
    const query = $('searchInput').value.trim();
    if (severity) params.set('severity', severity);
    if (category) params.set('category', category);
    if (query) params.set('q', query);
    const payload = await api(`/api/anomalies?${params.toString()}`);
    renderRows(payload);
  }

  async function refreshDashboard() {
    const data = await api('/api/summary');
    renderMetrics(data);
    renderCharts(data);
    await loadAnomalies();
  }

  function setBusy(busy) {
    state.loading = busy;
    $('uploadButton').disabled = busy;
    $('sampleButton').disabled = busy;
    $('uploadButton').style.opacity = busy ? '.65' : '';
    $('sampleButton').style.opacity = busy ? '.65' : '';
  }

  async function loadSample() {
    setBusy(true);
    try {
      await api('/api/sample', { method: 'POST' });
      state.page = 1;
      $('severityFilter').value = '';
      $('categoryFilter').value = '';
      $('searchInput').value = '';
      await refreshDashboard();
      showToast('演示样例已恢复');
    } catch (error) {
      showToast(error.message, true);
    } finally {
      setBusy(false);
    }
  }

  async function uploadFile(file) {
    if (!file) return;
    setBusy(true);
    $('sourceName').textContent = `正在分析 ${file.name}`;
    try {
      const form = new FormData();
      form.append('logfile', file);
      await api('/api/upload', { method: 'POST', body: form });
      state.page = 1;
      $('severityFilter').value = '';
      $('categoryFilter').value = '';
      $('searchInput').value = '';
      await refreshDashboard();
      showToast(`已完成 ${file.name} 的分析`);
    } catch (error) {
      showToast(error.message, true);
      await refreshDashboard().catch(() => {});
    } finally {
      $('logFile').value = '';
      setBusy(false);
    }
  }

  function exportCSV() {
    const params = new URLSearchParams();
    const severity = $('severityFilter').value;
    const category = $('categoryFilter').value;
    const query = $('searchInput').value.trim();
    if (severity) params.set('severity', severity);
    if (category) params.set('category', category);
    if (query) params.set('q', query);
    window.location.assign(`/api/anomalies/export.csv?${params.toString()}`);
  }

  function bindEvents() {
    $('uploadButton').addEventListener('click', () => $('logFile').click());
    $('logFile').addEventListener('change', (event) => uploadFile(event.target.files[0]));
    $('sampleButton').addEventListener('click', loadSample);
    $('exportButton').addEventListener('click', exportCSV);
    $('severityFilter').addEventListener('change', () => { state.page = 1; loadAnomalies().catch((error) => showToast(error.message, true)); });
    $('categoryFilter').addEventListener('change', () => { state.page = 1; loadAnomalies().catch((error) => showToast(error.message, true)); });
    let searchTimer;
    $('searchInput').addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.page = 1;
        loadAnomalies().catch((error) => showToast(error.message, true));
      }, 220);
    });
    $('previousPage').addEventListener('click', () => {
      if (state.page > 1) { state.page -= 1; loadAnomalies().catch((error) => showToast(error.message, true)); }
    });
    $('nextPage').addEventListener('click', () => {
      state.page += 1;
      loadAnomalies().catch((error) => showToast(error.message, true));
    });
    let resizeTimer;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => Object.values(state.charts).forEach((chart) => chart.resize()), 100);
    });
  }

  async function start() {
    bindEvents();
    if (!window.echarts) {
      showToast('图表库未能加载，请检查 static/vendor/echarts.min.js', true);
      return;
    }
    try {
      await refreshDashboard();
    } catch (error) {
      showToast(error.message || '无法加载分析结果', true);
    }
  }

  document.addEventListener('DOMContentLoaded', start);
})();
