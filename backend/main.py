from __future__ import annotations

import uvicorn

from backend.api.app import app


def run() -> None:
    uvicorn.run(app, host="127.0.0.1", port=3000)


if __name__ == "__main__":
    run()
