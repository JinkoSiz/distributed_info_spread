import os
import json
import asyncio
import logging
from fastapi import FastAPI, Request
import uvicorn
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    push_to_gateway,
    start_http_server,
)

app = FastAPI()
log = logging.getLogger("controller")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Сколько обычных нод ожидаем:
NODE_COUNT = int(os.getenv("NODE_COUNT", "100"))
EXPECTED = int(os.getenv("EXPECTED", str(NODE_COUNT - 1)))

# Куда сохранять результаты:
RESULTS_DIR = os.getenv("RESULTS_DIR", "/app/results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Хранилище приходящих отчётов:
reports_by_run: dict[int, dict[str, dict]] = {}


@app.post("/report")
async def report(req: Request):
    data = await req.json()
    node = data.get("node", "unknown")
    run_id = int(data.get("run_id", 0))
    run_reports = reports_by_run.setdefault(run_id, {})

    if node not in run_reports:
        run_reports[node] = data
        fn = os.path.join(RESULTS_DIR, f"experiment_{run_id}_{node}.json")
        with open(fn, "w") as f:
            json.dump(data, f)
        log.info("✏️  Saved report for run %s node %s → %s", run_id, node, fn)

        # push metric
        reg = CollectorRegistry()
        g = Gauge(
            "receive_delay_seconds",
            "Delay between start and receive",
            ["node", "algorithm", "run"],
            registry=reg,
        )
        delay = data.get("receive_time", 0) - data.get("start_time", 0)
        g.labels(node=node, algorithm=data.get("algorithm", "?"), run=str(run_id)).set(delay)
        push_to_gateway("pushgateway:9091", job="info_spread", registry=reg)

    if len(run_reports) >= EXPECTED:
        open(os.path.join(RESULTS_DIR, f"done_{run_id}"), "w").close()
        log.info("Run %s finished", run_id)
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "up"}


if __name__ == "__main__":
    start_http_server(8001)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
