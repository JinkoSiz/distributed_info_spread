import asyncio
import random
import os
import logging
import socket

import httpx

# -----------------------------------------------------------------------------
# ПАРАМЕТРЫ НАДЁЖНОСТИ
# -----------------------------------------------------------------------------
LOSS_PROB = float(os.getenv("LOSS_PROB", "0.0"))
FAIL_PROB = float(os.getenv("FAIL_PROB", "0.0"))
FANOUT = int(os.getenv("FANOUT", "5"))
ROUNDS_BROADCAST = int(os.getenv("ROUNDS_BROADCAST", "3"))
ROUNDS_FANOUT = int(os.getenv("ROUNDS_FANOUT", "4"))
PAUSE_SEC = float(os.getenv("ROUND_PAUSE", "0.3"))

log = logging.getLogger("node.algos")


def get_all_peers(service: str) -> list[str]:
    addrs = {
        info[4][0]
        for info in socket.getaddrinfo(service, 5000, proto=socket.IPPROTO_TCP)
    }
    return [f"http://{ip}:5000/message" for ip in sorted(addrs)]


# -----------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНАЯ ОТПРАВКА
# -----------------------------------------------------------------------------
async def unreliable_send(client: httpx.AsyncClient, url: str, payload: dict):
    if random.random() < LOSS_PROB:
        log.debug("DROP to %s", url)
        return
    try:
        await client.post(url, json=payload, timeout=5)
        log.debug("sent to %s", url)
    except Exception as exc:
        log.debug("ERR to %s: %s", url, exc)


# -----------------------------------------------------------------------------
# АЛГОРИТМЫ
# -----------------------------------------------------------------------------
async def singlecast(node, peers, payload):
    async with httpx.AsyncClient() as client:
        target = random.choice(peers)
        log.debug("singlecast to %s", target)
        await unreliable_send(client, target, payload)


async def multicast(node, peers, payload):
    async with httpx.AsyncClient() as client:
        for r in range(ROUNDS_FANOUT):
            current = random.sample(peers, min(FANOUT, len(peers)))
            log.debug("multicast round %d/%d to %d peers", r + 1, ROUNDS_FANOUT, len(current))
            for url in current:
                await unreliable_send(client, url, payload)
            await asyncio.sleep(PAUSE_SEC)


async def broadcast(node, peers, payload):
    async with httpx.AsyncClient() as client:
        for r in range(ROUNDS_BROADCAST):
            current = get_all_peers(os.getenv("SERVICE_NAME", "node"))
            log.debug("broadcast round %d/%d to %d peers", r + 1, ROUNDS_BROADCAST, len(current))
            for url in current:
                await unreliable_send(client, url, payload)
            await asyncio.sleep(PAUSE_SEC)


async def gossip_push(node, peers, payload):
    async with httpx.AsyncClient() as client:
        for r in range(ROUNDS_FANOUT):
            target = random.choice(peers)
            log.debug("gossip_push round %d/%d to %s", r + 1, ROUNDS_FANOUT, target)
            await unreliable_send(client, target, payload)
            await asyncio.sleep(PAUSE_SEC)


async def gossip_pushpull(node, peers, payload):
    async with httpx.AsyncClient() as client:
        for r in range(ROUNDS_FANOUT):
            peer = random.choice(peers)
            log.debug(
                "gossip_pushpull round %d/%d with %s", r + 1, ROUNDS_FANOUT, peer
            )
            base = peer.rsplit("/", 1)[0]
            await unreliable_send(client, peer, payload)
            await unreliable_send(client, f"{base}/pull", payload)
            await asyncio.sleep(PAUSE_SEC)
