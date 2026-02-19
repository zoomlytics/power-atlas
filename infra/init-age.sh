#!/bin/bash
set -e

# This script runs during database initialization
# The database is already running when init scripts are called

echo "Ensuring power_atlas database exists..."

# Create the database if it doesn't exist
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
    SELECT 'CREATE DATABASE power_atlas'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'power_atlas')\gexec
EOSQL

echo "Ensuring Apache AGE extension is created..."

# Connect to the database and create the AGE extension
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "power_atlas" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS age;
    LOAD 'age';
    SET search_path = ag_catalog, "\$user", public;
EOSQL

echo "Apache AGE setup complete!"
