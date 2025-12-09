#!/bin/bash
# Create new migration
echo "Creating migration..."
alembic revision --autogenerate -m "$1"
echo "✅ Migration created"
