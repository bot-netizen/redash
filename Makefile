.PHONY: compose_build up test_db create_database clean down tests lint backend-unit-tests stream-tests frontend-unit-tests test build watch start redis-cli bash

compose_build: .env
	COMPOSE_DOCKER_CLI_BUILD=1 DOCKER_BUILDKIT=1 docker compose build

up:
	docker compose up -d redis postgres --remove-orphans
	docker compose exec -u postgres postgres psql postgres --csv \
		-1tqc "SELECT table_name FROM information_schema.tables WHERE table_name = 'organizations'" 2> /dev/null \
		| grep -q "organizations" || make create_database
	COMPOSE_DOCKER_CLI_BUILD=1 DOCKER_BUILDKIT=1 docker compose up -d --build --remove-orphans

test_db:
	@for i in `seq 1 5`; do \
		if (docker compose exec postgres sh -c 'psql -U postgres -c "select 1;"' 2>&1 > /dev/null) then break; \
		else echo "postgres initializing..."; sleep 5; fi \
	done
	docker compose exec postgres sh -c 'psql -U postgres -c "drop database if exists tests;" && psql -U postgres -c "create database tests;"'

create_database: .env
	docker compose run server create_db

clean:
	docker compose down
	docker compose --project-name cypress down
	docker compose rm --stop --force
	docker compose --project-name cypress rm --stop --force
	docker image rm --force \
		cypress-server:latest cypress-worker:latest cypress-scheduler:latest \
		sqldesk-server:latest sqldesk-worker:latest sqldesk-scheduler:latest
	docker container prune --force
	docker image prune --force
	docker volume prune --force

down:
	docker compose down

.env:
	printf "SQLDESK_COOKIE_SECRET=`pwgen -1s 32`\nSQLDESK_SECRET_KEY=`pwgen -1s 32`\n" >> .env

env: .env

format:
	pre-commit run --all-files

tests:
	docker compose run server tests

lint:
	ruff check .
	black --check . --diff

backend-unit-tests: up test_db
	docker compose run --rm --name tests server tests

# The stream tests that need a real broker. Everything else about streams is
# driven by a fake that returns bytes; what this covers is whether librdkafka
# behaves as `sqldesk.streams.consumer.Broker` assumes -- above all that a
# consumer group which has run before still starts at the end of the topic,
# since `auto.offset.reset` does not apply once a group has an offset.
#
# Redpanda rather than Kafka: one process, no ZooKeeper, same protocol. The
# tests skip themselves (loudly) when no broker is running, so an ordinary
# `make backend-unit-tests` does not need one.
stream-tests: up test_db
	docker compose --profile streams up -d broker
	docker compose run --rm -e SQLDESK_DATABASE_URL=postgresql://postgres@postgres/tests server \
	  bash -c "pip install -q confluent-kafka==2.6.1 && pytest tests/streams -q"

frontend-unit-tests:
	CYPRESS_INSTALL_BINARY=0 PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=1 pnpm install --frozen-lockfile
	pnpm test

test: backend-unit-tests frontend-unit-tests lint

build:
	pnpm run build

watch:
	pnpm run watch

start:
	pnpm start

redis-cli:
	docker compose run --rm redis redis-cli -h redis

bash:
	docker compose run --rm server bash
