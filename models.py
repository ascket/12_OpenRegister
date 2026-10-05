from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ID компании в OpenRegister.
    # Это основной способ определения дублей.
    openregister_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=True,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    street: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    postal_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )

    city: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    country: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    formatted_address: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    legal_form: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    register_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    register_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    register_court: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    purpose: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(100),
        default="openregister",
        nullable=False,
    )

    source_retrieved_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Позже пригодится для postal marketing.
    do_not_contact: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    __table_args__ = (
        # Дополнительная защита от дублей,
        # если OpenRegister ID по какой-либо причине отсутствует.
        UniqueConstraint(
            "name",
            "street",
            "postal_code",
            "city",
            name="uq_company_address",
        ),
    )


class ImportRun(Base):
    """
    История импортов.

    Позволяет видеть:
    - что искали;
    - сколько получили;
    - сколько добавили;
    - сколько обновили;
    - сколько пропустили.
    """

    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    source: Mapped[str] = mapped_column(
        String(100),
        default="openregister",
        nullable=False,
    )

    city: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    postal_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    industry_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    purpose_keyword: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    requested_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    received_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    inserted_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    updated_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    duplicate_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    skipped_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
