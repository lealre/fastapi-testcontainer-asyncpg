# Testcontainers with FastAPI and asyncpg

This repository is a simple example application of how to test asynchronous FastAPI routes using a Docker instance of PostgreSQL with `asyncpg` as the database driver. It is done by using [testcontainers-python](https://github.com/testcontainers/testcontainers-python).

You can check a more detailed text about the repository [here](https://lealre.github.io/fastapi-testcontainer-asyncpg/).

## How to run this project

This repo was created using [uv](https://docs.astral.sh/uv/) and uses Python version 3.12.3.

[How to install uv](https://docs.astral.sh/uv/getting-started/installation/).

1. Clone the repo locally and access the project folder:

    ```bash
    git clone https://github.com/lealre/fastapi-testcontainer-asyncpg.git
    cd fastapi-testcontainer-asyncpg
    ```

2. Run the command to serve the API on port 8000. It will automatically create and activate the virtual environment:

    ```bash
    uv run -m fastapi dev src/app.py
    ```

    To test the endpoint, access `http://localhost:8000/docs`.

3. Run the tests:

    ```bash
    uv run pytest -vv
    ```
