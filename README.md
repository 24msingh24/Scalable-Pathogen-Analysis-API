# CoughOverflow – Scalable Pathogen Analysis API

CoughOverflow is a high-performance cloud API that enables asynchronous pathogen detection (COVID-19 and H5N1) from saliva sample images. Designed to simulate epidemic-scale conditions, the system ensures resilience, scalability, and fast turnaround for urgent and batch requests.

## 🚀 Tech Stack

- **Backend:** Python, Flask
- **Infrastructure:** AWS (EC2, Lambda, MSK Kafka, S3, SQS)
- **IaC & Automation:** Terraform
- **Performance Testing:** Locust, JMeter

## ⚙️ Key Features

- ✅ Asynchronous processing of sample images via Kafka and Lambda
- ✅ Supports both urgent and batch analysis workflows
- ✅ Achieved **99.9% uptime** under simulated epidemic peak load
- ✅ Infrastructure-as-Code (IaC) using Terraform for reproducible deployments
- ✅ Fault-tolerant storage and queuing with S3 and SQS
- ✅ Load-tested for thousands of concurrent requests

## 🧪 How It Works

1. **User uploads saliva image** via REST API
2. **Kafka (MSK)** queues the job
3. **Lambda** triggers `overflowengine` CLI analysis
4. **Results** are stored/retrieved via S3 and logged in DynamoDB
5. **Users receive status updates or batched results via callback/webhook**

## 📦 Repository Structure

