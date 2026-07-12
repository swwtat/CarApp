const net = require('net');
const fs = require('fs');
const path = require('path');
const { encodeOrderFrame, encodeCancelFrame } = require('./carEncoder');
const { SITE_FLOOR } = require('./db');

const TCP_TIMEOUT = 5000;
const DEFAULT_TCP_PORT = 6000;

function buildOrderPayload(order, uploadsDir) {
  let faceImageBase64 = null;
  let faceImageExt = null;

  if (order.face_image) {
    const facePath = path.join(uploadsDir, order.face_image);
    if (fs.existsSync(facePath)) {
      faceImageBase64 = fs.readFileSync(facePath).toString('base64');
      faceImageExt = path.extname(order.face_image).replace('.', '') || 'jpg';
    }
  }

  return {
    action: 'delivery_order',
    order_id: order.id,
    order_no: order.order_no,
    floor_name: SITE_FLOOR,
    classroom_no: order.classroom_no,
    recipient_name: order.recipient_name,
    recipient_phone: order.recipient_phone,
    package_desc: order.package_desc || '',
    remark: order.remark || '',
    status: order.status,
    face_image_base64: faceImageBase64,
    face_image_ext: faceImageExt,
    delivery_steps: [
      { step: 1, action: 'navigate', target: order.classroom_no },
      { step: 2, action: 'enter', target: order.classroom_no },
      { step: 3, action: 'face_scan' },
      { step: 4, action: 'deliver' },
    ],
  };
}

function sendTcpFrame(host, port, frame) {
  return new Promise((resolve) => {
    if (!host) {
      return resolve({ ok: false, error: '小车 IP 未配置' });
    }

    const socket = new net.Socket();
    let settled = false;

    const finish = (result) => {
      if (settled) return;
      settled = true;
      try { socket.destroy(); } catch { /* ignore */ }
      resolve(result);
    };

    socket.setTimeout(TCP_TIMEOUT);

    socket.connect(port, host, () => {
      socket.write(frame, 'utf8', (err) => {
        if (err) return finish({ ok: false, error: err.message });
        finish({ ok: true, bytes: Buffer.byteLength(frame, 'utf8') });
      });
    });

    socket.on('error', (err) => finish({ ok: false, error: err.message }));
    socket.on('timeout', () => finish({ ok: false, error: `TCP 连接超时 (${host}:${port})` }));
  });
}

async function pushOrderToCar(order, car, uploadsDir) {
  const payload = buildOrderPayload(order, uploadsDir);
  const frame = encodeOrderFrame(payload);
  const port = car?.tcp_port || DEFAULT_TCP_PORT;
  const result = await sendTcpFrame(car?.ip_address, port, frame);

  return {
    ...result,
    host: car?.ip_address,
    port,
    order_no: order.order_no,
    classroom_no: order.classroom_no,
    frame_preview: frame.length > 80 ? `${frame.slice(0, 80)}...` : frame,
  };
}

async function cancelOrderOnCar(orderNo, car) {
  const frame = encodeCancelFrame(orderNo);
  const port = car?.tcp_port || DEFAULT_TCP_PORT;
  return sendTcpFrame(car?.ip_address, port, frame);
}

module.exports = { pushOrderToCar, cancelOrderOnCar, buildOrderPayload };
