# SPDX-License-Identifier: GPL-2.0-only

import uvicorn


def main() -> None:
    uvicorn.run(
        "esp32_s3_simulator.api:app",
        host="127.0.0.1",
        port=8765,
        proxy_headers=False,
    )
