const API = '/api';
let cars = [];
let floorData = null;

const TITLES = {
  dashboard: '数据概览',
  orders: '订单管理',
  floor: '楼层教室',
  cars: '小车状态',
  create: '新建订单',
};

document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

function switchView(name) {
  document.querySelectorAll('.nav-item').forEach(b =>
    b.classList.toggle('active', b.dataset.view === name)
  );
  document.querySelectorAll('.view').forEach(v =>
    v.classList.toggle('active', v.id === `view-${name}`)
  );
  document.getElementById('pageTitle').textContent = TITLES[name];
  if (name === 'dashboard') loadDashboard();
  if (name === 'orders') loadOrders();
  if (name === 'floor') loadFloorPlan();
  if (name === 'cars') loadCars();
  if (name === 'create') loadClassroomOptions();
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || '请求失败');
  return data;
}

function toast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast ${type}`;
  setTimeout(() => el.classList.add('hidden'), 3000);
}

function badge(status, label) {
  return `<span class="badge badge-${status}">${label}</span>`;
}

function updateClock() {
  document.getElementById('liveTime').textContent = new Date().toLocaleString('zh-CN');
}
setInterval(updateClock, 1000);
updateClock();

async function ensureFloorData() {
  if (!floorData) floorData = await api('/floor');
  document.getElementById('sidebarFloor').textContent = floorData.floor_name;
  return floorData;
}

async function loadClassroomOptions() {
  const floor = await ensureFloorData();
  const select = document.getElementById('classroomSelect');
  document.getElementById('createFloorHint').textContent =
    `配送范围：${floor.floor_name}，选择教室号码即可定位`;
  select.innerHTML = '<option value="">— 选择教室 —</option>' +
    floor.classrooms.map(c =>
      `<option value="${c.classroom_no}">${c.classroom_no}教室</option>`
    ).join('');
}

async function loadFloorPlan(highlightClassroom = null) {
  const floor = await ensureFloorData();
  document.getElementById('floorTitle').textContent = `${floor.floor_name} · 教室分布`;

  const orders = await api('/orders');
  const activeRooms = new Set(
    orders.filter(o => ['assigned', 'navigating', 'scanning'].includes(o.status))
      .map(o => o.classroom_no)
  );

  const maxRow = Math.max(...floor.classrooms.map(c => c.grid_row), 0);
  const maxCol = Math.max(...floor.classrooms.map(c => c.grid_col), 0);

  let html = '<div class="floor-grid" style="grid-template-columns:repeat(' + (maxCol + 1) + ',1fr)">';
  for (let r = 0; r <= maxRow; r++) {
    for (let c = 0; c <= maxCol; c++) {
      const room = floor.classrooms.find(x => x.grid_row === r && x.grid_col === c);
      if (!room) {
        html += '<div class="floor-cell empty"></div>';
        continue;
      }
      const isActive = activeRooms.has(room.classroom_no);
      const isHighlight = highlightClassroom === room.classroom_no;
      html += `<div class="floor-cell ${isActive ? 'active' : ''} ${isHighlight ? 'highlight' : ''}">
        <span class="room-no">${room.classroom_no}</span>
        <span class="room-label">${room.label || ''}</span>
        ${isActive ? '<span class="room-status">配送中</span>' : ''}
      </div>`;
    }
  }
  html += '</div>';
  document.getElementById('floorPlan').innerHTML = html;
}

async function loadDashboard() {
  const stats = await api('/stats');
  await ensureFloorData();
  const orders = await api('/orders');
  const active = orders.filter(o => ['assigned', 'navigating', 'scanning'].includes(o.status));

  document.getElementById('statsGrid').innerHTML = `
    <div class="stat-card primary"><div class="label">总订单</div><div class="value">${stats.total}</div></div>
    <div class="stat-card warning"><div class="label">待分配</div><div class="value">${stats.pending}</div></div>
    <div class="stat-card info"><div class="label">配送中</div><div class="value">${(stats.assigned||0)+(stats.navigating||0)+(stats.scanning||0)}</div></div>
    <div class="stat-card success"><div class="label">已送达</div><div class="value">${stats.delivered}</div></div>
    <div class="stat-card"><div class="label">配送范围</div><div class="value floor-stat">${stats.floor_name}</div></div>
    <div class="stat-card info"><div class="label">快递小车</div><div class="value floor-stat">${stats.car_name || '未配置'}</div></div>
  `;

  const container = document.getElementById('activeOrders');
  if (!active.length) {
    container.innerHTML = '<div class="empty-state">当前没有配送中的订单</div>';
    return;
  }
  container.innerHTML = active.map(o => `
    <div class="order-card" onclick="showDetail(${o.id})">
      <div class="order-no">${o.order_no} ${badge(o.status, o.status_label)}</div>
      <div class="meta">
        收件人：${o.recipient_name} (${o.recipient_phone})<br/>
        教室：<strong>${o.classroom_no}</strong> · ${o.classroom_label}<br/>
        小车：逸夫楼快递小车
      </div>
    </div>
  `).join('');
}

document.getElementById('statusFilter').addEventListener('change', loadOrders);

async function loadOrders() {
  const status = document.getElementById('statusFilter').value;
  const qs = status ? `?status=${status}` : '';
  const orders = await api('/orders' + qs);
  const tbody = document.getElementById('ordersTable');

  if (!orders.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">暂无订单</td></tr>';
    return;
  }

  tbody.innerHTML = orders.map(o => `
    <tr>
      <td><strong>${o.order_no}</strong></td>
      <td>${o.recipient_name}<br/><small style="color:var(--text-muted)">${o.recipient_phone}</small></td>
      <td><strong class="classroom-tag">${o.classroom_no}</strong><br/><small>${o.classroom_label}</small></td>
      <td>${o.face_image_url
        ? `<img class="face-thumb" src="${o.face_image_url}" alt="人脸" />`
        : '<div class="face-missing">👤</div>'}</td>
      <td>${badge(o.status, o.status_label)}</td>
      <td>
        <button class="btn btn-sm btn-ghost" onclick="showDetail(${o.id})">详情</button>
        <button class="btn btn-sm btn-danger" onclick="deleteOrder(${o.id})">删除</button>
      </td>
    </tr>
  `).join('');
}

function getActiveView() {
  const el = document.querySelector('.view.active');
  return el ? el.id.replace('view-', '') : 'dashboard';
}

async function refreshOrderViews() {
  await loadDashboard();
  const view = getActiveView();
  if (view === 'orders') await loadOrders();
  if (view === 'floor') await loadFloorPlan();
}

async function deleteOrder(id) {
  if (!confirm('确定删除该订单？')) return;
  try {
    await api(`/orders/${id}`, { method: 'DELETE' });
    toast('订单已删除');
    await refreshOrderViews();
  } catch (e) { toast(e.message, 'error'); }
}

async function showDetail(id) {
  const o = await api(`/orders/${id}`);
  if (!cars.length) cars = await api('/cars');
  await ensureFloorData();

  document.getElementById('detailBody').innerHTML = `
    <h3 style="margin-bottom:12px">${o.order_no} ${badge(o.status, o.status_label)}</h3>
    <p class="hint" style="margin-bottom:20px">${o.delivery_flow}</p>
    <div class="detail-grid">
      <div class="detail-section">
        <h4>收件人信息</h4>
        <div class="detail-row"><span class="label">姓名</span><span>${o.recipient_name}</span></div>
        <div class="detail-row"><span class="label">电话</span><span>${o.recipient_phone}</span></div>
        <div class="detail-row"><span class="label">包裹</span><span>${o.package_desc || '—'}</span></div>
        <div class="detail-row"><span class="label">备注</span><span>${o.remark || '—'}</span></div>
      </div>
      <div class="detail-section">
        <h4>送达教室</h4>
        <div class="detail-row"><span class="label">楼层</span><span>${o.floor_name}</span></div>
        <div class="detail-row"><span class="label">教室号码</span><span class="classroom-tag-lg">${o.classroom_no}</span></div>
        <div class="detail-row"><span class="label">教室名称</span><span>${o.classroom_label}</span></div>
      </div>
      <div class="detail-section">
        <h4>收件人人脸核验照片</h4>
        ${o.face_image_url
          ? `<img class="detail-face" src="${o.face_image_url}" alt="收件人人脸" />`
          : '<div class="detail-face-empty">暂未上传人脸照片</div>'}
        <p class="hint" style="margin-top:8px">小车进入 ${o.classroom_no} 教室后，摄像头扫描并比对此照片</p>
      </div>
      <div class="detail-section">
        <h4>教室位置</h4>
        <div id="detailFloorMini" class="floor-plan-mini"></div>
      </div>
      <div class="detail-actions">
        <select id="detailStatus">
          <option value="pending" ${o.status==='pending'?'selected':''}>待分配</option>
          <option value="assigned" ${o.status==='assigned'?'selected':''}>已分配</option>
          <option value="navigating" ${o.status==='navigating'?'selected':''}>前往教室</option>
          <option value="scanning" ${o.status==='scanning'?'selected':''}>人脸核验中</option>
          <option value="delivered" ${o.status==='delivered'?'selected':''}>已送达</option>
          <option value="failed" ${o.status==='failed'?'selected':''}>配送失败</option>
        </select>
        <button class="btn btn-primary btn-sm" onclick="updateOrder(${o.id})">保存更改</button>
        <button class="btn btn-sm btn-ghost" onclick="pushOrderTcp(${o.id})">TCP 下发小车</button>
      </div>
    </div>
  `;

  document.getElementById('detailModal').classList.remove('hidden');
  renderMiniFloorPlan(o.classroom_no);
}

function renderMiniFloorPlan(highlightClassroom) {
  if (!floorData) return;
  const maxCol = Math.max(...floorData.classrooms.map(c => c.grid_col), 0);
  let html = `<div class="floor-grid mini" style="grid-template-columns:repeat(${maxCol + 1},1fr)">`;
  const maxRow = Math.max(...floorData.classrooms.map(c => c.grid_row), 0);
  for (let r = 0; r <= maxRow; r++) {
    for (let c = 0; c <= maxCol; c++) {
      const room = floorData.classrooms.find(x => x.grid_row === r && x.grid_col === c);
      if (!room) { html += '<div class="floor-cell empty mini"></div>'; continue; }
      const hl = room.classroom_no === highlightClassroom;
      html += `<div class="floor-cell mini ${hl ? 'highlight' : ''}">${room.classroom_no}</div>`;
    }
  }
  html += '</div>';
  const el = document.getElementById('detailFloorMini');
  if (el) el.innerHTML = html;
}

function closeDetail() {
  document.getElementById('detailModal').classList.add('hidden');
}

async function pushOrderTcp(id) {
  try {
    const res = await api(`/orders/${id}/push-tcp`, { method: 'POST' });
    if (res.tcp_push?.ok) {
      toast(`已通过 TCP 下发至 ${res.tcp_push.host}:${res.tcp_push.port}`);
    } else {
      toast(res.tcp_push?.error || 'TCP 下发失败', 'error');
    }
  } catch (e) { toast(e.message, 'error'); }
}

async function updateOrder(id) {
  const fd = new FormData();
  fd.append('status', document.getElementById('detailStatus').value);
  try {
    await api(`/orders/${id}`, { method: 'PATCH', body: fd });
    toast('订单已更新');
    closeDetail();
    await refreshOrderViews();
  } catch (e) { toast(e.message, 'error'); }
}

async function loadCars() {
  const car = await api('/car');
  cars = [car];
  const statusLabel = {
    idle: '空闲', assigned: '已分配', navigating: '前往教室', scanning: '人脸核验中',
  }[car.status] || car.status;

  document.getElementById('carGrid').innerHTML = `
    <div class="car-card car-card-single">
      <h4>🤖 ${car.name}</h4>
      <div class="detail-row"><span class="label">运行范围</span><span>逸夫楼 5 层</span></div>
      <div class="detail-row"><span class="label">当前状态</span><span>${badge(car.status === 'idle' ? 'pending' : car.status, statusLabel)}</span></div>
      <div class="detail-row">
        <span class="label">TCP 地址</span>
        <span>${car.ip_address || '未配置'}:${car.tcp_port || 6000}</span>
      </div>
      <div class="detail-row">
        <span class="label">TCP IP</span>
        <span>
          <input id="carIpInput" type="text" value="${car.ip_address || ''}" placeholder="192.168.1.11"
            style="background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:6px 10px;border-radius:6px;width:140px" />
        </span>
      </div>
      <div class="detail-row">
        <span class="label">TCP 端口</span>
        <span>
          <input id="carPortInput" type="number" value="${car.tcp_port || 6000}" min="1" max="65535"
            style="background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:6px 10px;border-radius:6px;width:100px" />
          <button class="btn btn-sm btn-primary" style="margin-left:8px" onclick="saveCarTcp()">保存</button>
        </span>
      </div>
      <p class="hint" style="margin-top:12px">新建订单后自动通过 TCP 向小车下发订单详情（协议 type=20）</p>
    </div>`;
}

async function saveCarTcp() {
  const ip_address = document.getElementById('carIpInput').value.trim();
  const tcp_port = document.getElementById('carPortInput').value;
  try {
    await api('/car', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ip_address, tcp_port }),
    });
    toast('小车 TCP 配置已更新');
  } catch (e) { toast(e.message, 'error'); }
}

const faceInput = document.getElementById('faceInput');
const facePreview = document.getElementById('facePreview');
document.getElementById('faceUploadArea').addEventListener('click', () => faceInput.click());
faceInput.addEventListener('change', () => {
  const file = faceInput.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => { facePreview.innerHTML = `<img src="${e.target.result}" alt="预览" />`; };
  reader.readAsDataURL(file);
});

document.getElementById('createForm').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    const res = await api('/orders', { method: 'POST', body: fd });
    if (res.tcp_push?.ok) {
      toast(`订单已创建，已通过 TCP 下发至 ${res.tcp_push.host}:${res.tcp_push.port}`);
    } else if (res.tcp_push?.error) {
      toast(`订单已创建，但 TCP 下发失败：${res.tcp_push.error}`, 'error');
    } else {
      toast('订单创建成功');
    }
    e.target.reset();
    facePreview.innerHTML = '<span>点击上传人脸照片</span>';
    switchView('orders');
  } catch (err) { toast(err.message, 'error'); }
});

loadDashboard();
