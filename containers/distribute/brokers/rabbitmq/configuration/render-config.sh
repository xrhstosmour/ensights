#!/bin/sh
# Renders rabbitmq.conf.template into a real config file, substituting the
# $(VAR) placeholders from the container's actual environment. RabbitMQ's
# Cuttlefish config format doesn't do this itself, and Compose only
# interpolates ${VAR} inside compose YAML, never inside bind-mounted files.
set -eu

sed \
  -e "s|\$(RABBITMQ_PORT)|${RABBITMQ_PORT}|g" \
  -e "s|\$(RABBITMQ_CONSUMER_TIMEOUT)|${RABBITMQ_CONSUMER_TIMEOUT}|g" \
  -e "s|\$(RABBITMQ_MANAGEMENT_PORT)|${RABBITMQ_MANAGEMENT_PORT}|g" \
  /etc/rabbitmq/rabbitmq.conf.template > /etc/rabbitmq/rabbitmq.conf

exec docker-entrypoint.sh rabbitmq-server
