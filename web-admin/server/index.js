const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const multer = require('multer');
const { db, initDb, UPLOADS_DIR, getSingleCar, getRecipientByName, SITE_FLOOR, SINGLE_CAR_NAME } = require('./db');
const { pushOrderToCar, cancelOrderOnCar, pushFaceScanToCar } = require('./tcpPush');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use('/uploads', express.static(path.join(__dirname, '..', 'uploads')));
app.use(express.static(path.join(__dirname, '..', 'public')));

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, UPLOADS_DIR),
  filename: (_req, file, cb) => {
    const ext = path.extname(file.originalname) || '.jpg';
    cb(null, `face_${Date.now()}${ext}`);
  },
});
const upload = multer({
  storage,
  limits: { fileSize: 5 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    if (/^image\/(jpeg|png|webp|gif)$/.test(file.mimetype)) cb(null, true);
    else cb(new Error('仅支持 JPG/PNG/WebP/GIF 图片'));
  },
});

const STATUS_LABELS = {
  queued: '排队中',
  navigating: '前往教室',
  scanning: '人脸核验中',
  delivered: '已送达',
  failed: '配送失败',
};

function getFloorConfig() {
  return db.prepare('SELECT * FROM floor_config WHERE id = 1').get()
    || { floor_name: '教学楼 1 层' };
}

function getClassroom(classroomNo) {
  return db.prepare('SELECT * FROM classrooms WHERE classroom_no = ?').get(classroomNo);
}

function mapOrder(row) {
  if (!row) return null;
  const floor = getFloorConfig();
  const classroom = getClassroom(row.classroom_no);
  return {
    ...row,
    floor_name: floor.floor_name,
    classroom_label: classroom?.label || `${row.classroom_no} 教室`,
    classroom_position: classroom ? { row: classroom.grid_row, col: classroom.grid_col } : null,
    status_label: STATUS_LABELS[row.status] || ({ pending: '排队中', assigned: '排队中' }[row.status]) || row.status,
    face_image_url: row.face_image ? `/uploads/faces/${row.face_image}` : null,
    delivery_flow: `${SINGLE_CAR_NAME} 在${SITE_FLOOR}根据教室号自动驶入 → 进入教室 → 摄像头扫描人脸 → 核验通过后递交货物`,
  };
}

// --- Floor & Classrooms ---

app.get('/api/floor', (_req, res) => {
  const floor = getFloorConfig();
  const classrooms = db.prepare('SELECT * FROM classrooms ORDER BY grid_row, grid_col').all();
  res.json({ ...floor, classrooms });
});

app.get('/api/classrooms', (_req, res) => {
  res.json(db.prepare('SELECT * FROM classrooms ORDER BY classroom_no').all());
});

// --- Cars (single robot) ---

app.get('/api/cars', (_req, res) => {
  const car = getSingleCar();
  res.json(car ? [car] : []);
});

app.get('/api/car', (_req, res) => {
  const car = getSingleCar();
  if (!car) return res.status(404).json({ error: '小车未配置' });
  res.json(car);
});

app.patch('/api/car', (req, res) => {
  const car = getSingleCar();
  if (!car) return res.status(404).json({ error: '小车未配置' });
  const { ip_address, tcp_port } = req.body;
  if (ip_address !== undefined) {
    db.prepare('UPDATE cars SET ip_address = ? WHERE id = ?').run(ip_address || null, car.id);
  }
  if (tcp_port !== undefined) {
    const port = parseInt(tcp_port, 10);
    if (Number.isNaN(port) || port < 1 || port > 65535) {
      return res.status(400).json({ error: 'TCP 端口无效' });
    }
    db.prepare('UPDATE cars SET tcp_port = ? WHERE id = ?').run(port, car.id);
  }
  res.json(db.prepare('SELECT * FROM cars WHERE id = ?').get(car.id));
});

app.post('/api/cars', (_req, res) => {
  res.status(403).json({ error: '当前场景仅部署一台快递小车，无需新增' });
});

// --- Orders ---

app.get('/api/orders', (req, res) => {
  const { status } = req.query;
  let sql = `
    SELECT o.*, c.name AS car_name
    FROM orders o LEFT JOIN cars c ON o.car_id = c.id
  `;
  const params = [];
  if (status) { sql += ' WHERE o.status = ?'; params.push(status); }
  sql += ' ORDER BY o.created_at DESC';
  res.json(db.prepare(sql).all(...params).map(mapOrder));
});

app.get('/api/orders/:id', (req, res) => {
  const row = db.prepare(`
    SELECT o.*, c.name AS car_name, c.ip_address AS car_ip
    FROM orders o LEFT JOIN cars c ON o.car_id = c.id WHERE o.id = ?
  `).get(req.params.id);
  if (!row) return res.status(404).json({ error: '订单不存在' });
  res.json(mapOrder(row));
});

function generateOrderNo() {
  const now = new Date();
  const dateStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const prefix = `KD${dateStr}`;
  const last = db.prepare(
    'SELECT order_no FROM orders WHERE order_no LIKE ? ORDER BY order_no DESC LIMIT 1'
  ).get(`${prefix}%`);
  let seq = 1;
  if (last?.order_no) {
    const n = parseInt(last.order_no.slice(prefix.length), 10);
    if (!Number.isNaN(n)) seq = n + 1;
  }
  return `${prefix}${String(seq).padStart(3, '0')}`;
}

app.post('/api/orders', async (req, res) => {
  try {
    const { recipient_name, recipient_phone, classroom_no, package_desc, remark } = req.body;

    if (!recipient_name || !recipient_phone || !classroom_no) {
      return res.status(400).json({ error: '请选择收件人并填写教室号码' });
    }

    // Look up recipient's face image from the recipients database
    const recipient = getRecipientByName(recipient_name.trim());
    if (!recipient || !recipient.face_image) {
      return res.status(400).json({ error: `收件人「${recipient_name}」未录入人脸信息，请先在收件人管理中注册` });
    }

    const classroom = getClassroom(classroom_no.trim());
    if (!classroom) {
      return res.status(400).json({ error: `教室 ${classroom_no} 不在当前楼层教室列表中` });
    }

    const order_no = generateOrderNo();

    const result = db.prepare(`
      INSERT INTO orders (order_no, recipient_name, recipient_phone, classroom_no, face_image, package_desc, remark)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      order_no, recipient_name, recipient_phone, classroom_no.trim(),
      recipient.face_image, package_desc || null, remark || null
    );

    const orderId = result.lastInsertRowid;
    const car = getSingleCar();
    if (car) {
      db.prepare("UPDATE orders SET car_id = ?, status = 'queued', updated_at = datetime('now') WHERE id = ?")
        .run(car.id, orderId);
    }

    const order = db.prepare('SELECT * FROM orders WHERE id = ?').get(orderId);
    const mapped = mapOrder(order);
    let tcp_push = { ok: false, error: '小车未配置' };
    if (car) {
      tcp_push = await pushOrderToCar(order, car, UPLOADS_DIR);
      if (tcp_push.ok) {
        db.prepare("UPDATE cars SET status = 'queued' WHERE id = ?").run(car.id);
      }
    }

    res.status(201).json({ ...mapped, tcp_push });
  } catch (err) {
    if (err.code === 'SQLITE_CONSTRAINT_UNIQUE') return res.status(409).json({ error: '订单号已存在' });
    res.status(500).json({ error: err.message });
  }
});

app.patch('/api/orders/:id', (req, res) => {
  const existing = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: '订单不存在' });

  const { status, remark, recipient_name } = req.body;
  const updates = [];
  const params = [];

  if (status !== undefined) { updates.push('status = ?'); params.push(status); }
  if (remark !== undefined) { updates.push('remark = ?'); params.push(remark); }

  // If recipient name changes, refresh face_image from recipients table
  if (recipient_name !== undefined) {
    const recipient = getRecipientByName(recipient_name.trim());
    if (!recipient || !recipient.face_image) {
      return res.status(400).json({ error: `收件人「${recipient_name}」未录入人脸信息` });
    }
    updates.push('recipient_name = ?'); params.push(recipient_name.trim());
    updates.push('face_image = ?'); params.push(recipient.face_image);
  }

  const car = getSingleCar();
  if (car && status && ['queued', 'navigating', 'scanning'].includes(status)) {
    updates.push('car_id = ?');
    params.push(car.id);
  }

  if (updates.length === 0) return res.status(400).json({ error: '无更新内容' });

  updates.push("updated_at = datetime('now')");
  params.push(req.params.id);
  db.prepare(`UPDATE orders SET ${updates.join(', ')} WHERE id = ?`).run(...params);

  const activeStatuses = ['queued', 'navigating', 'scanning'];
  if (status && activeStatuses.includes(status)) {
    const updated = db.prepare('SELECT car_id FROM orders WHERE id = ?').get(req.params.id);
    if (updated.car_id) {
      db.prepare('UPDATE cars SET status = ? WHERE id = ?').run(status, updated.car_id);
    }
  }

  res.json(mapOrder(db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id)));
});

app.post('/api/orders/:id/push-tcp', async (req, res) => {
  const order = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  if (!order) return res.status(404).json({ error: '订单不存在' });

  const car = getSingleCar();
  if (!car) return res.status(400).json({ error: '小车未配置' });

  if (!['queued', 'navigating', 'scanning'].includes(order.status)) {
    return res.status(400).json({ error: '当前订单状态不可下发' });
  }

  if (!order.car_id) {
    db.prepare("UPDATE orders SET car_id = ?, status = 'queued', updated_at = datetime('now') WHERE id = ?")
      .run(car.id, order.id);
  }

  const tcp_push = await pushOrderToCar(order, car, UPLOADS_DIR);
  if (tcp_push.ok) {
    db.prepare("UPDATE cars SET status = 'queued' WHERE id = ?").run(car.id);
  }
  res.json({ order: mapOrder(db.prepare('SELECT * FROM orders WHERE id = ?').get(order.id)), tcp_push });
});

app.post('/api/orders/:id/cancel-tcp', async (req, res) => {
  const order = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  if (!order) return res.status(404).json({ error: '订单不存在' });
  const car = getSingleCar();
  const tcp_result = await cancelOrderOnCar(order.order_no, car);
  res.json({ tcp_result });
});

// ── Face Scan ────────────────────────────────────

app.post('/api/orders/:id/face-scan', async (req, res) => {
  const order = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  if (!order) return res.status(404).json({ error: '订单不存在' });
  if (!order.face_image) return res.status(400).json({ error: '该订单未关联收件人人脸' });

  const car = getSingleCar();
  if (!car) return res.status(400).json({ error: '小车未配置' });

  // 更新状态为 scanning
  db.prepare("UPDATE orders SET status = 'scanning', updated_at = datetime('now') WHERE id = ?")
    .run(order.id);

  const result = await pushFaceScanToCar(order, car, UPLOADS_DIR);
  if (result.ok) {
    db.prepare("UPDATE cars SET status = 'scanning' WHERE id = ?").run(car.id);
  }

  res.json({
    order: mapOrder(db.prepare('SELECT * FROM orders WHERE id = ?').get(order.id)),
    tcp_push: result,
  });
});

// 小车查询人脸识别状态 (轮询接口)
app.get('/api/orders/:id/face-status', (req, res) => {
  const order = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  if (!order) return res.status(404).json({ error: '订单不存在' });

  // 读取小车写入的状态文件 (通过 NFS 或 HTTP)
  const statusPath = path.join(require('os').homedir(), 'icar_face_status.json');
  let faceStatus = null;
  try {
    if (fs.existsSync(statusPath)) {
      faceStatus = JSON.parse(fs.readFileSync(statusPath, 'utf-8'));
    }
  } catch { /* ignore */ }

  res.json({
    order_status: order.status,
    face_scan: faceStatus,
  });
});

app.delete('/api/orders/:id', (req, res) => {
  const existing = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: '订单不存在' });
  // 不删除人脸文件：人脸照片属于收件人数据库，多个订单可共用
  db.prepare('DELETE FROM orders WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

// --- Delivery Status (小车实时状态上报) ---

let deliveryStatus = null;  // 内存中缓存的配送状态

app.get('/api/delivery/status', (_req, res) => {
  // 优先返回小车上报的状态, 其次读取状态文件
  if (deliveryStatus) {
    return res.json(deliveryStatus);
  }
  // 兜底: 读取小车通过 NFS 写入的状态文件
  const statusPath = path.join(require('os').homedir(), 'icar_delivery_status.json');
  try {
    if (fs.existsSync(statusPath)) {
      deliveryStatus = JSON.parse(fs.readFileSync(statusPath, 'utf-8'));
      return res.json(deliveryStatus);
    }
  } catch { /* ignore */ }
  res.json({ state: 'unknown', state_label: '等待连接', message: '小车尚未上报状态' });
});

app.post('/api/delivery/status', (req, res) => {
  deliveryStatus = req.body;
  if (deliveryStatus.timestamp == null) {
    deliveryStatus.timestamp = Date.now() / 1000;
  }
  // 同步更新订单状态
  try {
    const orderId = deliveryStatus.order_id;
    const state = deliveryStatus.state;
    const statusMap = {
      'idle': null,
      'navigating': 'navigating',
      'arrived': 'navigating',
      'entering': 'navigating',
      'scanning': 'scanning',
      'verified': 'delivered',
      'returning': 'navigating',
      'done': 'delivered',
      'failed': 'failed',
    };
    const orderStatus = statusMap[state];
    if (orderId && orderStatus) {
      db.prepare("UPDATE orders SET status = ?, updated_at = datetime('now') WHERE id = ?")
        .run(orderStatus, orderId);
      // 同步更新小车状态
      const car = getSingleCar();
      if (car) {
        db.prepare('UPDATE cars SET status = ? WHERE id = ?').run(orderStatus, car.id);
      }
    }
  } catch { /* ignore db errors from status updates */ }
  res.json({ ok: true });
});

// --- Stats ---

app.get('/api/stats', (_req, res) => {
  const rows = db.prepare('SELECT status, COUNT(*) AS count FROM orders GROUP BY status').all();
  const stats = { total: 0, queued: 0, navigating: 0, scanning: 0, delivered: 0, failed: 0 };
  for (const r of rows) {
    if (r.status === 'pending' || r.status === 'assigned') {
      stats.queued += r.count;
    } else if (stats[r.status] !== undefined) {
      stats[r.status] = r.count;
    }
    stats.total += r.count;
  }
  stats.cars = getSingleCar() ? 1 : 0;
  stats.car_name = SINGLE_CAR_NAME;
  stats.floor_name = SITE_FLOOR;
  res.json(stats);
});

// --- Recipients ---

app.get('/api/recipients', (_req, res) => {
  const rows = db.prepare('SELECT * FROM recipients ORDER BY id DESC').all();
  res.json(rows.map(r => ({
    ...r,
    face_image_url: r.face_image ? `/uploads/faces/${r.face_image}` : null,
  })));
});

app.get('/api/recipients/:id', (req, res) => {
  const r = db.prepare('SELECT * FROM recipients WHERE id = ?').get(req.params.id);
  if (!r) return res.status(404).json({ error: '收件人不存在' });
  res.json({
    ...r,
    face_image_url: r.face_image ? `/uploads/faces/${r.face_image}` : null,
  });
});

app.post('/api/recipients', upload.single('face_image'), (req, res) => {
  const { name, phone } = req.body;
  if (!name) return res.status(400).json({ error: '请填写收件人姓名' });
  if (!req.file) return res.status(400).json({ error: '请上传收件人人脸照片' });

  const existing = db.prepare('SELECT id FROM recipients WHERE name = ?').get(name.trim());
  if (existing) return res.status(409).json({ error: `收件人「${name}」已存在，请使用其他姓名或编辑现有记录` });

  const result = db.prepare(
    'INSERT INTO recipients (name, phone, face_image) VALUES (?, ?, ?)'
  ).run(name.trim(), phone || null, req.file.filename);

  const r = db.prepare('SELECT * FROM recipients WHERE id = ?').get(result.lastInsertRowid);
  res.status(201).json({
    ...r,
    face_image_url: r.face_image ? `/uploads/faces/${r.face_image}` : null,
  });
});

app.patch('/api/recipients/:id', upload.single('face_image'), (req, res) => {
  const existing = db.prepare('SELECT * FROM recipients WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: '收件人不存在' });

  const { name, phone } = req.body;
  const updates = [];
  const params = [];

  if (name !== undefined) { updates.push('name = ?'); params.push(name.trim()); }
  if (phone !== undefined) { updates.push('phone = ?'); params.push(phone); }
  if (req.file) {
    // Remove old face image file
    if (existing.face_image) {
      const oldPath = path.join(UPLOADS_DIR, existing.face_image);
      if (fs.existsSync(oldPath)) fs.unlinkSync(oldPath);
    }
    updates.push('face_image = ?');
    params.push(req.file.filename);
  }

  if (updates.length === 0) return res.status(400).json({ error: '无更新内容' });

  updates.push("updated_at = datetime('now')");
  params.push(req.params.id);
  db.prepare(`UPDATE recipients SET ${updates.join(', ')} WHERE id = ?`).run(...params);

  // Refresh face_image on all orders linked to this recipient
  if (req.file || name !== undefined) {
    const fresh = db.prepare('SELECT * FROM recipients WHERE id = ?').get(req.params.id);
    if (fresh && fresh.face_image) {
      db.prepare('UPDATE orders SET face_image = ? WHERE recipient_name = ?')
        .run(fresh.face_image, fresh.name);
    }
  }

  const r = db.prepare('SELECT * FROM recipients WHERE id = ?').get(req.params.id);
  res.json({ ...r, face_image_url: r.face_image ? `/uploads/faces/${r.face_image}` : null });
});

app.delete('/api/recipients/:id', (req, res) => {
  const existing = db.prepare('SELECT * FROM recipients WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: '收件人不存在' });

  // Remove face image file
  if (existing.face_image) {
    // Check if any orders still reference this image
    const refCount = db.prepare('SELECT COUNT(*) AS c FROM orders WHERE face_image = ?').get(existing.face_image).c;
    if (refCount === 0) {
      const imgPath = path.join(UPLOADS_DIR, existing.face_image);
      if (fs.existsSync(imgPath)) fs.unlinkSync(imgPath);
    }
  }

  db.prepare('DELETE FROM recipients WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

// --- Robot API: fetch task by classroom + face for delivery ---

app.get('/api/robot/task', (_req, res) => {
  const car = getSingleCar();
  if (!car) return res.json({ task: null });
  return fetchRobotTask(res, car.id);
});

app.get('/api/robot/:carId/task', (req, res) => {
  const car = getSingleCar();
  if (!car) return res.json({ task: null });
  return fetchRobotTask(res, car.id);
});

function fetchRobotTask(res, carId) {
  const task = db.prepare(`
    SELECT o.*, c.name AS car_name
    FROM orders o JOIN cars c ON o.car_id = c.id
    WHERE o.car_id = ? AND o.status IN ('queued', 'navigating', 'scanning')
    ORDER BY o.updated_at DESC LIMIT 1
  `).get(carId);

  if (!task) return res.json({ task: null });

  const mapped = mapOrder(task);
  res.json({
    task: {
      order_id: mapped.id,
      order_no: mapped.order_no,
      classroom_no: mapped.classroom_no,
      classroom_label: mapped.classroom_label,
      floor_name: mapped.floor_name,
      recipient_name: mapped.recipient_name,
      recipient_phone: mapped.recipient_phone,
      face_image_url: mapped.face_image_url,
      package_desc: mapped.package_desc,
      status: mapped.status,
      car_name: SINGLE_CAR_NAME,
      delivery_steps: [
        { step: 1, action: 'navigate', target: mapped.classroom_no, desc: `在${SITE_FLOOR}自动导航至 ${mapped.classroom_no} 教室` },
        { step: 2, action: 'enter', target: mapped.classroom_no, desc: '驶入教室' },
        { step: 3, action: 'face_scan', face_image_url: mapped.face_image_url, desc: '摄像头扫描人脸,调用 icar_face 识别节点比对', api: `/api/orders/${mapped.id}/face-scan` },
        { step: 4, action: 'deliver', desc: '核验通过后递交货物' },
      ],
    },
  });
}

app.use((err, _req, res, _next) => {
  res.status(400).json({ error: err.message });
});

(async () => {
await initDb();

const server = app.listen(PORT, () => {
  const car = getSingleCar();
  console.log(`送快递机器人后台管理端: http://localhost:${PORT}`);
  console.log(`配送范围: ${SITE_FLOOR} · 部署小车: ${SINGLE_CAR_NAME} × 1`);
  if (car) {
    console.log(`TCP 下发地址: ${car.ip_address || '未配置'}:${car.tcp_port || 6000}`);
  }
});

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`\n端口 ${PORT} 已被占用，后台可能已在运行。`);
    console.error(`直接访问: http://localhost:${PORT}`);
    console.error(`如需重启，先结束占用进程: netstat -ano | findstr :${PORT}`);
    process.exit(1);
  }
  throw err;
});
})();
