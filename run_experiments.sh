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
#   Генерируем .env
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
EOF

echo ".env:"
cat .env
echo

# -----------------------
#   Цикл экспериментов
# -----------------------
for ALG in "${ALGORITHMS[@]}"; do
  for RUN in $(seq 1 $REPEATS); do
    echo ">>> $ALG  run $RUN/$REPEATS"
    export ALGORITHM=$ALG

    # Сбрасываем старые
    docker compose down -v --remove-orphans

    # Запускаем — controller завершится сам, как только соберёт все отчёты
    docker compose up --build \
      --scale node=$ORDINARY \
      --exit-code-from controller

    # Переносим результаты
    mkdir -p archive/$ALG
    mv results/experiment_*.json archive/$ALG/ 2>/dev/null || true
    rm -rf results/*
  done
done

docker compose down -v --remove-orphans
echo "✅ All done — see ./archive/"
