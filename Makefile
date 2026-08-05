LOCALES := clashogram/locales
POT := $(LOCALES)/messages.pot
VERSION = $(shell uv run python -c 'import clashogram; print(clashogram.__version__)')
IMAGE ?= mehdisadeghi/clashogram
HOST ?= mail
CONTAINER ?= clashogram
HOST_DATA ?= /home/mx/apps/clashogramvolume
HOST_ENV ?= /home/mx/apps/clashogram/docker_env

# The live container was created without a restart policy, which is why it
# does not come back after a host reboot.
RUN_ARGS = --name $(CONTAINER) --restart=always --env-file=$(HOST_ENV) \
	   -v $(HOST_DATA):/data $(IMAGE):latest --warlog /data/warlog.db

.PHONY: help lint test verify build clean run dryrun i18n docker deploy

help:
	@grep -E '^[a-z0-9]+:' Makefile | cut -d: -f1

lint:
	uvx ruff check .

test:
	uv run --extra test pytest

verify: lint test

build:
	uv build

clean:
	rm -rf dist build *.egg-info .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} +

# Reads COC_API_TOKEN, COC_CLAN_TAG, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
run:
	uv run clashogram

dryrun:
	uv run clashogram --dryrun --loglevel DEBUG

i18n:
	uv run --extra i18n pybabel extract clashogram/ -o $(POT) \
		--project Clashogram --version $(VERSION)
	uv run --extra i18n pybabel update -i $(POT) -d $(LOCALES)
	uv run --extra i18n pybabel compile -d $(LOCALES)

docker:
	docker build -t $(IMAGE):$(VERSION) -t $(IMAGE):latest .

deploy: docker
	docker push $(IMAGE):$(VERSION)
	docker push $(IMAGE):latest
	ssh $(HOST) 'docker pull $(IMAGE):latest && docker rm -f $(CONTAINER); docker run -d $(RUN_ARGS)'
