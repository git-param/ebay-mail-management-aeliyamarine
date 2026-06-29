import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class MessageType(Base):
    __tablename__ = 'message_types'
    __table_args__ = (UniqueConstraint('parent_id', 'name', name='uq_message_types_parent_name'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('message_types.id'), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    parent = relationship('MessageType', remote_side=[id], back_populates='children')
    children = relationship('MessageType', back_populates='parent', order_by='MessageType.display_order')


class MessageClassification(Base):
    __tablename__ = 'conversation_message_classifications'
    __table_args__ = (
        UniqueConstraint('conversation_message_id', name='uq_message_classification_message'),
        Index('ix_message_classifications_user_id', 'user_id'),
        Index('ix_message_classifications_seller_account_id', 'seller_account_id'),
        Index('ix_message_classifications_message_type_id', 'message_type_id'),
        Index('ix_message_classifications_conversation_id', 'conversation_id'),
        Index('ix_message_classifications_created_at', 'created_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    conversation_message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('messages.id'), nullable=False)
    seller_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    message_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('message_types.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    message_type = relationship('MessageType')
    message = relationship('Message')
    conversation = relationship('Conversation')
    seller_account = relationship('EbayAccount')
    user = relationship('User')
