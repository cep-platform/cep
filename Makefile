.PHONY: deploy up trust

deploy: trust

trust: up
	pwd
	ls ./scripts/register-appstore-client.sh
	scripts/register-appstore-client.sh

up:
	incus-compose up -d --no-healthd
