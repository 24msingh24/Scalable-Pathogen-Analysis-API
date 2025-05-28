resource "aws_sqs_queue" "celery_task_queue" {
  name = "celerytaskqueue"
}

resource "aws_sqs_queue" "celery_urgent_queue" {
  name = "urgentqueue"
}
