SHELL := /bin/sh

REQUIRED_TOOLS := docker kind kubectl uv
TASKS_API_DIR  := services/tasks_api
MCP_SERVER_DIR := services/mcp_server

.DEFAULT_GOAL := help
.PHONY: help check install test deploy destroy

help:
	@echo "Targets:"
	@echo "  check    Verify required tools are installed (docker, kind, kubectl, uv)"
	@echo "  install  Sync Python dependencies for both services via uv"
	@echo "  test     Run unit tests for both services"
	@echo "  deploy   Bootstrap Kind cluster, build images, apply manifests"
	@echo "  destroy  Delete the Kind cluster and all PoC resources"

check:
	@missing=""; \
	for tool in $(REQUIRED_TOOLS); do \
		if ! command -v $$tool >/dev/null 2>&1; then \
			missing="$$missing $$tool"; \
		fi; \
	done; \
	if [ -n "$$missing" ]; then \
		echo "Missing required tools:$$missing" >&2; \
		echo "See README.md > Prerequisites for install links." >&2; \
		exit 1; \
	fi; \
	echo "All required tools are installed."

install:
	cd $(TASKS_API_DIR)  && uv sync --extra dev
	cd $(MCP_SERVER_DIR) && uv sync --extra dev

test:
	cd $(TASKS_API_DIR)  && uv run --extra dev pytest -q
	cd $(MCP_SERVER_DIR) && uv run --extra dev pytest -q

deploy:
	sh scripts/setup.sh

destroy:
	sh scripts/teardown.sh
