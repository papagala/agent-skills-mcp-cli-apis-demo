SHELL := /bin/sh

REQUIRED_TOOLS := docker kind kubectl uv
TASKS_API_DIR  := services/tasks_api
MCP_SERVER_DIR := services/mcp_server
OLLAMA_MODEL   := qwen2.5:0.5b-instruct

.DEFAULT_GOAL := help
.PHONY: help check install test deploy destroy demo pull-model

help:
	@echo "Targets:"
	@echo "  check    Verify required tools are installed (docker, kind, kubectl, uv)"
	@echo "  install  Sync Python dependencies for both services via uv"
	@echo "  test     Run unit tests for both services"
	@echo "  deploy   Bootstrap Kind cluster, build images, apply manifests"
	@echo "  pull-model  Pull the Ollama model ($(OLLAMA_MODEL)) into the cluster"
	@echo "  demo     Launch the Streamlit comparison of Direct API, CLI, and MCP"
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

pull-model:
	@echo "Pulling $(OLLAMA_MODEL) into the in-cluster Ollama (this can take a few minutes)..."
	kubectl -n mcp-poc exec deploy/ollama -- ollama pull $(OLLAMA_MODEL)
	@echo "Model ready: $(OLLAMA_MODEL)"

demo:
	uv run --python 3.12 \
		--with streamlit==1.39.0 \
		--with httpx==0.27.2 \
		--with mcp==1.27.0 \
		--with plotly==5.24.1 \
		--with pandas==2.2.3 \
		streamlit run examples/streamlit_demo.py

destroy:
	sh scripts/teardown.sh
