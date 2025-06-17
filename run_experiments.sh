#!/usr/bin/env bash
set -euo pipefail

# -----------------------
#   Параметры эксперимента
# -----------------------
NODE_COUNT=101       # 1 seed + 100 обычных узлов
ORDINARY=$((NODE_COUNT-1))
EXPECTED=$ORDINARY
REPEATS=5
ALGORITHMS=(singlecast multicast broadcast gossip_push gossip_pushpull)

# Надёжность / фан-аут / проч.
LOSS_PROB=0.05
FAIL_PROB=0.02
FANOUT=5
ROUNDS_BROADCAST=3
ROUNDS_FANOUT=4
ROUND_PAUSE=0.3
TIMEOUT_SEC=120
SEED_CLUSTER_TIMEOUT=120
DEBUG=0

CONTROLLER_URL="http://controller:8000"

# -----------------------
#   Генерируем .env и запускаем контейнеры
# -----------------------
cat > .env <<EOF
NODE_COUNT=${NODE_COUNT}
EXPECTED=${EXPECTED}
LOSS_PROB=${LOSS_PROB}
FAIL_PROB=${FAIL_PROB}
FANOUT=${FANOUT}
ROUNDS_BROADCAST=${ROUNDS_BROADCAST}
ROUNDS_FANOUT=${ROUNDS_FANOUT}
ROUND_PAUSE=${ROUND_PAUSE}
TIMEOUT_SEC=${TIMEOUT_SEC}
DEBUG=${DEBUG}
CONTROLLER_URL=${CONTROLLER_URL}
SEED_CLUSTER_TIMEOUT=${SEED_CLUSTER_TIMEOUT}
ALGORITHM=unused
EOF

docker compose up -d --build --scale node=$ORDINARY
sleep 5

RUN_ID=1
for ALG in "${ALGORITHMS[@]}"; do
  for RUN in $(seq 1 $REPEATS); do
    echo ">>> $ALG  run $RUN/$REPEATS"
    docker compose exec -T \
      -e ALG=$ALG -e RUN_ID=$RUN_ID seed \
      python - <<'PY'
import os, httpx
payload = {"msg":"hello","origin":"seed","algorithm":os.environ['ALG'],"run_id":int(os.environ['RUN_ID'])}
httpx.post("http://localhost:5000/message", json=payload)
PY

    while [ ! -f results/done_${RUN_ID} ]; do sleep 2; done
    mkdir -p archive/$ALG
    mv results/experiment_${RUN_ID}_*.json archive/$ALG/ 2>/dev/null || true
    rm -f results/done_${RUN_ID}
    RUN_ID=$((RUN_ID+1))
    docker compose restart seed node >/dev/null
  done
done

docker compose down -v --remove-orphans
echo "✅ All done — see ./archive/"
