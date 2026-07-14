"""
iCar TCP 协议解析 — 共享模块
============================
与 Node.js carEncoder.js 及 Android CarEncoder.kt 帧格式完全兼容。

帧格式:
  $01<TYPE><SIZE><DATA_HEX><CHECKSUM>#

  $      — 帧头
  01     — 协议版本
  TYPE   — 指令类型 (2 字符十六进制, 如 20/21/22)
  SIZE   — 数据区长度 (2 字符十六进制, data_hex 字节数 + 2)
  DATA   — 数据载荷 (十六进制编码的 UTF-8 字符串)
  CHECKSUM — 校验和 (2 字符十六进制, 从 "01" 开始每 2 字符累加取低 8 位)
  #      — 帧尾

用法:
  from .protocol import parse_frame, build_frame, calc_checksum
  cmd = parse_frame(raw_string)   # str -> dict | None
  frame = build_frame(payload, '20')  # dict -> bytes
"""

from __future__ import annotations

import re
import json


def calc_checksum(hex_str: str) -> int:
    """
    计算校验和：从 hex_str 每 2 字符累加，取低 8 位。

    Args:
        hex_str: 十六进制字符串 (大写), 如 "012003"

    Returns:
        0-255 的整数
    """
    total = 0
    for i in range(0, len(hex_str), 2):
        try:
            total += int(hex_str[i:i+2], 16)
        except (ValueError, IndexError):
            continue
    return total % 256


def string_to_hex(s: str) -> str:
    """UTF-8 字符串转大写十六进制"""
    return s.encode('utf-8').hex().upper()


def hex_to_string(h: str) -> str:
    """大写十六进制字符串转 UTF-8 字符串"""
    try:
        return bytes.fromhex(h).decode('utf-8')
    except (ValueError, UnicodeDecodeError):
        return ''


def number_to_hex(num: int, length: int = 2) -> str:
    """整数转指定位数的大写十六进制字符串"""
    return format(num, f'0{length}x').upper()


def parse_frame(raw: str) -> dict | None:
    """
    解析 iCar 协议帧，提取 JSON 载荷。

    格式: $01<TYPE><SIZE><DATA_HEX><CHECKSUM>#

    对于 type=20/21/22 (配送相关), DATA 区是 hex 编码的 UTF-8 JSON。
    同时兼容非标准帧 (直接 JSON 文本嵌入)。

    Args:
        raw: 原始 TCP 数据字符串

    Returns:
        解析出的 JSON 字典, 失败返回 None
    """
    if not raw or not raw.strip():
        return None

    # ── 方式 1: 正则直接提取 JSON (兼容非标准帧, face_bridge 的同款策略) ──
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # ── 方式 2: 标准协议帧解析 ──
    # 帧格式: $01<TYPE=2><SIZE><DATA_HEX><CHECKSUM=2>#
    # SIZE 字段长度可变, 直接跳过它: content[4:-2] = SIZE + DATA_HEX
    try:
        start = raw.index('$')
        end = raw.index('#', start) if '#' in raw[start:] else None
        if end is None:
            return None
        content = raw[start + 1:end]

        if len(content) < 8:
            return None

        frame_type = content[2:4]
        if frame_type not in ('20', '21', '22'):
            return None

        # content = 01 + TYPE(2) + SIZE(variable) + DATA_HEX + CHECKSUM(2)
        # 跳过 SIZE 字段: 从头部之后到末尾 checksum 之前取 DATA_HEX
        # 策略: 从后往前找, checksum 固定 2 字符, data_hex 是剩余部分
        # 尝试不同 SIZE 长度 (2-6), 看哪个能解析出有效 JSON
        for size_len in range(2, 7):
            data_start = 4 + size_len
            data_hex_len = len(content) - data_start - 2
            if data_hex_len <= 0:
                continue
            data_hex = content[data_start:data_start + data_hex_len]
            # hex 字符数必须偶数
            if len(data_hex) % 2 != 0:
                continue
            try:
                json_str = hex_to_string(data_hex)
                if json_str and '{' in json_str:
                    return json.loads(json_str)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

        return None

    except (ValueError, IndexError):
        return None


def build_frame(payload: dict, frame_type: str = '20') -> bytes:
    """
    构建 iCar 协议帧 (供回传 Web 时使用)。

    Args:
        payload: JSON 可序列化的字典
        frame_type: 指令类型 (默认 '20')

    Returns:
        bytes: 完整的帧
    """
    json_str = json.dumps(payload, ensure_ascii=False)
    data_hex = string_to_hex(json_str)

    # 帧格式: $01<type=2><size=4><data_hex><checksum=2>#
    # size = hex 字符数 + checksum 长度(2)
    size = number_to_hex(len(data_hex) + 2, 4)

    prefix = f'01{frame_type}{size}{data_hex}'
    cs = number_to_hex(calc_checksum(prefix), 2)

    frame = f'${prefix}{cs}#'
    return frame.encode('utf-8')
