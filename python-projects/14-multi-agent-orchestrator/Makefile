.PHONY: help build up down restart logs shell db-shell redis-shell clean test

help:
	@echo "Multi-Agent Task Orchestrator - Docker Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make build        - Build Docker images"
	@echo "  make up           - Start all services"
	@echo "  make down         - Stop all services"
	@echo "  make restart      - Restart all services"
	@echo "  make logs         - View logs from all services"
	@echo "  make shell        - Open shell in app container"
	@echo "  make db-shell     - Open PostgreSQL shell"
	@echo "  make redis-shell  - Open Redis CLI"
	@echo "  make clean        - Remove all containers and volumes"
	@echo "  make test         - Run tests"

build:
	docker-compose build

up:
	docker-compose up -d
	@echo "Services started successfully!"
	@echo "API: http://localhost:8001"
	@echo "PostgreSQL: localhost:5432"
	@echo "Redis: localhost:6379"

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

shell:
	docker-compose exec app /bin/bash

db-shell:
	docker-compose exec postgres psql -U postgres -d multi_agent_orchestrator

redis-shell:
	docker-compose exec redis redis-cli

clean:
	docker-compose down -v
	@echo "All containers and volumes removed"

test:
	docker-compose exec app pytest tests/ -v

init-db:
	docker-compose exec app python scripts/init_db.py

seed-data:
	docker-compose exec app python scripts/seed_sample_data.py
