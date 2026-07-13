"""
配送状态定义 — 共享枚举与数据结构
==================================
供 delivery_controller 和其他节点共同使用。
"""

from enum import Enum


class DeliveryState(Enum):
    """配送状态机"""
    IDLE = 'idle'               # 空闲, 等待订单
    NAVIGATING = 'navigating'   # 正在导航到目标教室
    ARRIVED = 'arrived'         # 已到达教室门口
    ENTERING = 'entering'       # 正在驶入教室
    SCANNING = 'scanning'       # 正在进行人脸核验
    VERIFIED = 'verified'       # 核验通过, 等待取件
    DELIVERING = 'delivering'   # 正在递交货物
    RETURNING = 'returning'     # 返回充电桩途中
    DONE = 'done'               # 配送完成
    FAILED = 'failed'           # 配送失败


# 状态 → 中文标签
STATE_LABELS = {
    DeliveryState.IDLE: '空闲',
    DeliveryState.NAVIGATING: '前往教室',
    DeliveryState.ARRIVED: '已到达',
    DeliveryState.ENTERING: '驶入教室',
    DeliveryState.SCANNING: '人脸核验中',
    DeliveryState.VERIFIED: '核验通过',
    DeliveryState.DELIVERING: '递交货物',
    DeliveryState.RETURNING: '返回充电桩',
    DeliveryState.DONE: '配送完成',
    DeliveryState.FAILED: '配送失败',
}

# 终态集合
TERMINAL_STATES = {DeliveryState.DONE, DeliveryState.FAILED}

# 活跃态 (可取消)
ACTIVE_STATES = {
    DeliveryState.NAVIGATING,
    DeliveryState.ENTERING,
    DeliveryState.SCANNING,
    DeliveryState.DELIVERING,
    DeliveryState.RETURNING,
}


def build_status_msg(
    state: DeliveryState,
    order_id: int = None,
    order_no: str = None,
    classroom_no: str = None,
    recipient_name: str = None,
    message: str = None,
    extra: dict = None,
) -> dict:
    """
    构建标准配送状态消息。

    Returns:
        dict: 可直接 JSON 序列化的状态报告
    """
    msg = {
        'state': state.value,
        'state_label': STATE_LABELS.get(state, state.value),
        'timestamp': None,  # 由调用方填入
    }
    if order_id is not None:
        msg['order_id'] = order_id
    if order_no is not None:
        msg['order_no'] = order_no
    if classroom_no is not None:
        msg['classroom_no'] = classroom_no
    if recipient_name is not None:
        msg['recipient_name'] = recipient_name
    if message is not None:
        msg['message'] = message
    if extra:
        msg.update(extra)
    return msg
