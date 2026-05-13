CONTAINER_ENGINE ?= podman

PYTHON_BASE_IMAGE ?= python-base
PYTHON_BASE_CONTEXT ?= ../..
PYTHON_BASE_DOCKERFILE ?= infra/docker/python-base.Dockerfile

BACKEND_DOCKERFILE ?= backend.Dockerfile
PIP_CONFIG_SECRET_ID ?= pip_config
PIP_CONFIG_SECRET_SRC ?= $(HOME)/.config/pip/pip.conf
PIP_CONFIG_SECRET_ARG ?= --secret id=$(PIP_CONFIG_SECRET_ID),src=$(PIP_CONFIG_SECRET_SRC)

AG_UI_GATEWAY_IMAGE ?= magnum-opus-agui-agent-gateway:dev
AGENT_SERVICE_IMAGE ?= magnum-opus-agui-agent-service:dev

.PHONY: podman-build-python-base
podman-build-python-base:
	$(CONTAINER_ENGINE) build \
		-f $(PYTHON_BASE_DOCKERFILE) \
		-t $(PYTHON_BASE_IMAGE) \
		$(PYTHON_BASE_CONTEXT)

.PHONY: podman-build-ag-ui-gateway
podman-build-ag-ui-gateway:
	$(CONTAINER_ENGINE) build \
		$(PIP_CONFIG_SECRET_ARG) \
		--build-arg SERVICE_PATH=ag_ui_gateway \
		--build-arg SERVICE_MODULE=gateway_app.app \
		--build-arg SERVICE_PORT=8088 \
		-f $(BACKEND_DOCKERFILE) \
		-t $(AG_UI_GATEWAY_IMAGE) \
		.

.PHONY: podman-build-agent-service
podman-build-agent-service:
	$(CONTAINER_ENGINE) build \
		$(PIP_CONFIG_SECRET_ARG) \
		--build-arg SERVICE_PATH=agent_service \
		--build-arg SERVICE_MODULE=adk_agent_service.app \
		--build-arg SERVICE_PORT=8090 \
		-f $(BACKEND_DOCKERFILE) \
		-t $(AGENT_SERVICE_IMAGE) \
		.

.PHONY: podman-build-backends
podman-build-backends: podman-build-ag-ui-gateway podman-build-agent-service

.PHONY: podman-compose-up
podman-compose-up: podman-build-backends
	AG_UI_GATEWAY_IMAGE=$(AG_UI_GATEWAY_IMAGE) \
	AGENT_SERVICE_IMAGE=$(AGENT_SERVICE_IMAGE) \
	$(CONTAINER_ENGINE) compose up --no-build
