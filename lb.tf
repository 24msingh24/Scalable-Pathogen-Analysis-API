resource "aws_lb_target_group" "todo" {
  name        = "todo"
  port        = 8080
  protocol    = "HTTP"
  vpc_id = data.aws_vpc.default.id
  target_type = "ip"

  health_check {
    path                = "/api/v1/health"
    port                = "8080"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 10
  }
}


resource "aws_lb" "todo" {
  name               = "todo"
  internal           = false
  load_balancer_type = "application"
  subnets            = data.aws_subnets.private.ids
  security_groups    = [aws_security_group.todo_lb.id]
}

resource "aws_security_group" "todo_lb" {
  name        = "todo_lb"
  description = "todo Load Balancer Security Group"
  vpc_id = data.aws_vpc.default.id  

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "todo_lb_security_group"
  }
}

resource "aws_lb_listener" "todo" {
  load_balancer_arn = aws_lb.todo.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.todo.arn
  }
}
