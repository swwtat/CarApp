const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const multer = require('multer');
const { db, UPLOADS_DIR, getSingleCar, SITE_FLOOR, SINGLE_CAR_NAME } = require('./db');
const { pushOrderToCar, cancelOrderOnCar } = require('./tcpPush');

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
  pending: '待分配',
  assigned: '已分配',
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
    status_label: STATUS_LABELS[row.status] || row.status,
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

app.post('/api/orders', upload.single('face_image'), async (req, res) => {
  try {
    const { order_no, recipient_name, recipient_phone, classroom_no, package_desc, remark } = req.body;

    if (!order_no || !recipient_name || !recipient_phone || !classroom_no) {
      return res.status(400).json({ error: '请填写订单号、收件人、电话和教室号码' });
    }
    if (!req.file) {
      return res.status(400).json({ error: '请上传收件人人脸照片，小车需在教室内扫描核验' });
    }

    const classroom = getClassroom(classroom_no.trim());
    if (!classroom) {
      return res.status(400).json({ error: `教室 ${classroom_no} 不在当前楼层教室列表中` });
    }

    const result = db.prepare(`
      INSERT INTO orders (order_no, recipient_name, recipient_phone, classroom_no, face_image, package_desc, remark)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      order_no, recipient_name, recipient_phone, classroom_no.trim(),
      req.file.filename, package_desc || null, remark || null
    );

    const orderId = result.lastInsertRowid;
    const car = getSingleCar();
    if (car) {
      db.prepare("UPDATE orders SET car_id = ?, status = 'assigned', updated_at = datetime('now') WHERE id = ?")
        .run(car.id, orderId);
    }

    const order = db.prepare('SELECT * FROM orders WHERE id = ?').get(orderId);
    const mapped = mapOrder(order);
    let tcp_push = { ok: false, error: '小车未配置' };
    if (car) {
      tcp_push = await pushOrderToCar(order, car, UPLOADS_DIR);
      if (tcp_push.ok) {
        db.prepare("UPDATE cars SET status = 'assigned' WHERE id = ?").run(car.id);
      }
    }

    res.status(201).json({ ...mapped, tcp_push });
  } catch (err) {
    if (err.code === 'SQLITE_CONSTRAINT_UNIQUE') return res.status(409).json({ error: '订单号已存在' });
    res.status(500).json({ error: err.message });
  }
});

app.patch('/api/orders/:id', upload.single('face_image'), (req, res) => {
  const existing = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: '订单不存在' });

  const { status, remark } = req.body;
  const updates = [];
  const params = [];

  if (status !== undefined) { updates.push('status = ?'); params.push(status); }
  if (remark !== undefined) { updates.push('remark = ?'); params.push(remark); }

  const car = getSingleCar();
  if (car && status && ['assigned', 'navigating', 'scanning'].includes(status)) {
    updates.push('car_id = ?');
    params.push(car.id);
  }
  if (req.file) {
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
  db.prepare(`UPDATE orders SET ${updates.join(', ')} WHERE id = ?`).run(...params);

  const activeStatuses = ['assigned', 'navigating', 'scanning'];
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

  if (!['assigned', 'navigating', 'scanning', 'pending'].includes(order.status)) {
    return res.status(400).json({ error: '当前订单状态不可下发' });
  }

  if (!order.car_id) {
    db.prepare("UPDATE orders SET car_id = ?, status = 'assigned', updated_at = datetime('now') WHERE id = ?")
      .run(car.id, order.id);
  }

  const tcp_push = await pushOrderToCar(order, car, UPLOADS_DIR);
  if (tcp_push.ok) {
    db.prepare("UPDATE cars SET status = 'assigned' WHERE id = ?").run(car.id);
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

app.delete('/api/orders/:id', (req, res) => {
  const existing = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: '订单不存在' });
  if (existing.face_image) {
    const facePath = path.join(UPLOADS_DIR, existing.face_image);
    if (fs.existsSync(facePath)) fs.unlinkSync(facePath);
  }
  db.prepare('DELETE FROM orders WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

// --- Stats ---

app.get('/api/stats', (_req, res) => {
  const rows = db.prepare('SELECT status, COUNT(*) AS count FROM orders GROUP BY status').all();
  const stats = { total: 0, pending: 0, assigned: 0, navigating: 0, scanning: 0, delivered: 0, failed: 0 };
  for (const r of rows) { stats[r.status] = r.count; stats.total += r.count; }
  stats.cars = getSingleCar() ? 1 : 0;
  stats.car_name = SINGLE_CAR_NAME;
  stats.floor_name = SITE_FLOOR;
  res.json(stats);
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
    WHERE o.car_id = ? AND o.status IN ('assigned', 'navigating', 'scanning')
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
        { step: 3, action: 'face_scan', face_image_url: mapped.face_image_url, desc: '扫描教室内人脸并比对收件人' },
        { step: 4, action: 'deliver', desc: '核验通过后递交货物' },
      ],
    },
  });
}

app.use((err, _req, res, _next) => {
  res.status(400).json({ error: err.message });
});

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
