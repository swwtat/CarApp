const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DATA_DIR = path.join(__dirname, '..', 'data');
const DB_PATH = path.join(DATA_DIR, 'delivery.db');
const UPLOADS_DIR = path.join(__dirname, '..', 'uploads', 'faces');

const SITE_FLOOR = '逸夫楼 5 层';
const SINGLE_CAR_NAME = '逸夫楼快递小车';
const SINGLE_CAR_IP = '192.168.1.11';

const YIFU_5F_CLASSROOMS = [
  ['501', '501 教室', 0, 0], ['502', '502 教室', 0, 1], ['503', '503 教室', 0, 2], ['504', '504 教室', 0, 3],
  ['505', '505 教室', 1, 0], ['506', '506 教室', 1, 1], ['507', '507 教室', 1, 2], ['508', '508 教室', 1, 3],
  ['509', '509 教室', 2, 0], ['510', '510 教室', 2, 1], ['511', '511 教室', 2, 2], ['512', '512 教室', 2, 3],
];

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR, { recursive: true });

const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS cars (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    ip_address  TEXT,
    status      TEXT NOT NULL DEFAULT 'idle',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS floor_config (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    floor_name  TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS classrooms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    classroom_no  TEXT NOT NULL UNIQUE,
    label         TEXT,
    grid_row      INTEGER NOT NULL DEFAULT 0,
    grid_col      INTEGER NOT NULL DEFAULT 0
  );

  CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no        TEXT NOT NULL UNIQUE,
    recipient_name  TEXT NOT NULL,
    recipient_phone TEXT NOT NULL,
    classroom_no    TEXT NOT NULL,
    face_image      TEXT,
    package_desc    TEXT,
    remark          TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    car_id          INTEGER REFERENCES cars(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
  );
`);

function migrateSchema() {
  const cols = db.prepare('PRAGMA table_info(orders)').all().map(c => c.name);
  const carCols = db.prepare('PRAGMA table_info(cars)').all().map(c => c.name);

  if (!carCols.includes('tcp_port')) {
    db.exec('ALTER TABLE cars ADD COLUMN tcp_port INTEGER NOT NULL DEFAULT 6000');
  }

  if (!cols.includes('classroom_no')) {
    db.exec('ALTER TABLE orders ADD COLUMN classroom_no TEXT');
    if (cols.includes('room')) {
      db.exec("UPDATE orders SET classroom_no = room WHERE classroom_no IS NULL");
    }
  }

  db.exec("UPDATE orders SET status = 'navigating' WHERE status = 'delivering'");

  const legacy = ['building', 'floor', 'room', 'address_detail', 'latitude', 'longitude'];
  for (const col of legacy) {
    if (cols.includes(col)) {
      try { db.exec(`ALTER TABLE orders DROP COLUMN ${col}`); } catch { /* sqlite < 3.35 */ }
    }
  }
}

function seedClassrooms() {
  const insert = db.prepare(
    'INSERT INTO classrooms (classroom_no, label, grid_row, grid_col) VALUES (?, ?, ?, ?)'
  );
  for (const r of YIFU_5F_CLASSROOMS) insert.run(...r);
}

function applySiteConfig() {
  if (!db.prepare('SELECT id FROM floor_config WHERE id = 1').get()) {
    db.prepare('INSERT INTO floor_config (id, floor_name) VALUES (1, ?)').run(SITE_FLOOR);
  } else {
    db.prepare("UPDATE floor_config SET floor_name = ?, updated_at = datetime('now') WHERE id = 1").run(SITE_FLOOR);
  }

  const invalidRooms = db.prepare("SELECT COUNT(*) AS c FROM classrooms WHERE classroom_no NOT LIKE '5%'").get().c;
  if (db.prepare('SELECT COUNT(*) AS c FROM classrooms').get().c === 0 || invalidRooms > 0) {
    db.prepare('DELETE FROM classrooms').run();
    seedClassrooms();
    db.prepare(`
      UPDATE orders SET classroom_no = '501'
      WHERE classroom_no NOT IN (SELECT classroom_no FROM classrooms)
    `).run();
  }

  const car = db.prepare('SELECT id FROM cars ORDER BY id LIMIT 1').get();
  if (!car) {
    db.prepare('INSERT INTO cars (name, ip_address, tcp_port, status) VALUES (?, ?, ?, ?)')
      .run(SINGLE_CAR_NAME, SINGLE_CAR_IP, 6000, 'idle');
  } else {
    db.prepare('UPDATE orders SET car_id = ? WHERE car_id IS NOT NULL AND car_id != ?').run(car.id, car.id);
    db.prepare('DELETE FROM cars WHERE id != ?').run(car.id);
    db.prepare('UPDATE cars SET name = ?, ip_address = COALESCE(ip_address, ?) WHERE id = ?').run(
      SINGLE_CAR_NAME, SINGLE_CAR_IP, car.id
    );
  }
}

function seedIfEmpty() {
  const orderCount = db.prepare('SELECT COUNT(*) AS c FROM orders').get().c;
  if (orderCount > 0) return;

  const carId = db.prepare('SELECT id FROM cars ORDER BY id LIMIT 1').get().id;
  const insertOrder = db.prepare(`
    INSERT INTO orders (
      order_no, recipient_name, recipient_phone, classroom_no,
      face_image, package_desc, remark, status, car_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  const samples = [
    ['KD20260712001', '张明', '13800138001', '501', null, '文件袋 × 1', '进入教室后扫描人脸交付', 'navigating', carId],
    ['KD20260712002', '李芳', '13900139002', '505', null, '实验器材 × 1', '轻拿轻放', 'pending', null],
    ['KD20260712003', '王强', '13700137003', '509', null, '教材 × 2', '需本人签收', 'assigned', carId],
  ];
  for (const row of samples) insertOrder.run(...row);
}

migrateSchema();
applySiteConfig();
seedIfEmpty();

function getSingleCar() {
  return db.prepare('SELECT * FROM cars ORDER BY id LIMIT 1').get();
}

module.exports = { db, UPLOADS_DIR, DB_PATH, getSingleCar, SITE_FLOOR, SINGLE_CAR_NAME };
