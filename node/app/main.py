import os
import time
import random
import asyncio
import logging
import socket

import httpx
import uvicorn
from fastapi import FastAPI, Request

from algorithms import (
    singlecast,
    multicast,
    broadcast,
    gossip_push,
    gossip_pushpull,
)

# -----------------------------------------------------------------------------
# ПАРАМЕТРЫ
# -----------------------------------------------------------------------------
NODE_COUNT = int(os.getenv("NODE_COUNT", "100"))
ORDINARY_EXPECTED = NODE_COUNT - 1
ALGORITHM = os.getenv("ALGORITHM", "broadcast")
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
# DNS-peer discovery
# -----------------------------------------------------------------------------
def get_all_peers(service: str) -> list[str]:
    addrs = {
        info[4][0]
        for info in socket.getaddrinfo(service, 5000, proto=socket.IPPROTO_TCP)
    }
    return [f"http://{ip}:5000/message" for ip in sorted(addrs)]


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

algo_fn = {
    "singlecast": singlecast,
    "multicast": multicast,
    "broadcast": broadcast,
    "gossip_push": gossip_push,
    "gossip_pushpull": gossip_pushpull,
}[ALGORITHM]


async def spread(payload: dict):
    peers = get_all_peers(SERVICE_NAME)
    log.debug("spreading via %s to %d peers", ALGORITHM, len(peers))
    await algo_fn(None, peers, payload)


@app.on_event("startup")
async def on_startup():
    global start_ts
    if IS_SEED:
        # 1) дождаться контроллера
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    await client.get(f"{CONTROLLER_URL}/health", timeout=2)
                    log.info("Controller is up")
                    break
                except Exception:
                    log.info("Waiting for controller…")
                    await asyncio.sleep(1)

        # 2) ждать появления нод по DNS, но не дольше SEED_CLUSTER_TIMEOUT
        start_wait = time.time()
        while True:
            peers = get_all_peers(SERVICE_NAME)
            count = len(peers)
            elapsed = time.time() - start_wait
            if count >= ORDINARY_EXPECTED:
                log.info(
                    "Cluster ready: %d/%d peers after %.1fs",
                    count, ORDINARY_EXPECTED, elapsed
                )
                break
            if elapsed > SEED_CLUSTER_TIMEOUT:
                log.warning(
                    "Timeout waiting for cluster: got %d/%d after %.1fs, proceeding anyway",
                    count, ORDINARY_EXPECTED, elapsed
                )
                break
            log.info(
                "Waiting for cluster: %d/%d (%.1fs elapsed)",
                count, ORDINARY_EXPECTED, elapsed
            )
            await asyncio.sleep(1)

        # короткая задержка, чтобы все HTTP-серверы поднялись
        await asyncio.sleep(ROUND_PAUSE)

        # запускаем рассылку
        start_ts = time.time()
        payload = {"msg": "hello", "origin": "seed"}
        log.info(
            "<< SEED >> start spread() to %d peers",
            len(get_all_peers(SERVICE_NAME))
        )
        await spread(payload)


@app.post("/message")
async def receive(req: Request):
    global has_msg, recv_ts
    payload = await req.json()
    if not has_msg:
        has_msg = True
        recv_ts = time.time()
        log.debug("received msg from %s", payload.get("origin"))
        # запустить спред асинхронно
        asyncio.create_task(spread(payload))

        # отчёт контроллеру
        report = {
            "node": os.getenv("HOSTNAME", "unknown"),
            "algorithm": ALGORITHM,
            "start_time": float(start_ts or recv_ts),
            "receive_time": float(recv_ts),
        }
        async with httpx.AsyncClient() as client:
            for attempt in range(5):
                try:
                    await client.post(
                        f"{CONTROLLER_URL}/report",
                        json=report,
                        timeout=5
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
