import enum


class ProductType(enum.StrEnum):
    SERVICE = "SERVICE"
    GOODS = "GOODS"
    DIGITAL = "DIGITAL"


class BillingInterval(enum.StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class QuotationStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class SubscriptionStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    QUOTATION = "QUOTATION"
    CONFIRMED = "CONFIRMED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class DiscountType(enum.StrEnum):
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"


class InvoiceStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class PaymentMethod(enum.StrEnum):
    CASH = "CASH"
    CARD = "CARD"
    UPI = "UPI"
    BANK_TRANSFER = "BANK_TRANSFER"
    CHEQUE = "CHEQUE"
    ONLINE = "ONLINE"


class PaymentStatus(enum.StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class NotificationChannel(enum.StrEnum):
    EMAIL = "EMAIL"
    IN_APP = "IN_APP"
    SMS = "SMS"


class NotificationStatus(enum.StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    READ = "READ"


class BillingJobStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"