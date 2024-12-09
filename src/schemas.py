from pydantic import BaseModel


class TicketBase(BaseModel):
    price: int
    is_sold: bool = False
    sold_to: str | None = None


class TicketResponse(TicketBase):
    id: int


class TicketRequestCreate(TicketBase):
    pass


class TicketRequestBuy(BaseModel):
    ticket_id: int
    user: str


class ListTickets(BaseModel):
    tickets: list[TicketResponse]
