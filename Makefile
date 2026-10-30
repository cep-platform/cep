include .env
export

.PHONY: deploy build up trust dns-up dns-down

deploy: trust

# Build the nix OCI image and import it into the incus-compose cache.
build:
	./image/build.sh

redeploy: down deploy

trust: up
	scripts/register-appstore-client.sh

up:
	incus-compose up -d --no-healthd
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

down: dns-down
	incus-compose down
