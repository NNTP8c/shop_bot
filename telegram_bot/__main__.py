"""Run the Telegram bot using long polling."""

import logging

from app.bot import run


if __name__ == "__main__":
    logging.getLogger(__name__).info("Starting Telegram bot process...")
    run()
