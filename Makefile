include .env
export

.PHONY: deploy build up dev-up dev dev-trust log trust dns-up dns-down host-extras \
        healthd-pause healthd-resume healthd-quiesce

deploy: trust

# Development equivalent of deploy with live-reload overlay.
dev: dev-trust

# Build the nix OCI image and import it into the incus-compose cache.
build:
	./image/build.sh

logs:
	incus-compose logs --follow
redeploy: down deploy

trust: up
	scripts/register-appstore-client.sh

up:
	cat startupscripts/client_banner.txt
	incus-compose up -d
	$(MAKE) healthd-resume
	$(MAKE) host-extras

dev-up:
	cat startupscripts/client_banner.txt
	incus-compose -f compose.yml -f compose.dev.yml up -d
	$(MAKE) healthd-resume
	$(MAKE) host-extras

dev-trust: dev-up
	scripts/register-appstore-client.sh

# Host-side dev extras that live outside incus-compose (cep-dns + client init).
host-extras:
	$(MAKE) dns-up
	$(MAKE) client-init

client-init:
	chmod +x ./startupscripts/start_client.sh
	./startupscripts/start_client.sh

dns-up:
	docker build -t cep-dns:dev ./unbound
	-docker rm -f cep-dns
	docker run -d \
		--name cep-dns \
		--network host \
		--volume unbound-state:/var/lib/unbound \
		--volume "$(CURDIR)/unbound/service/api.py:/app/api.py" \
		--restart unless-stopped \
		--env DNS_TOKEN \
		cep-dns:dev \
		uvicorn api:app --host 0.0.0.0 --port 8053

dns-down:
	docker rm -f cep-dns

# down pauses the shared health daemon first: ic-healthd busy-loops on stopped
# instances that still carry a healthcheck (see ~/ic-healthd-hotloop.md).
down: healthd-pause dns-down
	incus-compose down
	pkill nebula

# --- ic-healthd hot-loop workaround (~/ic-healthd-hotloop.md) -------------
# Until the scheduler fix is merged and deployed:
#   make healthd-pause    stop the daemon entirely (checks/restarts off)
#   make healthd-quiesce  surgical: strip checks from *stopped* instances only
#   make healthd-resume   restore the daemon (make up / dev-up do it too)

healthd-pause:
	@if incus info ic-healthd --project incus-compose | grep -q "Status: RUNNING"; then \
		echo "Pausing ic-healthd: health checks and auto-restarts are OFF"; \
		incus stop ic-healthd --project incus-compose; \
	else \
		echo "ic-healthd is not running"; \
	fi

healthd-resume:
	@if incus info ic-healthd --project incus-compose | grep -q "Status: STOPPED"; then \
		echo "Resuming ic-healthd"; \
		incus start ic-healthd --project incus-compose; \
	else \
		echo "ic-healthd already running"; \
	fi

# Drops the healthcheck from every stopped instance that still carries one.
# incus-compose up re-applies the config from compose.yml, so starting the
# stack restores the checks. Running instances (caddy) keep theirs.
healthd-quiesce:
	@incus list --all-projects --format json | jq -r \
		'.[] | select((.status|ascii_downcase)=="stopped" and ((.config["user.healthcheck.test"] // "")!="")) | "\(.project) \(.name)"' \
		| while read -r project instance; do \
			echo "Quiescing $$instance (project $$project): unsetting user.healthcheck.test"; \
			incus config unset "$$instance" user.healthcheck.test --project "$$project"; \
		done
	@echo "Stopped instances no longer carry a healthcheck."
