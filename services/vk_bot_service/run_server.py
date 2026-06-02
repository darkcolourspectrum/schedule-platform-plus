#!/usr/bin/env python3
"""Запуск VK Bot Service."""
import uvicorn

from app.config import settings


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" if settings.debug else "warning",
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
