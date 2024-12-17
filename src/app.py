from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import and_, select, update

from src.database import AsyncSession, engine, get_session
from src.models import Ticket, table_register
from src.schemas import (
    ListTickets,
    TicketRequestBuy,
    TicketRequestCreate,
    TicketResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(table_register.metadata.create_all)
        yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@app.get('/tickets/all', response_model=ListTickets)
async def get_all_tickets(session: SessionDep):
    async with session.begin():
        tickets = await session.scalars(select(Ticket))

    all_tickets = tickets.all()

    return {'tickets': all_tickets}


@app.post(
    '/tickets/create',
    response_model=TicketResponse,
    status_code=HTTPStatus.CREATED,
)
async def create_ticket(session: SessionDep, ticket_in: TicketRequestCreate):
    new_ticket = Ticket(**ticket_in.model_dump())

    async with session.begin():
        session.add(new_ticket)
        await session.commit()

    async with session.begin():
        await session.refresh(new_ticket)

    return new_ticket


@app.post('/tickets/buy', response_model=TicketResponse)
async def get_ticket_by_id(session: SessionDep, ticket_in: TicketRequestBuy):
    async with session.begin():
        ticket_db = await session.scalar(
            select(Ticket).where(Ticket.id == ticket_in.ticket_id)
        )

    if not ticket_db:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Ticket was not found'
        )

    async with session.begin():
        stm = (
            update(Ticket)
            .where(
                and_(
                    Ticket.id == ticket_in.ticket_id,
                    Ticket.is_sold == False,  # noqa: E712
                )
            )
            .values(is_sold=True, sold_to=ticket_in.user)
        )

        ticket_updated = await session.execute(stm)

        if ticket_updated.rowcount == 0:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail='Ticket has already been sold',
            )

        await session.commit()

    async with session.begin():
        await session.refresh(ticket_db)

    return ticket_db
