const API = '/api';
let cars = [];
let floorData = null;

const TITLES = {
  dashboard: '数据概览',
  orders: '订单管理',
  recipients: '收件人管理',
  floor: '楼层教室',
  cars: '小车状态',
  create: '新建订单',
};

const ORDER_STATUSES = [
  { value: 'queued', label: '排队中', desc: '订单已创建，等待小车处理' },
  { value: 'navigating', label: '前往教室', desc: '小车正在前往目标教室' },
  { value: 'scanning', label: '人脸核验中', desc: '小车在教室内扫描人脸核验身份' },
  { value: 'delivered', label: '已送达', desc: '货物已成功交付' },
  { value: 'failed', label: '配送失败', desc: '配送未能完成' },
];

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
  if (name === 'recipients') loadRecipients();
  if (name === 'floor') loadFloorPlan();
  if (name === 'cars') loadCars();
  if (name === 'create') { loadClassroomOptions(); loadRecipientOptions(); }
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
    orders.filter(o => ['navigating', 'scanning'].includes(o.status))
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
  const active = orders.filter(o => ['navigating', 'scanning'].includes(o.status));
  const queued = orders.filter(o => o.status === 'queued');

  document.getElementById('statsGrid').innerHTML = `
    <div class="stat-card primary"><div class="label">总订单</div><div class="value">${stats.total}</div></div>
    <div class="stat-card warning"><div class="label">排队中</div><div class="value">${stats.queued ?? 0}</div></div>
    <div class="stat-card info"><div class="label">配送中</div><div class="value">${(stats.navigating||0)+(stats.scanning||0)}</div></div>
    <div class="stat-card success"><div class="label">已送达</div><div class="value">${stats.delivered}</div></div>
    <div class="stat-card"><div class="label">配送范围</div><div class="value floor-stat">${stats.floor_name}</div></div>
    <div class="stat-card info"><div class="label">快递小车</div><div class="value floor-stat">${stats.car_name || '未配置'}</div></div>
  `;

  const container = document.getElementById('activeOrders');
  const cards = [
    ...queued.map(o => ({ ...o, _section: 'queued' })),
    ...active.map(o => ({ ...o, _section: 'active' })),
  ];
  if (!cards.length) {
    container.innerHTML = '<div class="empty-state">当前没有排队或配送中的订单</div>';
    return;
  }
  container.innerHTML = cards.map(o => `
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
        <button type="button" class="btn btn-sm btn-ghost" onclick="toggleStatusPanel()">查看订单状态</button>
        <button class="btn btn-sm btn-ghost" onclick="pushOrderTcp(${o.id})">TCP 下发小车</button>
      </div>
      <div id="statusPanel" class="status-panel hidden">
        <h4>订单状态说明</h4>
        <ul class="status-list">
          ${ORDER_STATUSES.map(s => `
            <li class="status-list-item ${o.status === s.value ? 'current' : ''}">
              ${badge(s.value, s.label)}
              <span class="status-desc">${s.desc}</span>
              ${o.status === s.value ? '<span class="status-current-tag">当前</span>' : ''}
            </li>
          `).join('')}
        </ul>
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

function toggleStatusPanel() {
  const panel = document.getElementById('statusPanel');
  if (panel) panel.classList.toggle('hidden');
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

async function loadCars() {
  const car = await api('/car');
  cars = [car];
  const statusLabel = {
    idle: '空闲', queued: '排队中', navigating: '前往教室', scanning: '人脸核验中',
  }[car.status] || car.status;

  document.getElementById('carGrid').innerHTML = `
    <div class="car-card car-card-single">
      <h4>🤖 ${car.name}</h4>
      <div class="detail-row"><span class="label">运行范围</span><span>逸夫楼 5 层</span></div>
      <div class="detail-row"><span class="label">当前状态</span><span>${badge(car.status, statusLabel)}</span></div>
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

// ── Recipient select in create order ────────────────────────────
let recipientsList = [];

async function loadRecipientOptions() {
  recipientsList = await api('/recipients');
  const select = document.getElementById('recipientSelect');
  select.innerHTML = '<option value="">— 选择已录入收件人 —</option>' +
    recipientsList.map(r =>
      `<option value="${r.name}" data-phone="${r.phone || ''}" data-face="${r.face_image_url || ''}">${r.name}</option>`
    ).join('');
}

function onRecipientSelect() {
  const select = document.getElementById('recipientSelect');
  const opt = select.selectedOptions[0];
  const phone = opt?.dataset.phone || '';
  const faceUrl = opt?.dataset.face || '';
  document.getElementById('recipientPhoneInput').value = phone;
  const preview = document.getElementById('orderFacePreview');
  if (faceUrl) {
    preview.innerHTML = `<img src="${faceUrl}" alt="收件人人脸" style="max-width:200px;border-radius:8px" />`;
  } else {
    preview.innerHTML = '<span>该收件人暂无照片</span>';
  }
}

// ── Create order (no file upload) ────────────────────────────────
document.getElementById('createForm').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  try {
    const res = await api('/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const no = res.order_no ? `（${res.order_no}）` : '';
    if (res.tcp_push?.ok) {
      toast(`订单${no}已创建，已通过 TCP 下发至 ${res.tcp_push.host}:${res.tcp_push.port}`);
    } else if (res.tcp_push?.error) {
      toast(`订单${no}已创建，但 TCP 下发失败：${res.tcp_push.error}`, 'error');
    } else {
      toast(`订单${no}创建成功`);
    }
    e.target.reset();
    document.getElementById('orderFacePreview').innerHTML = '<span>选择收件人后显示人脸照片</span>';
    switchView('orders');
  } catch (err) { toast(err.message, 'error'); }
});

// ── Recipient management ─────────────────────────────────────────
function showRecipientForm(id = null) {
  document.getElementById('recipientFormPanel').classList.remove('hidden');
  document.getElementById('recipientFormTitle').textContent = id ? '编辑收件人' : '录入收件人';
  document.getElementById('recipientId').value = id || '';
  if (!id) {
    document.getElementById('recipientForm').reset();
    document.getElementById('recipientFacePreview').innerHTML = '<span>点击上传人脸照片</span>';
  } else {
    const r = recipientsList.find(x => x.id === parseInt(id));
    if (r) {
      document.getElementById('recipientNameInput').value = r.name || '';
      document.getElementById('recipientPhoneFormInput').value = r.phone || '';
      const preview = document.getElementById('recipientFacePreview');
      if (r.face_image_url) {
        preview.innerHTML = `<img src="${r.face_image_url}" alt="${r.name}" />`;
      } else {
        preview.innerHTML = '<span>点击上传人脸照片</span>';
      }
    }
  }
}

function hideRecipientForm() {
  document.getElementById('recipientFormPanel').classList.add('hidden');
}

document.getElementById('recipientFaceUploadArea').addEventListener('click', () => {
  document.getElementById('recipientFaceInput').click();
});
document.getElementById('recipientFaceInput').addEventListener('change', () => {
  const file = document.getElementById('recipientFaceInput').files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('recipientFacePreview').innerHTML =
      `<img src="${e.target.result}" alt="预览" />`;
  };
  reader.readAsDataURL(file);
});

document.getElementById('recipientForm').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const recipientId = fd.get('recipient_id');
  fd.delete('recipient_id');

  const isEdit = !!recipientId;
  const url = isEdit ? `/recipients/${recipientId}` : '/recipients';
  const method = isEdit ? 'PATCH' : 'POST';

  try {
    await api(url, { method, body: fd });
    toast(isEdit ? '收件人已更新' : '收件人已录入');
    hideRecipientForm();
    await loadRecipients();
    await loadRecipientOptions(); // refresh the create-order dropdown too
  } catch (err) { toast(err.message, 'error'); }
});

async function loadRecipients() {
  recipientsList = await api('/recipients');
  const tbody = document.getElementById('recipientsTable');
  if (!recipientsList.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">暂无录入收件人，请先录入</td></tr>';
    return;
  }
  tbody.innerHTML = recipientsList.map(r => `
    <tr>
      <td><strong>${r.name}</strong></td>
      <td>${r.phone || '—'}</td>
      <td>${r.face_image_url
        ? `<img class="face-thumb" src="${r.face_image_url}" alt="${r.name}" />`
        : '<span class="face-missing">👤</span>'}</td>
      <td><small>${r.created_at ? r.created_at.slice(0, 10) : '—'}</small></td>
      <td>
        <button class="btn btn-sm btn-ghost" onclick="showRecipientForm(${r.id})">编辑</button>
        <button class="btn btn-sm btn-danger" onclick="deleteRecipient(${r.id}, '${r.name}')">删除</button>
      </td>
    </tr>
  `).join('');
}

async function deleteRecipient(id, name) {
  if (!confirm(`确定删除收件人「${name}」？删除后，该收件人人脸信息将不再可用。`)) return;
  try {
    await api(`/recipients/${id}`, { method: 'DELETE' });
    toast('收件人已删除');
    await loadRecipients();
    await loadRecipientOptions();
  } catch (err) { toast(err.message, 'error'); }
}

loadDashboard();
