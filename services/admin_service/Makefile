# Admin Service Makefile
.PHONY: help install run test migrate clean

help:
	@echo "Admin Service Commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make run        - Run the service"
	@echo "  make test       - Run tests"
	@echo "  make migrate    - Create and apply migrations"
	@echo "  make clean      - Clean cache files"
	@echo "  make docker     - Build and run in Docker"

install:
	pip install -r requirements.txt

run:
	python run_server.py

test:
	pytest tests/ -v

migrate:
	alembic revision --autogenerate -m "$(m)"
	alembic upgrade head

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +

docker:
	docker build -t admin-service .
	docker run -p 8003:8003 --env-file .env admin-service
