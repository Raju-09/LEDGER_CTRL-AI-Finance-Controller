import uuid
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class TransactionAuditLog:
    tx_id: str
    reconciled_by: str
    status: str
    amount: float
    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
