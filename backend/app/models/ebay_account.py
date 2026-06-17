import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class EbayEnvironment(str, enum.Enum):
    SANDBOX = 'SANDBOX'
    PRODUCTION = 'PRODUCTION'


class EbayConnectionStatus(str, enum.Enum):
    PENDING = 'PENDING'
    CONNECTED = 'CONNECTED'
    DISCONNECTED = 'DISCONNECTED'
    EXPIRED = 'EXPIRED'
    FAILED = 'FAILED'


class EbayAccount(Base):
    __tablename__ = 'ebay_accounts'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ebay_username: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[EbayEnvironment] = mapped_column(
        Enum(EbayEnvironment, name='ebay_environment'),
        nullable=False,
    )
    connection_status: Mapped[EbayConnectionStatus] = mapped_column(
        Enum(EbayConnectionStatus, name='ebay_connection_status'),
        nullable=False,
        default=EbayConnectionStatus.CONNECTED,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    oauth_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ebay_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    store_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
