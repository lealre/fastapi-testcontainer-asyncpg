from http import HTTPStatus

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Ticket


async def test_get_all_tickets_success(async_session: AsyncSession, async_client: AsyncClient):
    ticket_data_list = [
        {'price': 100, 'is_sold': False, 'sold_to': None},
        {'price': 200, 'is_sold': True, 'sold_to': 'Buyer1'},
        {'price': 150, 'is_sold': False, 'sold_to': None},
    ]

    expected_len = len(ticket_data_list)

    tickets = [Ticket(**data) for data in ticket_data_list]

    async with async_session.begin():
        async_session.add_all(tickets)
        await async_session.commit()

    response = await async_client.get('/tickets/all')

    assert response.status_code == HTTPStatus.OK
    assert len(response.json()['tickets']) == expected_len


async def test_get_all_tickets_when_empty(async_client: AsyncClient):
    response = await async_client.get('/tickets/all')

    assert response.status_code == HTTPStatus.OK
    assert response.json()['tickets'] == []


async def test_create_ticket_success(async_client: AsyncClient):
    expected_price = 100

    response = await async_client.post('/create', json={'price': expected_price})

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {
        'id': 1,
        'price': expected_price,
        'is_sold': False,
        'sold_to': None,
    }


async def test_buy_ticket_success(async_session: AsyncSession, async_client: AsyncClient):
    expected_user = 'test user'
    new_ticket = Ticket(price=100)

    async with async_session.begin():
        async_session.add(new_ticket)
        await async_session.commit()

    response = await async_client.post(
        '/tickets/buy', json={'ticket_id': new_ticket.id, 'user': expected_user}
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        'id': new_ticket.id,
        'price': new_ticket.price,
        'is_sold': True,
        'sold_to': expected_user,
    }


async def test_buy_ticket_when_ticket_not_found(
    async_session: AsyncSession, async_client: AsyncClient
):
    new_ticket = Ticket(price=100)

    async with async_session.begin():
        async_session.add(new_ticket)
        await async_session.commit()

    response = await async_client.post(
        '/tickets/buy', json={'ticket_id': new_ticket.id + 1, 'user': 'other user'}
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['detail'] == 'Ticket was not found'


async def test_buy_ticket_when_already_sold(
    async_session: AsyncSession, async_client: AsyncClient
):
    new_ticket = Ticket(price=100, is_sold=True, sold_to='test user')

    async with async_session.begin():
        async_session.add(new_ticket)
        await async_session.commit()

    response = await async_client.post(
        '/tickets/buy', json={'ticket_id': new_ticket.id, 'user': 'other user'}
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()['detail'] == 'Ticket has already been sold'
