/**
 * 小车 TCP 协议编码（与 Android CarEncoder.kt 帧格式一致）
 * 帧格式: $01<type><size><data><checksum>#
 */

function numberToHex(num, len) {
  return num.toString(16).padStart(len, '0').toUpperCase();
}

function checksum(data) {
  let sum = 0;
  for (let i = 0; i < data.length; i += 2) {
    sum += parseInt(data.substring(i, i + 2), 16);
  }
  return sum % 256;
}

function baseEncode(type, ...datas) {
  const info = datas.join('');
  const size = numberToHex(info.length + 2, 4);
  let code = `01${type}${size}${info}`;
  code += numberToHex(checksum(code), 2);
  return `$${code}#`;
}

function stringToHex(str) {
  return Buffer.from(str, 'utf8').toString('hex').toUpperCase();
}

/** type=20 订单下发，data 为 UTF-8 JSON 的十六进制编码 */
function encodeOrderFrame(orderPayload) {
  const json = JSON.stringify(orderPayload);
  return baseEncode('20', stringToHex(json));
}

/** type=21 订单取消 */
function encodeCancelFrame(orderNo) {
  return baseEncode('21', stringToHex(JSON.stringify({ action: 'cancel', order_no: orderNo })));
}

/** type=22 人脸扫描指令 */
function encodeFaceScanFrame(scanPayload) {
  const json = JSON.stringify(scanPayload);
  return baseEncode('22', stringToHex(json));
}

module.exports = { encodeOrderFrame, encodeCancelFrame, encodeFaceScanFrame, baseEncode };
