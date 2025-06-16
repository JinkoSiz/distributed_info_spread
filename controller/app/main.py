import os
import json
import asyncio
import logging
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()
log = logging.getLogger("controller")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Сколько обычных нод ожидаем:
NODE_COUNT = int(os.getenv("NODE_COUNT", "100"))
EXPECTED = NODE_COUNT - 1

# Куда сохранять результаты:
RESULTS_DIR = os.getenv("RESULTS_DIR", "/app/results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Хранилище приходящих отчётов:
reports = {}
shutdown_event = asyncio.Event()


@app.post("/report")
async def report(req: Request):
    data = await req.json()
    node = data.get("node", f"unknown-{len(reports)}")
    if node not in reports:
        reports[node] = data
        fn = os.path.join(RESULTS_DIR, f"experiment_{node}.json")
        with open(fn, "w") as f:
            json.dump(data, f)
        log.info("✏️  Saved report for %s → %s", node, fn)
    # Когда все отчёты собраны — ставим ивент на завершение
    if len(reports) >= EXPECTED:
        shutdown_event.set()
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "up"}


if __name__ == "__main__":
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    # Запускаем сервер и ждём shutdown_event
    loop = asyncio.get_event_loop()
    loop.create_task(server.serve())
    loop.run_until_complete(shutdown_event.wait())
    # Даём Uvicorn завершиться
    server.should_exit = True
