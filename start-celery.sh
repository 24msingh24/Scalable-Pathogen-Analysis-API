#!/bin/bash
# start-celery.sh

# Load environment variables from aws.env
set -a
. /app/aws.env  # Load the environment variables (AWS credentials, etc.)
set +a

# Optional: Print environment variables for debugging (remove in production)
echo "Starting Celery worker with the following environment:"
echo "CELERY_BROKER_URL=$CELERY_BROKER_URL"
echo "AWS_REGION=$AWS_REGION"
echo "CELERY_RESULT_BACKEND=$CELERY_RESULT_BACKEND"
echo "CELERY_APP=$CELERY_APP"  # This will show the Celery app being used
echo "CELERY_LOGLEVEL=$CELERY_LOGLEVEL"  # Show the log level

# Ensure CELERY_APP and CELERY_LOGLEVEL are set correctly
: ${CELERY_APP:="todo.tasks.ical"}  # Default if not set in aws.env
: ${CELERY_LOGLEVEL:="info"}  # Default if not set in aws.env

# Now run the Celery worker (this is equivalent to the CMD in the Dockerfile)
exec poetry run celery --app $CELERY_APP worker --loglevel $CELERY_LOGLEVEL -Q celerytaskqueue,urgentqueue
