"""统一状态机：物品状态与流转申请状态。

状态集合、中文名与允许转换均来自 6.2 全局约定第 4、5 节；
service 层的每次状态变更必须经 validate_item_transition /
validate_request_transition 校验并写状态历史。
"""

from __future__ import annotations

from app.core.errors import ConflictError

# ---------------------------------------------------------------------------
# 物品状态
# ---------------------------------------------------------------------------

ITEM_ACTIVE = "active"
ITEM_RESERVED = "reserved"
ITEM_IN_PROGRESS = "in_progress"
ITEM_COMPLETED = "completed"
ITEM_OFF_SHELF = "off_shelf"
ITEM_ON_HOLD = "on_hold"

ITEM_STATUS_LABELS = {
    "active": "可申请",
    "reserved": "已被申请",
    "in_progress": "流转中",
    "completed": "已完成",
    "off_shelf": "已下架",
    "on_hold": "异常冻结",
}

# ---------------------------------------------------------------------------
# 流转申请状态
# ---------------------------------------------------------------------------

REQ_PENDING = "pending"
REQ_ACCEPTED = "accepted"
REQ_PAYMENT_PENDING = "payment_pending"
REQ_HANDOVER_PENDING = "handover_pending"
REQ_IN_PROGRESS = "in_progress"
REQ_RETURN_PENDING = "return_pending"
REQ_INSPECTION_PENDING = "inspection_pending"
REQ_COMPLETED = "completed"
REQ_REJECTED = "rejected"
REQ_CANCELLED = "cancelled"
REQ_DISPUTED = "disputed"

REQUEST_STATUS_LABELS = {
    "pending": "待处理",
    "accepted": "已接受",
    "payment_pending": "待模拟支付",
    "handover_pending": "待交接",
    "in_progress": "借用中",
    "return_pending": "待归还确认",
    "inspection_pending": "待回收验收",
    "completed": "已完成",
    "rejected": "已拒绝",
    "cancelled": "已取消",
    "disputed": "争议中",
}

# 与数据库部分唯一索引 uq_active_request_per_item 保持一致
ACTIVE_REQUEST_STATUSES = frozenset(
    {
        REQ_PENDING,
        REQ_ACCEPTED,
        REQ_PAYMENT_PENDING,
        REQ_HANDOVER_PENDING,
        REQ_IN_PROGRESS,
        REQ_RETURN_PENDING,
        REQ_INSPECTION_PENDING,
        REQ_DISPUTED,
    }
)

# ---------------------------------------------------------------------------
# 允许转换（6.2 全局约定 5.1/5.2）
# ---------------------------------------------------------------------------

_ITEM_TRANSITIONS = {
    (ITEM_ACTIVE, ITEM_RESERVED),  # 创建活动申请
    (ITEM_RESERVED, ITEM_ACTIVE),  # 拒绝/取消/模拟支付失败
    (ITEM_RESERVED, ITEM_IN_PROGRESS),  # 借用交接成功 / 回收交接成功
    (ITEM_RESERVED, ITEM_COMPLETED),  # 出售/赠送交接成功
    (ITEM_IN_PROGRESS, ITEM_COMPLETED),  # 归还确认 / 回收验收通过
    (ITEM_RESERVED, ITEM_ON_HOLD),  # 发起争议或管理员冻结
    (ITEM_IN_PROGRESS, ITEM_ON_HOLD),
    (ITEM_COMPLETED, ITEM_ON_HOLD),  # 完成后发起争议
    (ITEM_ON_HOLD, ITEM_COMPLETED),  # 争议关闭且业务完成
    (ITEM_COMPLETED, ITEM_ACTIVE),  # 所有者重新上架（回收除外）
    (ITEM_ACTIVE, ITEM_OFF_SHELF),  # 所有者下架
    (ITEM_OFF_SHELF, ITEM_ACTIVE),  # 所有者重新上架
    # 回收站点拒绝：申请终止，物品不自动回到可申请，所有者可重新上架（D-036）
    (ITEM_RESERVED, ITEM_OFF_SHELF),
    (ITEM_IN_PROGRESS, ITEM_OFF_SHELF),
}

# 借用主链：pending → accepted → handover_pending → in_progress → return_pending → completed
_REQUEST_TRANSITIONS = {
    # 通用
    (REQ_PENDING, REQ_ACCEPTED),
    (REQ_PENDING, REQ_REJECTED),
    (REQ_PENDING, REQ_CANCELLED),
    (REQ_ACCEPTED, REQ_HANDOVER_PENDING),  # 服务端准备交接
    (REQ_ACCEPTED, REQ_CANCELLED),  # 交接前取消
    (REQ_PAYMENT_PENDING, REQ_CANCELLED),
    (REQ_HANDOVER_PENDING, REQ_CANCELLED),  # 交接前取消
    (REQ_ACCEPTED, REQ_PAYMENT_PENDING),  # 出售：进入模拟支付（G3）
    # 借用
    (REQ_HANDOVER_PENDING, REQ_IN_PROGRESS),  # 取件交接成功
    (REQ_IN_PROGRESS, REQ_RETURN_PENDING),  # 借用人提交归还
    (REQ_RETURN_PENDING, REQ_COMPLETED),  # 出借人确认归还
    (REQ_RETURN_PENDING, REQ_DISPUTED),  # 归还损坏或不符
    (REQ_COMPLETED, REQ_DISPUTED),  # 完成后争议（条件允许时）
    (REQ_DISPUTED, REQ_COMPLETED),  # 管理员处理争议关闭
    # 出售（6.2 分模式路径：payment_pending → handover_pending → completed）
    (REQ_PAYMENT_PENDING, REQ_HANDOVER_PENDING),  # 模拟支付成功
    (REQ_HANDOVER_PENDING, REQ_COMPLETED),  # 出售/赠送交接成功
    # 回收（交接成功后进入待验收；验收通过完成、不符合终止）
    (REQ_HANDOVER_PENDING, REQ_INSPECTION_PENDING),  # 送达交接成功
    (REQ_INSPECTION_PENDING, REQ_COMPLETED),  # 站点验收通过
    (REQ_INSPECTION_PENDING, REQ_REJECTED),  # 验收不符合（D-036）
}

# 活动状态下允许发起争议的申请状态
DISPUTABLE_REQUEST_STATUSES = frozenset({REQ_IN_PROGRESS, REQ_RETURN_PENDING, REQ_COMPLETED})


def validate_item_transition(from_status: str, to_status: str) -> None:
    """校验物品状态转换；不允许的跳跃返回状态冲突错误。"""
    if (from_status, to_status) not in _ITEM_TRANSITIONS:
        raise ConflictError(
            f"物品当前状态（{ITEM_STATUS_LABELS.get(from_status, from_status)}）"
            f"不能变更为（{ITEM_STATUS_LABELS.get(to_status, to_status)}）。"
        )


def validate_request_transition(from_status: str, to_status: str) -> None:
    """校验流转申请状态转换；不允许跨模式跳跃。"""
    if (from_status, to_status) not in _REQUEST_TRANSITIONS:
        raise ConflictError(
            f"申请当前状态（{REQUEST_STATUS_LABELS.get(from_status, from_status)}）"
            f"不能变更为（{REQUEST_STATUS_LABELS.get(to_status, to_status)}）。"
        )


# ---------------------------------------------------------------------------
# 公益状态（6.2 全局约定第 6 节）
# ---------------------------------------------------------------------------

CHARITY_PROJECT_ACTIVE = "active"
CHARITY_PROJECT_COMPLETED = "completed"

DONATION_STATUS_LABELS = {
    "pending": "待核验",
    "received": "已接收",
    "rejected": "已拒绝",
    "cancelled": "已取消",
}

RECEIPT_STATUS_LABELS = {"draft": "草稿", "published": "已公示"}
