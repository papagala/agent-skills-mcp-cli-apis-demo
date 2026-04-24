#!/usr/bin/env sh
# Destroy everything created by setup.sh.

set -eu

CLUSTER_NAME="mcp-poc"

if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  kind delete cluster --name "${CLUSTER_NAME}"
  echo "Cluster '${CLUSTER_NAME}' deleted."
else
  echo "Cluster '${CLUSTER_NAME}' not found, nothing to do."
fi
