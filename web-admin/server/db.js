const initSqlJs = require('sql.js');
const path = require('path');
const fs = require('fs');

const DATA_DIR = path.join(__dirname, '..', 'data');
const DB_PATH = path.join(DATA_DIR, 'delivery.db');
const UPLOADS_DIR = path.join(__dirname, '..', 'uploads', 'faces');

const SITE_FLOOR = '逸夫楼 5 层';
const SINGLE_CAR_NAME = '逸夫楼快递小车';
const SINGLE_CAR_IP = '192.168.43.82';

const YIFU_5F_CLASSROOMS = [
  ['501', '501 教室', 0, 0], ['502', '502 教室', 0, 1], ['503', '503 教室', 0, 2],
];

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR, { recursive: true });

// ── sql.js adapter ──────────────────────────────────────────────
let _db; // underlying sql.js Database

function saveDb() {
  fs.writeFileSync(DB_PATH, Buffer.from(_db.export()));
}

/**
 * Statement wrapper that mirrors better-sqlite3's { get, all, run } API.
 */
class Stmt {
  constructor(_sql) { this._sql = _sql; }

  all(...params) {
    const stmt = _db.prepare(this._sql);
    if (params.length && params[0] !== undefined) stmt.bind(params);
    const rows = [];
    while (stmt.step()) {
      const cols = stmt.getColumnNames();
      const vals = stmt.get();
      const obj = {};
      cols.forEach((c, i) => { obj[c] = vals[i]; });
      rows.push(obj);
    }
    stmt.free();
    return rows;
  }

  get(...params) {
    const stmt = _db.prepare(this._sql);
    if (params.length && params[0] !== undefined) stmt.bind(params);
    let result;
    if (stmt.step()) {
      const cols = stmt.getColumnNames();
      const vals = stmt.get();
      result = {};
      cols.forEach((c, i) => { result[c] = vals[i]; });
    }
    stmt.free();
    return result;
  }

  run(...params) {
    _db.run(this._sql, params.length && params[0] !== undefined ? params : undefined);
    // Capture lastInsertRowid BEFORE saveDb (which may execute internal SQL)
    let lastInsertRowid = 0;
    const idStmt = _db.prepare('SELECT last_insert_rowid() AS id');
    if (idStmt.step()) lastInsertRowid = idStmt.get()[0];
    idStmt.free();
    saveDb();
    return { changes: _db.getRowsModified(), lastInsertRowid };
  }
}

const db = {
  prepare(sql) { return new Stmt(sql); },
  exec(sql) { _db.run(sql); saveDb(); },
};

// ── Schema & data helpers ───────────────────────────────────────

function migrateSchema() {
  const cols = db.prepare('PRAGMA table_info(orders)').all().map(c => c.name);
  const carCols = db.prepare('PRAGMA table_info(cars)').all().map(c => c.name);

  // Ensure recipients table exists (for DBs created before the migration)
  try {
    db.exec(`CREATE TABLE IF NOT EXISTS recipients (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      name        TEXT NOT NULL,
      phone       TEXT,
      face_image TEXT,
      created_at  TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )`);
  } catch { /* table already exists */ }

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
  db.exec("UPDATE orders SET status = 'queued' WHERE status IN ('pending', 'assigned')");
  db.exec("UPDATE cars SET status = 'queued' WHERE status = 'assigned'");

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

function seedRecipients() {
  const count = db.prepare('SELECT COUNT(*) AS c FROM recipients').get().c;
  if (count > 0) return;

  const FACEDATA_DIR = path.join(__dirname, '..', '..', 'facedata');
  const insert = db.prepare(
    'INSERT INTO recipients (name, phone, face_image) VALUES (?, ?, ?)'
  );

  // Copy one face photo from each person in facedata/ into uploads/faces/
  const mapping = [
    { name: 'zyf', phone: '13800138001', srcDir: 'personA' },
    { name: 'hzh', phone: '13900139002', srcDir: 'personB' },
  ];

  for (const { name, phone, srcDir } of mapping) {
    const srcDirPath = path.join(FACEDATA_DIR, srcDir);
    if (!fs.existsSync(srcDirPath)) continue;

    const files = fs.readdirSync(srcDirPath).filter(f => /\.(jpg|jpeg|png)$/i.test(f));
    if (files.length === 0) continue;

    const srcPath = path.join(srcDirPath, files[0]);
    const ext = path.extname(files[0]);
    const filename = `recipient_${Date.now()}${ext}`;
    const destPath = path.join(UPLOADS_DIR, filename);
    fs.copyFileSync(srcPath, destPath);

    insert.run(name, phone, filename);
    console.log(`已录入收件人: ${name} (${filename})`);
  }
}

function seedIfEmpty() {
  const orderCount = db.prepare('SELECT COUNT(*) AS c FROM orders').get().c;
  if (orderCount > 0) return;

  // Resolve face images from recipients table
  const getFace = (name) => {
    const r = db.prepare('SELECT face_image FROM recipients WHERE name = ?').get(name);
    return r ? r.face_image : null;
  };

  const carId = db.prepare('SELECT id FROM cars ORDER BY id LIMIT 1').get().id;
  const insertOrder = db.prepare(`
    INSERT INTO orders (
      order_no, recipient_name, recipient_phone, classroom_no,
      face_image, package_desc, remark, status, car_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  const samples = [
    ['KD20260712001', 'zyf', '13800138001', '501', getFace('zyf'), '文件袋 × 1', '进入教室后扫描人脸交付', 'navigating', carId],
    ['KD20260712002', 'hzh', '13900139002', '502', getFace('hzh'), '实验器材 × 1', '轻拿轻放', 'queued', carId],
  ];
  for (const row of samples) insertOrder.run(...row);
}

// ── Async init ──────────────────────────────────────────────────

async function initDb() {
  const SQL = await initSqlJs();
  if (fs.existsSync(DB_PATH)) {
    _db = new SQL.Database(fs.readFileSync(DB_PATH));
  } else {
    _db = new SQL.Database();
  }

  // Core PRAGMAs
  _db.run('PRAGMA journal_mode = WAL');
  _db.run('PRAGMA foreign_keys = ON');

  // Bootstrap schema
  const createSql = [
    `CREATE TABLE IF NOT EXISTS cars (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      name        TEXT NOT NULL,
      ip_address  TEXT,
      status      TEXT NOT NULL DEFAULT 'idle',
      created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS floor_config (
      id          INTEGER PRIMARY KEY CHECK (id = 1),
      floor_name  TEXT NOT NULL,
      updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS classrooms (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      classroom_no  TEXT NOT NULL UNIQUE,
      label         TEXT,
      grid_row      INTEGER NOT NULL DEFAULT 0,
      grid_col      INTEGER NOT NULL DEFAULT 0
    )`,
    `CREATE TABLE IF NOT EXISTS orders (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      order_no        TEXT NOT NULL UNIQUE,
      recipient_name  TEXT NOT NULL,
      recipient_phone TEXT NOT NULL,
      classroom_no    TEXT NOT NULL,
      face_image      TEXT,
      package_desc    TEXT,
      remark          TEXT,
      status          TEXT NOT NULL DEFAULT 'queued',
      car_id          INTEGER REFERENCES cars(id) ON DELETE SET NULL,
      created_at      TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )`,
    `CREATE TABLE IF NOT EXISTS recipients (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      name        TEXT NOT NULL,
      phone       TEXT,
      face_image TEXT,
      created_at  TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )`,
  ];
  for (const sql of createSql) { _db.run(sql); }
  saveDb();

  migrateSchema();
  applySiteConfig();
  seedRecipients();
  seedIfEmpty();

  console.log(`SQLite 已就绪 → ${DB_PATH}`);
  return db;
}

function getSingleCar() {
  return db.prepare('SELECT * FROM cars ORDER BY id LIMIT 1').get();
}

function getRecipientByName(name) {
  return db.prepare('SELECT * FROM recipients WHERE name = ?').get(name) || null;
}

module.exports = { db, initDb, UPLOADS_DIR, DB_PATH, getSingleCar, getRecipientByName, SITE_FLOOR, SINGLE_CAR_NAME };
