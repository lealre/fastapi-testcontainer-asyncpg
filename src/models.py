from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase, AsyncAttrs):
    pass


class Ticket(Base):
    __tablename__ = 'tickets'

    id: Mapped[int] = mapped_column(primary_key=True)
    price: Mapped[int]
    is_sold: Mapped[bool] = mapped_column(default=False)
    sold_to: Mapped[str] = mapped_column(nullable=True, default=None)
