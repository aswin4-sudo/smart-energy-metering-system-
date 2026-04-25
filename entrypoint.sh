#!/bin/bash
# entrypoint.sh

set -e

echo "🚀 Starting BitMinds Application..."

# Wait for database to be ready
echo "Waiting for database..."
while ! pg_isready -h postgres -U postgres; do
    sleep 1
done
echo "✅ Database is ready!"

# Run database migrations
echo "📊 Running database migrations..."
python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('✅ Database tables created/verified')
"

# Start the application
echo "🎯 Starting Gunicorn server..."
exec gunicorn --worker-class eventlet \
              --workers 2 \
              --bind 0.0.0.0:5000 \
              --timeout 120 \
              --access-logfile - \
              --error-logfile - \
              app:app
