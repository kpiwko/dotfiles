# Makefile for dotfiles cluster management

SHELL := /bin/sh
PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest

.PHONY: all test test-binary cluster-create cluster-up cluster-status cluster-logs cluster-down cluster-delete

all: help

help:
	@echo "Dotfiles Cluster Management"
	@echo ""
	@echo "Commands:"
	@echo "  make test                       Run all pytest tests"
	@echo "  make test-binary BINARY=<name>  Run tests for one .local/bin executable"
	@echo "  make cluster-create             Create Kind cluster"
	@echo "  make cluster-up                 Deploy kustomize manifests"
	@echo "  make cluster-status             Show cluster status"
	@echo "  make cluster-logs               Show logs (use LOGS_POD=<pod>)"
	@echo "  make cluster-down               Stop cluster"
	@echo "  make cluster-delete             Delete cluster"
	@echo ""

test:
	@$(PYTEST)

test-binary:
	@if [ -z "$(BINARY)" ]; then echo "Usage: make test-binary BINARY=<.local/bin name>" >&2; exit 2; fi
	@$(PYTEST) --binary "$(BINARY)"

cluster-create:
	@echo "Creating Kind cluster..."
	@devcluster create

cluster-up:
	@echo "Deploying manifests..."
	@devcluster up

cluster-status:
	@echo "Checking cluster status..."
	@devcluster status

cluster-logs:
	@if [ -z "$(LOGS_POD)" ]; then \
		echo "Usage: make cluster-logs LOGS_POD=<pod> [LOGS_CONTAINER=<container>]"; \
		exit 1; \
	fi
	@if [ -n "$(LOGS_CONTAINER)" ]; then \
		devcluster logs "$(LOGS_POD)" "$(LOGS_CONTAINER)"; \
	else \
		devcluster logs "$(LOGS_POD)"; \
	fi

cluster-down:
	@echo "Stopping cluster..."
	@devcluster down

cluster-delete:
	@echo "Deleting cluster..."
	@devcluster delete
