#!/bin/sh
# Create every database listed in POSTGRESQL_ADDITIONAL_DATABASES, in addition
# to the primary database the official image already creates for POSTGRES_USER.
# The list is comma or space separated, for example "glitchtip,metabase".
#
# This runs once, when the data directory is first initialized, from the
# official entrypoint's /docker-entrypoint-initdb.d hook. Each database is
# created only when missing and is owned by POSTGRES_USER, so companion
# services such as GlitchTip and Metabase find their database on first start.
set -e

if [ -z "${POSTGRESQL_ADDITIONAL_DATABASES:-}" ]; then
  echo "No additional databases requested."
  exit 0
fi

for database in $(echo "$POSTGRESQL_ADDITIONAL_DATABASES" | tr ',' ' '); do
  echo "Ensuring database '$database' exists..."
  # Double single quotes for safe interpolation into the SQL string below.
  escaped_database=$(printf '%s' "$database" | sed "s/'/''/g")
  # Same as above, plus doubled double quotes, since this one is also used
  # as a quoted identifier in CREATE DATABASE "...".
  escaped_identifier=$(printf '%s' "$database" | sed "s/\"/\"\"/g; s/'/''/g")
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE "$escaped_identifier"'
    WHERE NOT EXISTS (
      SELECT FROM pg_database WHERE datname = '$escaped_database'
    )\gexec
EOSQL
done
