from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, String, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Two-factor authentication (authenticator-app TOTP). The secret is stored
    # while setup is pending; totp_enabled flips once the user proves they can
    # generate a code.
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    # Last accepted 30-second time step, so a code can't be replayed.
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # SHA-256 hashes of the unused one-time recovery codes.
    recovery_code_hashes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
