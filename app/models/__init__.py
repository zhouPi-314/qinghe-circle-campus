"""SQLAlchemy 模型包：导入全部模型模块完成表注册。"""

from app.models.charity import (  # noqa: F401
    CharityDonation,
    CharityDonationItem,
    CharityProject,
    CharityProjectNeed,
    CharityReceipt,
    CharityReceiptItem,
)
from app.models.circulation import (  # noqa: F401
    BorrowDetails,
    CirculationRequest,
    HandoverRecord,
    RecycleDetails,
    SaleDetails,
)
from app.models.governance import (  # noqa: F401
    AuditLog,
    Dispute,
    DisputeMessage,
    Notification,
    StatusHistory,
)
from app.models.item import Item, ItemCategory, ItemImage  # noqa: F401
from app.models.university import (  # noqa: F401
    Campus,
    LoginVerificationCode,
    Station,
    StationManagerAssignment,
    StudentImportBatch,
    StudentRegistryRecord,
    University,
)
from app.models.user import User  # noqa: F401
