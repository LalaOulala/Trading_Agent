from __future__ import annotations

import logging
from pathlib import Path

from bot.config import BotConfig
from bot.discord_bot import run_bot
from bot.keep_alive import start_background_server


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    _configure_logging()
    logger = logging.getLogger(__name__)

    repo_root = Path(__file__).resolve().parents[1]
    config = BotConfig.from_env(repo_root=repo_root)

    if config.enable_keep_alive:
        start_background_server(host=config.keep_alive_host, port=config.keep_alive_port)
        logger.info(
            "Keep-alive Flask démarré sur http://%s:%s",
            config.keep_alive_host,
            config.keep_alive_port,
        )

    run_bot(config)


if __name__ == "__main__":
    main()
