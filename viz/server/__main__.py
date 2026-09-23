"""Run the server: `python -m viz.server` or `viz-server`."""
import uvicorn

from ..config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run("viz.server.app:create_app", factory=True, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
