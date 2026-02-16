from __future__ import annotations

from datetime import datetime, timezone
from threading import Thread

from flask import Flask, jsonify


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def health() -> tuple[object, int]:
        return (
            jsonify(
                {
                    "status": "ok",
                    "service": "discord-trading-bot",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                }
            ),
            200,
        )

    return app


def run_server(*, host: str, port: int) -> None:
    app = create_app()
    app.run(host=host, port=port, debug=False, use_reloader=False)


def start_background_server(*, host: str, port: int) -> Thread:
    thread = Thread(
        target=run_server,
        kwargs={"host": host, "port": port},
        daemon=True,
        name="keep-alive-server",
    )
    thread.start()
    return thread
