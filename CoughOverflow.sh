#!/bin/bash

# Update packages
yum update -y

# Install Docker
yum install -y docker
systemctl start docker
systemctl enable docker

# Install Git
yum install -y git

# Go to home directory and clone repo
cd /home/ec2-user
git clone https://github.com/CSSE6400/coughoverflow-24msingh24.git

# Give permission to run scripts
cd coughoverflow-24msingh24
chmod +x local.sh

# Run the local.sh script to build and run the Docker container
./local.sh
