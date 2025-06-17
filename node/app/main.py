import os
import time
import random
import asyncio
import logging
import socket

import httpx
import uvicorn
from fastapi import FastAPI, Request
from prometheus_client import start_http_server

from algorithms import (
    singlecast,
    multicast,
    broadcast,
    gossip_push,
    gossip_pushpull,
    get_all_peers,
)

# -----------------------------------------------------------------------------
# ПАРАМЕТРЫ
# -----------------------------------------------------------------------------
NODE_COUNT = int(os.getenv("NODE_COUNT", "100"))
ORDINARY_EXPECTED = NODE_COUNT - 1
ALGORITHM_DEFAULT = os.getenv("ALGORITHM", "broadcast")
DEBUG = os.getenv("DEBUG", "0") == "1"
SERVICE_NAME = os.getenv("SERVICE_NAME", "node")
IS_SEED = os.getenv("IS_SEED", "0") == "1"
CONTROLLER_URL = os.getenv("CONTROLLER_URL", "http://controller:8000")
SEED_CLUSTER_TIMEOUT = float(os.getenv("SEED_CLUSTER_TIMEOUT", "120"))
ROUND_PAUSE = float(os.getenv("ROUND_PAUSE", "0.3"))
FAIL_PROB = float(os.getenv("FAIL_PROB", "0.0"))

# -----------------------------------------------------------------------------
# ЛОГИРОВАНИЕ
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("node")

# -----------------------------------------------------------------------------
# FASTAPI
# -----------------------------------------------------------------------------
app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


has_msg = False
start_ts = None
recv_ts = None
RUN_ID = -1
current_algorithm = ALGORITHM_DEFAULT
algo_map = {
    "singlecast": singlecast,
    "multicast": multicast,
    "broadcast": broadcast,
    "gossip_push": gossip_push,
    "gossip_pushpull": gossip_pushpull,
}
algo_fn = algo_map[current_algorithm]

log.info("Using algorithm: %s", current_algorithm)


async def spread(payload: dict):
    peers = get_all_peers(SERVICE_NAME)
    log.debug("spreading via %s to %d peers", current_algorithm, len(peers))
    await algo_fn(None, peers, payload)


@app.on_event("startup")
async def on_startup():
    start_http_server(8001)
    log.info("Node up: seed=%s", IS_SEED)


@app.post("/message")
async def receive(req: Request):
    global has_msg, recv_ts, start_ts, RUN_ID, current_algorithm, algo_fn
    payload = await req.json()
    run_id = payload.get("run_id", 0)
    algorithm = payload.get("algorithm", current_algorithm)

    if run_id != RUN_ID:
        RUN_ID = run_id
        has_msg = False
        start_ts = None
        recv_ts = None
        current_algorithm = algorithm
        algo_fn = algo_map[current_algorithm]
        log.info("New run %s using %s", RUN_ID, current_algorithm)

    if not has_msg:
        has_msg = True
        recv_ts = time.time()
        if start_ts is None:
            start_ts = recv_ts
        log.debug("received msg from %s", payload.get("origin"))
        asyncio.create_task(spread(payload))

        report = {
            "node": os.getenv("HOSTNAME", "unknown"),
            "algorithm": current_algorithm,
            "run_id": RUN_ID,
            "start_time": float(start_ts),
            "receive_time": float(recv_ts),
        }
        async with httpx.AsyncClient() as client:
            for attempt in range(5):
                try:
                    await client.post(
                        f"{CONTROLLER_URL}/report",
                        json=report,
                        timeout=5,
                    )
                    break
                except httpx.HTTPError as exc:
                    log.warning("report attempt %d failed: %s", attempt + 1, exc)
                    await asyncio.sleep(0.2)
        if random.random() < FAIL_PROB:
            log.warning("Node failing after first message")
            os._exit(1)
    return {"status": "ok"}


@app.post("/pull")
async def pull(req: Request):
    return await receive(req)


def main():
    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="error")


if __name__ == "__main__":
    main()
