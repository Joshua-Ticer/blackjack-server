"""FastAPI application factory."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Blackjack Server")

    # TODO: app.include_router(...) for api/routes/* and api/ws/gateway
    # TODO: startup hook -- run Base.metadata.create_all() against the async engine
    #       (see app/db/base.py, app/db/session.py) so tables exist on boot
    # TODO: startup/shutdown hooks for Redis client, TableManager

    return app


app = create_app()
