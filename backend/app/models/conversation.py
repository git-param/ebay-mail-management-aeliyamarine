import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class ConversationStatus(str, enum.Enum):
    OPEN = 'OPEN'
    PENDING = 'PENDING'
    RESOLVED = 'RESOLVED'
    CLOSED = 'CLOSED'


class MessageSenderType(str, enum.Enum):
    CUSTOMER = 'CUSTOMER'
    AGENT = 'AGENT'
    SYSTEM = 'SYSTEM'
    PROVIDER = 'PROVIDER'


class SyncLogStatus(str, enum.Enum):
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'


class Conversation(Base):
    """Represent one buyer support thread and its current operational state."""
    __tablename__ = 'conversations'
    __table_args__ = (
        UniqueConstraint('provider', 'provider_conversation_id', name='uq_conversations_provider_external_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    buyer_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_conversation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_conversation_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linked_order_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('orders.id'), nullable=True)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name='conversation_status'),
        nullable=False,
        default=ConversationStatus.OPEN,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('categories.id'), nullable=True)
    category_manually_selected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    category = relationship('Category')
    linked_order = relationship('EbayOrder')
    order_mapping = relationship(
        'ConversationOrderContext',
        back_populates='conversation',
        cascade='all, delete-orphan',
        uselist=False,
    )
    product_context = relationship(
        'ConversationProductContext',
        back_populates='conversation',
        cascade='all, delete-orphan',
        uselist=False,
    )
    offers = relationship('Offer', back_populates='conversation', cascade='all, delete-orphan', order_by='Offer.created_at')
    messages = relationship(
        'Message',
        back_populates='conversation',
        cascade='all, delete-orphan',
        order_by='Message.sent_at',
    )
    participants = relationship(
        'ConversationParticipant',
        back_populates='conversation',
        cascade='all, delete-orphan',
        order_by='ConversationParticipant.created_at',
    )
    assignments = relationship(
        'ConversationAssignment',
        back_populates='conversation',
        cascade='all, delete-orphan',
        order_by='ConversationAssignment.assigned_at',
    )
    status_history = relationship(
        'ConversationStatusHistory',
        back_populates='conversation',
        cascade='all, delete-orphan',
        order_by='ConversationStatusHistory.changed_at',
    )
    category_history = relationship(
        'ConversationCategoryHistory',
        back_populates='conversation',
        cascade='all, delete-orphan',
        order_by='ConversationCategoryHistory.changed_at',
    )
    notes = relationship(
        'ConversationNote',
        back_populates='conversation',
        cascade='all, delete-orphan',
        order_by='ConversationNote.created_at',
    )
    sla_history = relationship(
        'ConversationSLAHistory',
        back_populates='conversation',
        cascade='all, delete-orphan',
        order_by='ConversationSLAHistory.cycle_number',
    )


class ConversationSLAHistory(Base):
    """
    Preserve one immutable first-response measurement per inbound SLA cycle.

    A cycle begins with a buyer message and is completed by the first reply
    that eBay accepts. Later messages create new rows rather than changing a
    previously reported response time.
    """

    __tablename__ = 'conversation_sla_history'
    __table_args__ = (
        UniqueConstraint('conversation_id', 'cycle_number', name='uq_conversation_sla_cycle'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False, index=True)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    buyer_message_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    replied_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    replied_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, index=True)
    response_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sla_met: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    conversation = relationship('Conversation', back_populates='sla_history')
    replying_user = relationship('User')


class Message(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        UniqueConstraint('provider', 'provider_message_id', name='uq_messages_provider_external_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_type: Mapped[MessageSenderType] = mapped_column(
        Enum(MessageSenderType, name='message_sender_type'),
        nullable=False,
    )
    sender_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    read_status: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_inbound: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    conversation = relationship('Conversation', back_populates='messages')
    attachments = relationship(
        'MessageAttachment',
        back_populates='message',
        cascade='all, delete-orphan',
        order_by='MessageAttachment.created_at',
    )


class MessageAttachment(Base):
    __tablename__ = 'message_attachments'
    __table_args__ = (
        UniqueConstraint('message_id', 'provider_attachment_id', name='uq_message_attachments_provider_attachment'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('messages.id'), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('ebay_accounts.id'), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_attachment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    media_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    message = relationship('Message', back_populates='attachments')


class ConversationParticipant(Base):
    __tablename__ = 'conversation_participants'
    __table_args__ = (
        UniqueConstraint(
            'conversation_id',
            'participant_identifier',
            'participant_type',
            name='uq_conversation_participants_identity',
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    participant_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    participant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    participant_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    conversation = relationship('Conversation', back_populates='participants')


class ConversationAssignment(Base):
    __tablename__ = 'conversation_assignments'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    assigned_to: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    assigned_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation = relationship('Conversation', back_populates='assignments')
    assignee = relationship('User', foreign_keys=[assigned_to])
    assigner = relationship('User', foreign_keys=[assigned_by])


class ConversationStatusHistory(Base):
    __tablename__ = 'conversation_status_history'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    old_status: Mapped[ConversationStatus | None] = mapped_column(Enum(ConversationStatus, name='conversation_status'), nullable=True)
    new_status: Mapped[ConversationStatus] = mapped_column(Enum(ConversationStatus, name='conversation_status'), nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    conversation = relationship('Conversation', back_populates='status_history')
    user = relationship('User')


class ConversationCategoryHistory(Base):
    __tablename__ = 'conversation_category_history'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    old_category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('categories.id'), nullable=True)
    new_category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('categories.id'), nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    conversation = relationship('Conversation', back_populates='category_history')
    old_category = relationship('Category', foreign_keys=[old_category_id])
    new_category = relationship('Category', foreign_keys=[new_category_id])
    user = relationship('User')


class ConversationNote(Base):
    __tablename__ = 'conversation_notes'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    conversation = relationship('Conversation', back_populates='notes')
    author = relationship('User')


class SyncLog(Base):
    __tablename__ = 'sync_logs'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sync_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[SyncLogStatus] = mapped_column(Enum(SyncLogStatus, name='sync_log_status'), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_metadata: Mapped[dict | None] = mapped_column('metadata', JSONB, nullable=True)
