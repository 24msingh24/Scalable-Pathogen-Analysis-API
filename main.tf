terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    docker = {
      source  = "kreuzwerker/docker"
      version = "3.0.2"
    }
  }
  
 
  
}

provider "aws" {
  region                  = "us-east-1"
  shared_credentials_files = ["./credentials"]
  default_tags {
    tags = {
      Course     = "CSSE6400"
      Name       = "CoughOverflow"
      Automation = "Terraform" 
    }
  }
}

data "aws_ecr_authorization_token" "ecr_token" {}

provider "docker" {
  registry_auth {
    address  = data.aws_ecr_authorization_token.ecr_token.proxy_endpoint
    username = data.aws_ecr_authorization_token.ecr_token.user_name
    password = data.aws_ecr_authorization_token.ecr_token.password
  }
}

resource "aws_ecr_repository" "todo" {
  name = "todo"
}

resource "docker_image" "todo" {
  name = "${aws_ecr_repository.todo.repository_url}:latest"
  build {
    context = "."
    dockerfile = "Dockerfile"
  }
  depends_on = [aws_ecr_repository.todo]
}
resource "aws_ecs_cluster" "todo" {
  name = "todo-cluster"
}

resource "aws_appautoscaling_policy" "todo_cpu_policy" {
  name               = "todo-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.todo.resource_id
  scalable_dimension = aws_appautoscaling_target.todo.scalable_dimension
  service_namespace  = aws_appautoscaling_target.todo.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    target_value       = 20
   # scale_in_cooldown  = 60
   # scale_out_cooldown = 60
  }
}
resource "aws_appautoscaling_target" "todo" {
  max_capacity       = 4
  min_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.todo.name}/${aws_ecs_service.todo.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
  depends_on = [ aws_ecs_service.todo]
}


resource "docker_registry_image" "todo" {
  name = docker_image.todo.name
  
}

output "ecr_repository_url" {
  value = aws_ecr_repository.todo.repository_url
}



locals {
  image              = docker_registry_image.todo.name
  celery_image       = docker_registry_image.celery_worker.name
  database_username  = "administrator"
  database_password  = "foobarbaz"
}
resource "aws_ecs_service" "todo" {
    name = "todo"
    cluster = aws_ecs_cluster.todo.id
    task_definition = aws_ecs_task_definition.todo.arn
    desired_count = 1
    launch_type = "FARGATE"
    network_configuration {
     subnets = data.aws_subnets.private.ids
     security_groups = [aws_security_group.todo.id]
     assign_public_ip = true
   } 
   load_balancer {
    target_group_arn = aws_lb_target_group.todo.arn
    container_name   = "todo"
    container_port   = 8080
  }
}


resource "aws_security_group" "todo" {
  name        = "todo"
  description = "todo Security Group"

  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "CoughOverflow_database" {
  name        = "coughoverflow_database"
  description = "Allow inbound PostgreSQL traffic"

  ingress {
    from_port        = 5432
    to_port          = 5432
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "CoughOverflow_database"
  }
}


data "aws_iam_role" "lab" {
  name = "LabRole"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}


resource "aws_db_instance" "CoughOverflow_database" {
  allocated_storage      = 20
  instance_class         = "db.t3.micro"
  engine                 = "postgres"
  engine_version         = "17"
  db_name                   = "coughoverflowdb"
  username               = local.database_username
  password               = local.database_password
  port                   = 5432
  skip_final_snapshot    = true
  publicly_accessible    = false
  vpc_security_group_ids = [aws_security_group.CoughOverflow_database.id]

  tags = {
    Name = "CoughOverflow_database"
  }
}

resource "aws_ecs_task_definition" "todo" {
  family                   = "todo"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = data.aws_iam_role.lab.arn

  container_definitions = <<DEFINITION
[
  {
    "image": "${local.image}",
    "cpu": 1024,
    "memory": 2048,
    "name": "todo",
    "networkMode": "awsvpc",
    "portMappings": [
      {
        "containerPort": 8080,
        "hostPort": 8080
      }
    ],
    "environment": [
      {
        "name": "SQLALCHEMY_DATABASE_URI",
        "value": "postgresql://${local.database_username}:${local.database_password}@${aws_db_instance.CoughOverflow_database.address}:${aws_db_instance.CoughOverflow_database.port}/${aws_db_instance.CoughOverflow_database.db_name}"

      },
      {
        "name": "CELERY_BROKER_URL",
        "value": "sqs://"
      },
      {
        "name": "SQS_QUEUE_URL",
        "value": "${aws_sqs_queue.celery_task_queue.url}"
      },
      {
        "name": "AWS_REGION",
        "value": "us-east-1"
      },
      {
        "name": "CELERY_RESULT_BACKEND",
        "value": "db+postgresql://${local.database_username}:${local.database_password}@${aws_db_instance.CoughOverflow_database.address}:${aws_db_instance.CoughOverflow_database.port}/${aws_db_instance.CoughOverflow_database.db_name}"

      },
      {
        "name": "CELERY_DEFAULT_QUEUE",
        "value": "celerytaskqueue"
      }
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/todo/todo",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "ecs",
        "awslogs-create-group": "true"
      }
    }
  }
]
DEFINITION
}


output "load_balancer_dns" {
  value = aws_lb.todo.dns_name
}

variable "aws_region" {
  description = "The AWS region to deploy resources in."
  type        = string
  default     = "us-east-1"  # Or another AWS region of your choice
}
data "aws_caller_identity" "current" {}

resource "aws_ecs_task_definition" "celery_worker" {
  family                   = "celery-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = data.aws_iam_role.lab.arn
  container_definitions = <<DEFINITION
[
  {
   "image": "${local.celery_image}",
    "cpu": 1024,
    "memory": 2048,
    "name": "celery-worker",
    "networkMode": "awsvpc",
    "environment": [
      {
        "name": "SQLALCHEMY_DATABASE_URI",
        "value": "postgresql://${local.database_username}:${local.database_password}@${aws_db_instance.CoughOverflow_database.address}:${aws_db_instance.CoughOverflow_database.port}/${aws_db_instance.CoughOverflow_database.db_name}"
      },
      {
        "name": "CELERY_BROKER_URL",
        "value": "sqs://"


      },
      {
        "name": "SQS_QUEUE_URL",
        "value": "${aws_sqs_queue.celery_task_queue.url}"
      },
      {
        "name": "AWS_REGION",
        "value": "us-east-1"
      },
      {
        "name": "CELERY_RESULT_BACKEND",
        "value": "db+postgresql://${local.database_username}:${local.database_password}@${aws_db_instance.CoughOverflow_database.address}:${aws_db_instance.CoughOverflow_database.port}/${aws_db_instance.CoughOverflow_database.db_name}"

      },
      {
        "name": "CELERY_DEFAULT_QUEUE",
        "value": "celerytaskqueue"
      }
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/celery/worker",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "ecs",
        "awslogs-create-group": "true"
      }
    }
  }
]
DEFINITION
}

resource "aws_ecs_task_definition" "celery_urgent_worker" {
  family                   = "celery-urgent-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = data.aws_iam_role.lab.arn
  container_definitions = <<DEFINITION
[
  {
    "image": "${local.celery_image}",
    "cpu": 1024,
    "memory": 2048,
    "name": "celery-urgent-worker",
    "networkMode": "awsvpc",
    "environment": [
      {
        "name": "SQLALCHEMY_DATABASE_URI",
        "value": "postgresql://${local.database_username}:${local.database_password}@${aws_db_instance.CoughOverflow_database.address}:${aws_db_instance.CoughOverflow_database.port}/${aws_db_instance.CoughOverflow_database.db_name}"
      },
      {
        "name": "CELERY_BROKER_URL",
        "value": "sqs://"
      },
      {
        "name": "SQS_QUEUE_URL",
        "value": "${aws_sqs_queue.celery_urgent_queue.url}"
      },
      {
        "name": "AWS_REGION",
        "value": "us-east-1"
      },
      {
        "name": "CELERY_RESULT_BACKEND",
        "value": "db+postgresql://${local.database_username}:${local.database_password}@${aws_db_instance.CoughOverflow_database.address}:${aws_db_instance.CoughOverflow_database.port}/${aws_db_instance.CoughOverflow_database.db_name}"
      },
      {
        "name": "CELERY_DEFAULT_QUEUE",
        "value": "urgentqueue"
      }
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/celery/urgent-worker",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "ecs",
        "awslogs-create-group": "true"
      }
    }
  }
]
DEFINITION
}

resource "aws_ecs_service" "celery_worker" {
  name            = "celery-worker"
  cluster         = aws_ecs_cluster.todo.id  # Reference the existing cluster
  task_definition = aws_ecs_task_definition.celery_worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = data.aws_subnets.private.ids
    security_groups  = [aws_security_group.todo.id]
    assign_public_ip = true
  }
}
resource "aws_ecs_service" "celery_urgent_worker" {
  name            = "celery-urgent-worker"
  cluster         = aws_ecs_cluster.todo.id
  task_definition = aws_ecs_task_definition.celery_urgent_worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = data.aws_subnets.private.ids
    security_groups  = [aws_security_group.todo.id]
    assign_public_ip = true
  }
}

resource "aws_ecr_repository" "celery_worker" {
  name = "celery-worker"
}

resource "docker_image" "celery_worker" {
  name = "${aws_ecr_repository.celery_worker.repository_url}:latest"
  build {
    context    = "."
    dockerfile = "Dockerfile.worker"
  }
  depends_on = [aws_ecr_repository.celery_worker]
}

resource "docker_registry_image" "celery_worker" {
  name = docker_image.celery_worker.name
}

