"""ASGI entry point for the payment webhook service."""

from app.webhook import app

__all__ = ["app"]
