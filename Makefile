.PHONY: help setup setup-dev sync validate clean test lint sync-debug validate-all status

# Default target
help:
	@echo "Agent-Matrix Catalog - Manual Sync & Validation"
	@echo ""
	@echo "Available targets:"
	@echo "  make setup          - Install dependencies (tries git, fallback to PyPI)"
	@echo "  make setup-dev      - Clone mcp_ingest repo for development"
	@echo "  make sync           - Run full sync from modelcontextprotocol/servers"
	@echo "  make sync-debug     - Run sync with verbose logging to logs/sync.log"
	@echo "  make validate       - Run all validators (structure, schema, index)"
	@echo "  make validate-all   - Run validators + linting"
	@echo "  make lint           - Run ruff linting on scripts"
	@echo "  make test           - Run sync + validate (full test cycle)"
	@echo "  make status         - Show current catalog status"
	@echo "  make clean          - Clean temporary files and logs"
	@echo ""

# Install dependencies
setup:
	@echo "Installing dependencies..."
	python -m pip install --upgrade pip
	pip install jsonschema ruff
	@echo ""
	@echo "Installing mcp_ingest (trying git first, fallback to PyPI)..."
	@if [ -d "../mcp_ingest" ]; then \
		echo "  → Found local mcp_ingest repository at ../mcp_ingest"; \
		pip install -e ../mcp_ingest && echo "  ✓ Installed from local git checkout" || \
		(echo "  ✗ Local install failed, falling back to PyPI..." && pip install mcp-ingest); \
	elif [ -d ".tmp/mcp_ingest" ]; then \
		echo "  → Found mcp_ingest at .tmp/mcp_ingest"; \
		pip install -e .tmp/mcp_ingest && echo "  ✓ Installed from .tmp checkout" || \
		(echo "  ✗ .tmp install failed, falling back to PyPI..." && pip install mcp-ingest); \
	else \
		echo "  → No local checkout found, using PyPI"; \
		pip install mcp-ingest; \
	fi
	@echo ""
	@python -c "import mcp_ingest; print(f'✓ mcp_ingest installed: {mcp_ingest.__file__}')" || echo "✗ mcp_ingest installation verification failed"
	@echo ""
	@echo "✓ All dependencies installed"

# Clone mcp_ingest for development
setup-dev:
	@echo "Setting up development environment..."
	@if [ ! -d ".tmp/mcp_ingest" ]; then \
		echo "Cloning agent-matrix/mcp_ingest..."; \
		mkdir -p .tmp; \
		git clone https://github.com/agent-matrix/mcp_ingest.git .tmp/mcp_ingest || \
		(echo "✗ Git clone failed, will use PyPI instead" && exit 0); \
	fi
	@$(MAKE) setup
	@echo "✓ Development environment ready"

# Run sync (basic)
sync:
	@echo "Running catalog sync..."
	@mkdir -p logs
	python scripts/sync_mcp_servers.py \
		--source-repo "https://github.com/modelcontextprotocol/servers" \
		--catalog-root "." \
		--servers-dir "servers" \
		--index-file "index.json" \
		2>&1 | tee logs/sync-$$(date +%Y%m%d-%H%M%S).log
	@echo "✓ Sync completed - check logs/ for details"

# Run sync with verbose debug logging
sync-debug:
	@echo "Running sync with debug logging..."
	@mkdir -p logs
	@echo "=== Sync started at $$(date) ===" > logs/sync-debug.log
	@echo "Command: python scripts/sync_mcp_servers.py --source-repo https://github.com/modelcontextprotocol/servers --catalog-root . --servers-dir servers --index-file index.json" >> logs/sync-debug.log
	@echo "" >> logs/sync-debug.log
	python -u scripts/sync_mcp_servers.py \
		--source-repo "https://github.com/modelcontextprotocol/servers" \
		--catalog-root "." \
		--servers-dir "servers" \
		--index-file "index.json" \
		2>&1 | tee -a logs/sync-debug.log
	@echo "" >> logs/sync-debug.log
	@echo "=== Sync completed at $$(date) ===" >> logs/sync-debug.log
	@echo "✓ Debug log saved to logs/sync-debug.log"

# Run all validators
validate:
	@echo "Running structure validation..."
	python scripts/validate_catalog_structure.py
	@echo ""
	@echo "Running schema validation..."
	python scripts/validate_catalog_schemas.py
	@echo ""
	@echo "Running index integrity validation..."
	python scripts/validate_catalog_index.py
	@echo ""
	@echo "✓ All validations passed"

# Run validators + linting
validate-all: validate lint

# Run linting
lint:
	@echo "Running ruff linting on scripts..."
	ruff check scripts
	@echo "✓ Linting passed"

# Full test cycle: sync + validate
test: sync validate
	@echo "✓ Full test cycle completed successfully"

# Clean temporary files
clean:
	@echo "Cleaning temporary files..."
	rm -rf .tmp/
	rm -rf logs/*.log
	rm -rf __pycache__/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Cleaned"

# Quick status check
status:
	@echo "Catalog Status:"
	@echo "==============="
	@if [ -f index.json ]; then \
		echo "Top-level index: ✓ exists"; \
		echo "Active manifests: $$(jq '.counts.active_manifests // 0' index.json)"; \
		echo "Total items: $$(jq '.counts.total_items // 0' index.json)"; \
		echo "Last generated: $$(jq -r '.generated_at // "unknown"' index.json)"; \
	else \
		echo "Top-level index: ✗ missing (run 'make sync')"; \
	fi
	@echo ""
	@echo "Server groups:"
	@if [ -d servers ]; then \
		ls -1 servers/ | head -10; \
		COUNT=$$(ls -1 servers/ | wc -l); \
		if [ $$COUNT -gt 10 ]; then echo "... and $$(($$COUNT - 10)) more"; fi; \
	else \
		echo "  (none - run 'make sync')"; \
	fi
