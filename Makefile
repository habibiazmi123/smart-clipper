BE_DIR  := apps/engine
FE_DIR  := apps/desktop
BE_HOST := 127.0.0.1
BE_PORT := 8719

.PHONY: help be fe dev build install test lint clean stop

help:
	@echo "  be       - run backend (uvicorn :$(BE_PORT))"
	@echo "  fe       - run frontend (vite dev)"
	@echo "  dev      - run be + fe concurrently"
	@echo "  build    - build frontend (output to $(FE_DIR)/dist)"
	@echo "  install  - install be + fe deps"
	@echo "  test     - run backend tests"
	@echo "  lint     - lint frontend"
	@echo "  stop     - kill be on :$(BE_PORT) and vite"

be:
	cd $(BE_DIR) && uv run uvicorn app.main:app --host $(BE_HOST) --port $(BE_PORT) --reload

fe:
	cd $(FE_DIR) && npm run dev

dev:
	@trap 'kill 0' INT TERM; \
	cd $(BE_DIR) && uv run uvicorn app.main:app --host $(BE_HOST) --port $(BE_PORT) --reload & \
	cd $(FE_DIR) && npm run dev & \
	wait

build:
	cd $(FE_DIR) && npm run build

install:
	cd $(BE_DIR) && uv sync
	cd $(FE_DIR) && npm install

test:
	cd $(BE_DIR) && uv run pytest

lint:
	cd $(FE_DIR) && npm run lint

stop:
	-lsof -ti:$(BE_PORT) | xargs kill -9 2>/dev/null || true
	-lsof -ti:5173 | xargs kill -9 2>/dev/null || true
	-pkill -f "uvicorn app.main:app" 2>/dev/null || true
	@echo "stopped"
