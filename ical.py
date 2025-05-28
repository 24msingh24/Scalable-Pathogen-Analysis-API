import os
import base64
import uuid
import subprocess
from datetime import datetime
from celery import Celery
from todo.models import db
from todo.models.todo import Todo
from kombu import Queue  # type: ignore

# Initialize Celery app
celery = Celery(__name__)
celery.conf.broker_url = os.environ.get("CELERY_BROKER_URL")
celery.conf.result_backend = os.environ.get("CELERY_RESULT_BACKEND")
celery.conf.task_default_queue = os.environ.get("CELERY_DEFAULT_QUEUE", "ical")

celery.conf.task_queues = [
    Queue(os.environ.get("CELERY_DEFAULT_QUEUE", "celerytaskqueue")),
    Queue(os.environ.get("URGENT_QUEUE", "urgentqueue")),
]

celery.conf.broker_transport_options = {
    'region': os.environ.get("AWS_REGION", "us-east-1"),
}

@celery.task(name="ical")
def ical(patient_id, lab_id, image_base64, urgent, request_id):
    try:
        # Import create_app inside the task function to avoid circular imports
        from todo import create_app

        # Create Flask app instance and push the app context
        app = create_app()
        with app.app_context():
            # Decode the image data
            image_data = base64.b64decode(image_base64)
            image_filename = f"temp_{str(uuid.uuid4())}.jpg"
            image_path = os.path.join('/tmp', image_filename)

            # Save the image temporarily
            with open(image_path, 'wb') as image_file:
                image_file.write(image_data)

            # Run the image analysis command
            result_filename = f"result_{str(uuid.uuid4())}.txt"
            result_path = os.path.join('/tmp', result_filename)
            binary_path = "/app/overflowengine"
            command = f"{binary_path} --input {image_path} --output {result_path}"

            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Read analysis results
            with open(result_path, 'r') as result_file:
                analysis_result = result_file.read()
            print(f"[DEBUG] Analysis result: {analysis_result}")
            # Handle cases with no results
            if "covid-19" in analysis_result.lower():
                status = "covid"
            elif "h5n1" in analysis_result.lower():
                status = "h5n1"
            elif "healthy" in analysis_result.lower():
                status = "healthy"
            else:
                status = "pending"
            print(f"[DEBUG] Analysis result: {status}")
            # Update the job in the database with the result
            job = Todo.query.filter_by(request_id=request_id).first()
            if job:
                job.result = status
                job.updated_at = datetime.utcnow()
                db.session.commit()
            print(f"[DEBUG] Analysis result: {status}")
            print(f"[DEBUG] Analysis result: {result}")
            return {"request_id": request_id, "result": status}

    except Exception as e:
        # Log the error in case of failure
        import logging
        logging.error(f"Error in ical task for request {request_id}: {e}")

    finally:
        # Clean up files even if an exception occurred
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        if result_path and os.path.exists(result_path):
            os.remove(result_path)
