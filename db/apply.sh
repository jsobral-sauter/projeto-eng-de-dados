#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  source <(tr -d '\r' < .env)
  set +a
fi

CONTAINER=spotify_postgres
DB_USER=${POSTGRES_USER:-admin}
DB_NAME=${POSTGRES_DB:-spotify}


SQL_FILES="db/sql/01_schema.sql db/sql/02_indexes.sql db/sql/04_bronze.sql"

for sql in $SQL_FILES; do
  echo "==> Aplicando $sql"
  docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$sql"
done

echo "==> DDL aplicado com sucesso."
