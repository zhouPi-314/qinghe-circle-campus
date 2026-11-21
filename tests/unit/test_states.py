"""单元测试：状态机转换规则（6.2 全局约定 4、5 节）。"""

import pytest

from app.core.errors import ConflictError
from app.core.states import (
    ITEM_ACTIVE,
    ITEM_COMPLETED,
    ITEM_IN_PROGRESS,
    ITEM_OFF_SHELF,
    ITEM_ON_HOLD,
    ITEM_RESERVED,
    REQ_CANCELLED,
    REQ_COMPLETED,
    REQ_DISPUTED,
    REQ_HANDOVER_PENDING,
    REQ_IN_PROGRESS,
    REQ_INSPECTION_PENDING,
    REQ_PAYMENT_PENDING,
    REQ_PENDING,
    REQ_REJECTED,
    REQ_RETURN_PENDING,
    validate_item_transition,
    validate_request_transition,
)


class TestItemTransitions:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            (ITEM_ACTIVE, ITEM_RESERVED),
            (ITEM_RESERVED, ITEM_ACTIVE),
            (ITEM_RESERVED, ITEM_OFF_SHELF),  # 回收拒绝（D-036）
            (ITEM_IN_PROGRESS, ITEM_OFF_SHELF),  # 验收不符合（D-036）
            (ITEM_RESERVED, ITEM_IN_PROGRESS),
            (ITEM_RESERVED, ITEM_COMPLETED),
            (ITEM_IN_PROGRESS, ITEM_COMPLETED),
            (ITEM_RESERVED, ITEM_ON_HOLD),
            (ITEM_IN_PROGRESS, ITEM_ON_HOLD),
            (ITEM_COMPLETED, ITEM_ON_HOLD),
            (ITEM_ON_HOLD, ITEM_COMPLETED),
            (ITEM_COMPLETED, ITEM_ACTIVE),
            (ITEM_ACTIVE, ITEM_OFF_SHELF),
            (ITEM_OFF_SHELF, ITEM_ACTIVE),
        ],
    )
    def test_allowed(self, from_status, to_status):
        validate_item_transition(from_status, to_status)

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            (ITEM_ACTIVE, ITEM_COMPLETED),  # 不能跳过业务直接完成
            (ITEM_IN_PROGRESS, ITEM_ACTIVE),  # 流转中不能直接恢复可申请
            (ITEM_ON_HOLD, ITEM_ACTIVE),  # 冻结中不能恢复可申请
            (ITEM_OFF_SHELF, ITEM_RESERVED),
            (ITEM_COMPLETED, ITEM_RESERVED),
        ],
    )
    def test_forbidden(self, from_status, to_status):
        with pytest.raises(ConflictError):
            validate_item_transition(from_status, to_status)


class TestRequestTransitions:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            (REQ_PENDING, REQ_REJECTED),
            (REQ_PENDING, REQ_CANCELLED),
            (REQ_HANDOVER_PENDING, REQ_CANCELLED),
            (REQ_HANDOVER_PENDING, REQ_IN_PROGRESS),
            (REQ_IN_PROGRESS, REQ_RETURN_PENDING),
            (REQ_RETURN_PENDING, REQ_COMPLETED),
            (REQ_RETURN_PENDING, REQ_DISPUTED),
            (REQ_COMPLETED, REQ_DISPUTED),
            (REQ_DISPUTED, REQ_COMPLETED),
            (REQ_PAYMENT_PENDING, REQ_HANDOVER_PENDING),  # 模拟支付成功
            (REQ_HANDOVER_PENDING, REQ_COMPLETED),  # 出售/赠送交接完成
            (REQ_HANDOVER_PENDING, REQ_INSPECTION_PENDING),  # 回收送达
            (REQ_INSPECTION_PENDING, REQ_COMPLETED),  # 验收通过
            (REQ_INSPECTION_PENDING, REQ_REJECTED),  # 验收不符合
        ],
    )
    def test_allowed(self, from_status, to_status):
        validate_request_transition(from_status, to_status)

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            (REQ_PENDING, REQ_IN_PROGRESS),  # 未交接不能直接借用中
            (REQ_PENDING, REQ_COMPLETED),
            (REQ_IN_PROGRESS, REQ_CANCELLED),  # 交接后不能取消（BR-028）
            (REQ_COMPLETED, REQ_CANCELLED),
            (REQ_REJECTED, REQ_PENDING),  # 历史终态不可复活
            (REQ_CANCELLED, REQ_PENDING),
        ],
    )
    def test_forbidden(self, from_status, to_status):
        with pytest.raises(ConflictError):
            validate_request_transition(from_status, to_status)
