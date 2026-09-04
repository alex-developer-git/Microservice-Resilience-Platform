from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MonitoredService(Base):
    __tablename__ = "monitored_services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    health_check_path: Mapped[str] = mapped_column(String(256), nullable=False)
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    failure_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    recovery_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
