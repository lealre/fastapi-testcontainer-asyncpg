---
hide:
  - navigation
---

# Testcontainers with FastAPI and asyncpg

![image.svg](image.svg)

When I first got to know about [testcontainers](https://testcontainers.com/){:target="\_blank"}, I wanted to learn how to integrate it with [`asyncpg`](https://magicstack.github.io/asyncpg/current/){:target="\_blank"}, an asynchronous driver for PostgreSQL, for testing asynchronous routes in FastAPI. In an initial reference search, I found [this article](https://www.linkedin.com/pulse/utilizando-testcontainers-fastapi-guilherme-de-carvalho-carneiro-9cmlf/){:target="\_blank"} by [Guilherme](https://www.linkedin.com/in/guilhermecarvalho/){:target="\_blank"}, and based on his article, I decided to write this example application.

You can check the complete repository [here](https://github.com/lealre/fastapi-testcontainer-asyncpg){:target="\_blank"}.

TL;DR: The full `conftest.py` setup is available [here](#final-version-of-test-fixtures).

## Testcontainers

Testcontainers is an open-source library for providing lightweight instances of anything that can run in a Docker container. It was originally implemented for .NET, Go, Java, and Node.js but has since been extended to other programming languages through community projects, including Python: [testcontainer-python](https://testcontainers-python.readthedocs.io/en/latest/){:target="\_blank"}.

Below is a documentation example of how to use an instance of PostgreSQL, which uses [`psycopg2`](https://github.com/psycopg/psycopg2){:target="\_blank"} as the default driver.

```py
>>> from testcontainers.postgres import PostgresContainer
>>> import sqlalchemy

>>> with PostgresContainer("postgres:16") as postgres:
...    psql_url = postgres.get_connection_url()
...    engine = sqlalchemy.create_engine(psql_url)
...    with engine.begin() as connection:
...        version, = connection.execute(sqlalchemy.text("SELECT version()")).fetchone()
>>> version
'PostgreSQL 16...'
```

## Context

The objective of this repository is to test asynchronous FastAPI endpoints using PostgreSQL as a database. To achieve that, besides the `testcontainers`, it uses [`pytest`](https://docs.pytest.org/en/stable/){:target="\_blank"} and [`anyio`](https://anyio.readthedocs.io/en/stable/testing.html){:target="\_blank"}, which provides built-in support for testing applications in the form of a pytest plugin. The choice of `anyio` over `pytest-asyncio` is because FastAPI is based on Starlette, which uses AnyIO, so we don't need to install an additional package here.

The development of the API routes uses [aiosqlite](https://aiosqlite.omnilib.dev/en/stable/){:target="\_blank"}, the async driver for SQLite.

Below are all the dependencies used to run the example.

```txt title="requirements.txt"
aiosqlite>=0.20.0
asyncpg>=0.30.0
fastapi[standard]>=0.115.6
pytest>=8.3.4
sqlalchemy>=2.0.36
testcontainers>=4.8.2
```

The repository README contains all the steps to run it locally using [uv](https://docs.astral.sh/uv/){:target="\_blank"}.

Below is how the example is structured:

```yaml
.
├── src # (1)
│   ├── app.py
│   ├── database.py
│   ├── models.py
│   └── schemas.py
└── tests
    ├── conftest.py # (2)
    └── test_routes.py
```

1. Where the example API is written using FastAPI.
2. Where API test fixtures are written, from the PostgreSQL instance to the client. You can learn more about the `conftest.py` file in the <a href="https://docs.pytest.org/en/stable/reference/fixtures.html#conftest-py-sharing-fixtures-across-multiple-files" target="_blank">pytest docs</a>.

## API routes implementation

This section will show the endpoints created for later tests. For this example, three simple routes were created to simulate a ticketing sell system:

- `GET /tickets/all` - To list all the available tickets
- `POST /tickets/create` - To create a new ticket to sell
- `POST /tickets/buy` - To buy an available ticket to sell

In the database, besides the `id` field, the ticket table has: a `price` field, a boolean field `is_sold` to identify if it's sold or not, and a `sold_to` field to identify who the ticket was sold to. The `models.py` file contains this information, using the [`SQLAlchemy`](https://www.sqlalchemy.org/){:target="\_blank"} ORM.

```py title="src/models.py" linenums="1"
from sqlalchemy.orm import Mapped, mapped_column, registry

table_register = registry()


@table_register.mapped_as_dataclass
class Ticket:
    __tablename__ = 'tickets'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    price: Mapped[int]
    is_sold: Mapped[bool] = mapped_column(default=False)
    sold_to: Mapped[str] = mapped_column(nullable=True, default=None)
```

The `database.py` contains the database connection, as well as the `get_session()` generator, responsible for creating asynchronous sessions to perform transactions in the database.

```python title="src/database.py" linenums="1"
import typing

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = 'sqlite+aiosqlite:///db.sqlite3'

engine = create_async_engine(DATABASE_URL, future=True, echo=True)

AsyncSessionLocal = async_sessionmaker(
    autocommit=False,
    expire_on_commit=False,
    autoflush=True,
    bind=engine,
    class_=AsyncSession,
)


async def get_session() -> typing.AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

The last file before creating the routes is the `schemas.py`, which will contain all the [Pydantic](https://docs.pydantic.dev/latest/){:target="\_blank"} models.

```py title="src/schemas.py" linenums="1"
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
```

The previous three files are imported in `app.py`, which contains the API routes for this example. As mentioned earlier, although the objective is to test the endpoints with a PostgreSQL database, the development of the API uses SQLite to avoid the need for a PostgreSQL instance running constantly.

To keep things simple and avoid database migrations, the database creation is handled using [lifespan events](https://fastapi.tiangolo.com/advanced/events/){:target="\_blank"}. This guarantees that every time we run the application, a database will be created if it doesn't already exist.

```py title="src/app.py" linenums="1" hl_lines="18-24"
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
```

Below are the route implementations, as well as the `SessionDep` to be used as [dependency injection](https://fastapi.tiangolo.com/tutorial/dependencies/){:target="\_blank"} in each route.

```py title="src/app.py" linenums="27" hl_lines="3"
...

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

```

Now, by running the command below in the terminal, the application should be available at `http://127.0.0.1:8000`.

=== "pip"

    ```bash
    python -m fastapi dev src/app.py
    ```

=== "uv"

    ``` bash
    uv run -m fastapi dev src/app.py
    ```

## Tests workflow

To use PostgreSQL in the tests, the testcontainer will be set up in `conftest.py`, along with the database session and the client required to test the endpoints.

Below is a simple diagram illustrating how it works **for each test**, where each block represents a different function.

```mermaid
flowchart LR
    %% Nodes for fixtures
    postgres_container["postgres_container"]
    async_session["async_session"]
    async_client["async_client"]
    test["Test"]

    %% Subgraph for dependencies
    subgraph Fixtures in conftest.py
        direction LR
        postgres_container --> async_session
        async_session --> async_client
    end

    %% Arrows from async_client to test blocks
    async_client --> test
    async_session --> test

    %% Style the nodes with rounded corners
    classDef fixtureStyle rx:10, ry:10;

    %% Style the nodes
    class postgres_container,async_session,async_client,test fixtureStyle;
```

The `postgres_container` will be passed to `async_session`, which will be used in both `async_client` and directly in the tests, in cases where we need to transact directly with the database.

## Creating the test fixtures

The first fixture inserted in `conftest.py` is the `anyio_backend`, highlighted in the code below. This function will be used in `postgres_container` and marked for the AnyIO pytest plugin, as well as setting `asyncio` as the backend to run the tests. This function was not included in the previous diagram because it is an AnyIO specification. You can check more details about it [here](https://anyio.readthedocs.io/en/stable/testing.html#specifying-the-backends-to-run-on).

```py title="tests/conftest.py" linenums="1" hl_lines="15-17"
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from src.app import app
from src.database import get_session
from src.models import table_register


@pytest.fixture
def anyio_backend():
    return 'asyncio'
```

Now, in the `postgres_container`, the `anyio_backend` is passed, and all the tests that use the `postgres_container` as a fixture at any level will be marked to run asynchronously.

Below is the `postgres_container` function, which will be responsible for creating the `PostgresContainer` instance from `testcontainers`. The `asyncpg` driver is passed as an argument to specify that it will be the driver used.

```py title="tests/conftest.py" linenums="20"
@pytest.fixture
def postgres_container(anyio_backend):
    with PostgresContainer('postgres:16', driver='asyncpg') as postgres:
        yield postgres
```

The `async_session` takes the connection URL from the `PostgresContainer` object returned by the `postgres_container` function and uses it to create the tables inside the database, as well as the session that will handle all interactions with the PostgreSQL instance created. The function will return and persist a session to be used, and then restore the database for the next test by deleting the tables.

```py title="tests/conftest.py" linenums="26"
@pytest.fixture
async def async_session(postgres_container: PostgresContainer):
    async_db_url = postgres_container.get_connection_url()
    async_engine = create_async_engine(async_db_url, pool_pre_ping=True)

    async with async_engine.begin() as conn:
        await conn.run_sync(table_register.metadata.drop_all)
        await conn.run_sync(table_register.metadata.create_all)

    async_session = async_sessionmaker(
        autoflush=False,
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session

    await async_engine.dispose()
```

The last fixture is the `async_client` function, which will create the [`AsyncClient`](https://fastapi.tiangolo.com/advanced/async-tests/), directly imported from [HTTPX](https://www.python-httpx.org/), and provide it to make requests to our endpoints. Here, the session provided by `async_session` will override the session originally used in our app as a dependency injection while the client is being used.

```py title="tests/conftest.py" linenums="48"
@pytest.fixture
async def async_client(async_session: async_sessionmaker[AsyncSession]):
    app.dependency_overrides[get_session] = lambda: async_session
    _transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=_transport, base_url='http://test', follow_redirects=True
    ) as client:
        yield client

    app.dependency_overrides.clear()
```

## Running the tests

With all the test fixtures created, it's now possible to write and run the tests.

Below are the test examples for the `GET /tickets/all`. The first one inserts 3 records in the table using the `async_session` and then asserts if the response has a 200 status and the list returned has a length of 3. The second one tests the case where there are no records yet in the database, as the response must return a 200 status and an empty list.

```py title="tests/test_routes.py" linenums="1"
from http import HTTPStatus

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Ticket


async def test_get_all_tickets_success(
    async_session: AsyncSession, async_client: AsyncClient
):
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
```

In total there are 6 test, and the rest of them has the same logic. Their full implementations can be checked in the repository.

Adding the following setting in `pyproject.toml` or `pytest.ini` will inform pytest to add the root directory to the Python search path when running tests.

=== "pyproject.toml"

    ``` toml
    [tool.pytest.ini_options]
    pythonpath = '.'
    ```

=== "pytest.ini"

    ```
    [pytest]
    pythonpath = .
    ```

Now, if we run the following command in the terminal...

=== "pip"

    ``` bash
    pytest -vv
    ```

=== "uv"

    ``` bash
    uv run pytest -vv
    ```

...we will see something similar to this:

```
tests/test_routes.py::test_get_all_tickets_success PASSED               [ 16%]
tests/test_routes.py::test_get_all_tickets_when_empty PASSED            [ 33%]
tests/test_routes.py::test_create_ticket_success PASSED                 [ 50%]
tests/test_routes.py::test_buy_ticket_success PASSED                    [ 66%]
tests/test_routes.py::test_buy_ticket_when_ticket_not_found PASSED      [ 83%]
tests/test_routes.py::test_buy_ticket_when_already_sold PASSED          [100%]

============================================= 6 passed in 12.31s =============================================
```

Although all the tests are very simple, it took an average of more than two seconds for each one of them to execute. This happens because for each test, a new PostgreSQL Docker instance is being created, as shown in [Tests workflow](#tests-workflow).

To make the tests faster, one option is to create just one PostgreSQL Docker instance and use it for all the tests by configuring the `@pytest.fixture(scope='')`.

## The pytest fixture scope

Fixtures requiring network access depend on connectivity and are usually time-expensive to create. By setting the `scope` in `@pytest.fixture`, we can tell pytest how to manage the fixture's creation and reuse.

Fixtures are created when first requested by a test and are destroyed based on their `scope`. Some of the scope options that can be set are:

- `function`: the default scope, the fixture is destroyed at the end of the test.
- `class`: the fixture is destroyed during the teardown of the last test in the class.
- `module`: the fixture is destroyed during the teardown of the last test in the module.
- `package`: the fixture is destroyed during the teardown of the last test in the package.
- `session`: the fixture is destroyed at the end of the test session.

As we want to create just one Docker instance and reuse it for all the tests, we changed the `@pytest.fixture` in the `conftest.py` file in the following highlighted lines.

```py title="conftest.py" linenums="25" hl_lines="1 6"
@pytest.fixture(scope='session')
def anyio_backend():
    return 'asyncio'


@pytest.fixture(scope='session')
def postgres_container(anyio_backend):
    with PostgresContainer('postgres:16', driver='asyncpg') as postgres:
        yield postgres
```

Now, every time we run the tests, we will follow a workflow similar to the one below, where the `postgres_container` fixture is created only once at the beginning of the test session and is reused in all other fixtures. The `async_session` and `async_client` fixtures are still created and destroyed for each test. The `postgres_container` fixture is destroyed only after all the tests have finished.

```mermaid
flowchart LR
    %% Nodes for fixtures
    postgres_container["postgres_container"]
    async_session["async_session"]
    async_client["async_client"]
    test["Test 1"]
    async_session_2["async_session"]
    async_client_2["async_client"]
    test_2["Test 2"]
    async_session_n["async_session"]
    async_client_n["async_client"]
    test_n["Test N"]

    subgraph All fixtures
        direction LR

        subgraph Function fixtures
            direction LR
            async_session --> async_client
            async_session_2 --> async_client_2
            async_session_n --> async_client_n
        end

        subgraph Session Fixture
            direction LR
            postgres_container --> async_session
            postgres_container --> async_session_2
            postgres_container --> async_session_n
        end
    end

    %% Arrows from async_client to test blocks
    async_client --> test
    async_session --> test

    async_client_2 --> test_2
    async_session_2 --> test_2
    async_client_n --> test_n
    async_session_n --> test_n


    %% Style the nodes with rounded corners
    classDef fixtureStyle rx:10, ry:10;

    %% Style the nodes
    class postgres_container,async_session,async_client,test fixtureStyle;
    class async_session_2,async_client_2,test_2 fixtureStyle;
    class async_session_n,async_client_n,test_n fixtureStyle;
```

Running the tests again, we should observe that the total time to run all tests decreases to around 4 seconds, with a median of less than one second per test.

```
tests/test_routes.py::test_get_all_tickets_success PASSED               [ 16%]
tests/test_routes.py::test_get_all_tickets_when_empty PASSED            [ 33%]
tests/test_routes.py::test_create_ticket_success PASSED                 [ 50%]
tests/test_routes.py::test_buy_ticket_success PASSED                    [ 66%]
tests/test_routes.py::test_buy_ticket_when_ticket_not_found PASSED      [ 83%]
tests/test_routes.py::test_buy_ticket_when_already_sold PASSED          [100%]

============================================= 6 passed in 3.94s =============================================
```

??? note "Documentation reference links"

    - [Scope: sharing fixtures across classes, modules, packages or session](https://docs.pytest.org/en/6.2.x/fixture.html#scope-sharing-fixtures-across-classes-modules-packages-or-session)
    - [API reference](https://docs.pytest.org/en/stable/reference/reference.html#pytest.fixture)
    - [Higher-scoped fixtures are executed first](https://docs.pytest.org/en/stable/reference/fixtures.html#higher-scoped-fixtures-are-executed-first)

## Final version of test fixtures

The final `conftest.py` is presented below:

```py title="tests/conftest.py" linenums="1"
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from src.app import app
from src.database import get_session
from src.models import table_register


@pytest.fixture(scope='session')
def anyio_backend():
    return 'asyncio'


@pytest.fixture(scope='session')
def postgres_container(anyio_backend):
    with PostgresContainer('postgres:16', driver='asyncpg') as postgres:
        yield postgres


@pytest.fixture
async def async_session(postgres_container: PostgresContainer):
    async_db_url = postgres_container.get_connection_url()
    async_engine = create_async_engine(async_db_url, pool_pre_ping=True)

    async with async_engine.begin() as conn:
        await conn.run_sync(table_register.metadata.drop_all)
        await conn.run_sync(table_register.metadata.create_all)

    async_session = async_sessionmaker(
        autoflush=False,
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session

    await async_engine.dispose()


@pytest.fixture
async def async_client(async_session: async_sessionmaker[AsyncSession]):
    app.dependency_overrides[get_session] = lambda: async_session
    _transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=_transport, base_url='http://test', follow_redirects=True
    ) as client:
        yield client

    app.dependency_overrides.clear()

```
