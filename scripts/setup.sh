#!/usr/bin/env sh
# Bootstrap the entire PoC: cluster, images, deployments.

set -eu

CLUSTER_NAME="mcp-poc"
NAMESPACE="mcp-poc"
TASKS_IMAGE="localhost/mcp-poc/tasks-api:0.1.0"
MCP_IMAGE="localhost/mcp-poc/mcp-server:0.1.0"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required tool: $1" >&2
    exit 1
  }
}

require docker
require kind
require kubectl

echo "[1/5] Creating Kind cluster '${CLUSTER_NAME}'..."
if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  echo "      Cluster already exists, reusing."
else
  kind create cluster --name "${CLUSTER_NAME}" --config kind-config.yaml
fi

echo "[2/5] Building images..."
docker build -t "${TASKS_IMAGE}" services/tasks_api
docker build -t "${MCP_IMAGE}" services/mcp_server

echo "[3/5] Loading images into Kind..."
kind load docker-image "${TASKS_IMAGE}" --name "${CLUSTER_NAME}"
kind load docker-image "${MCP_IMAGE}" --name "${CLUSTER_NAME}"

echo "[4/5] Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/

echo "[5/5] Waiting for deployments to become ready..."
kubectl -n "${NAMESPACE}" rollout status deployment/tasks-api --timeout=120s
kubectl -n "${NAMESPACE}" rollout status deployment/mcp-server --timeout=120s
kubectl -n "${NAMESPACE}" rollout status deployment/ollama --timeout=600s

cat <<'EOF'

Ready.
  Tasks API : http://localhost:30080
  MCP server: http://localhost:30090/mcp
  Ollama    : http://localhost:30100  (run `make pull-model` to load weights)

Try the three integration paths:
  sh   examples/cli_demo.sh
  uv run --python 3.12 --with httpx python examples/direct_api.py
  uv run --python 3.12 --with mcp   python examples/mcp_client.py
EOF
