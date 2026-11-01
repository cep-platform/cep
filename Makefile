include .env
export

.PHONY: deploy build up dev-up dev dev-trust log trust dns-up dns-down host-extras

deploy: trust

# Development equivalent of deploy: same shape (up + host-side extras +
# appstore trust registration), but against the live-reload overlay.
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
	incus-compose up -d --no-healthd
	$(MAKE) host-extras

# Bare live-reload stack: overlays compose.dev.yml, which bind-mounts ./src
# and points PYTHONPATH at it so the nix-baked interpreter imports the
# working tree (uvicorn reload=True does the rest). `make dev` is the full
# equivalent of `make deploy` (this + host extras + trust).
dev-up:
	cat startupscripts/client_banner.txt
	incus-compose -f compose.yml -f compose.dev.yml up -d --no-healthd
	$(MAKE) host-extras

dev-trust: dev-up
	scripts/register-appstore-client.sh

# Host-side dev extras that live outside incus-compose (cep-dns + client init).
host-extras:
	# $(MAKE) dns-up
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

down: dns-down
	incus-compose down
	pkill nebula
