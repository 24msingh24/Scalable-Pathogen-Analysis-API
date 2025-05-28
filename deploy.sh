#!/bin/bash

# Extract AWS credentials from the 'credentials' file
export AWS_ACCESS_KEY_ID=$(awk -F' *= *' '/aws_access_key_id/ {print $2}' credentials)
export AWS_SECRET_ACCESS_KEY=$(awk -F' *= *' '/aws_secret_access_key/ {print $2}' credentials)
export AWS_SESSION_TOKEN=$(awk -F' *= *' '/aws_session_token/ {print $2}' credentials)

# Optional: Write them into aws.env if needed by ECS or Dockerfile
cat <<EOF > aws.env
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}
EOF

# Initialize and apply Terraform
terraform init
terraform apply -auto-approve

# Extract the Load Balancer DNS name and write to api.txt
api_url=$(terraform output -raw load_balancer_dns)

# Write the full API URL to api.txt
echo "http://${api_url}/api/v1/" > api.txt
