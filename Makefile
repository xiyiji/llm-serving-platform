.PHONY: dev-backend dev-frontend test bench up down

dev-backend:
	cd backend && uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest -q

bench:
	python bench/benchmark.py --requests 200 --concurrency 16

up:
	docker compose up --build -d

down:
	docker compose down
