#!/bin/bash
# start-flask.sh

# Load environment variables from aws.env
set -a
. /app/aws.env  # Load the environment variables (AWS credentials, etc.)
set +a

# Optional: Print environment variables for debugging (remove in production)
echo "Starting Flask with the following environment:"
echo "FLASK_APP=$FLASK_APP"
echo "AWS_REGION=$AWS_REGION"

# Ensure FLASK_APP is set correctly
: ${FLASK_APP:="todo"}

# Now run Flask (this is equivalent to running `flask run`)
exec poetry run flask run --host=0.0.0.0 --port=8080
