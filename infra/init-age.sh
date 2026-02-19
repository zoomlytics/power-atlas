#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to start..."
until pg_isready -h localhost -U "$POSTGRES_USER"; do
  sleep 1
done

echo "PostgreSQL is ready!"

# Create the database if it doesn't exist
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
    SELECT 'CREATE DATABASE power_atlas'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'power_atlas')\gexec
EOSQL

echo "Database 'power_atlas' ensured to exist"

# Connect to the database and create the AGE extension
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "power_atlas" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS age;
    LOAD 'age';
    SET search_path = ag_catalog, "$user", public;
EOSQL

echo "Apache AGE extension created and loaded successfully!"
