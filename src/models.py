from sqlalchemy.orm import Mapped, mapped_column, registry

table_register = registry()


@table_register.mapped_as_dataclass
class Ticket:
    __tablename__ = 'tickets'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    price: Mapped[int]
    is_sold: Mapped[bool] = mapped_column(default=False)
    sold_to: Mapped[str | None] = mapped_column(nullable=True, default=None)
