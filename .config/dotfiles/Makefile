# Makefile for dotfiles cluster management

SHELL := /bin/sh

.PHONY: all test cluster-create cluster-up cluster-status cluster-logs cluster-down cluster-delete

all: help

help:
	@echo "Dotfiles Cluster Management"
	@echo ""
	@echo "Commands:"
	@echo "  make test               Run all tests"
	@echo "  make cluster-create     Create Kind cluster"
	@echo "  make cluster-up         Deploy kustomize manifests"
	@echo "  make cluster-status     Show cluster status"
	@echo "  make cluster-logs       Show logs (use LOGS_POD=<pod>)"
	@echo "  make cluster-down       Stop cluster"
	@echo "  make cluster-delete     Delete cluster"
	@echo ""

test:
	@echo "Running tests..."
	@bats tests/*.bats

cluster-create:
	@echo "Creating Kind cluster..."
	@dotfiles-cluster create

cluster-up:
	@echo "Deploying manifests..."
	@dotfiles-cluster up

cluster-status:
	@echo "Checking cluster status..."
	@dotfiles-cluster status

cluster-logs:
	@if [ -z "$(LOGS_POD)" ]; then \
		echo "Usage: make cluster-logs LOGS_POD=<pod> [LOGS_CONTAINER=<container>]"; \
		exit 1; \
	fi
	@if [ -n "$(LOGS_CONTAINER)" ]; then \
		dotfiles-cluster logs "$(LOGS_POD)" "$(LOGS_CONTAINER)"; \
	else \
		dotfiles-cluster logs "$(LOGS_POD)"; \
	fi

cluster-down:
	@echo "Stopping cluster..."
	@dotfiles-cluster down

cluster-delete:
	@echo "Deleting cluster..."
	@dotfiles-cluster delete
