from email import parser
from flask import Blueprint, jsonify, request # type: ignore
from todo.models import db
from todo.models.todo import Todo
import subprocess
import base64
import uuid
import os
import re

import csv
import requests # type: ignore
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__) 

from datetime import datetime, timedelta

api = Blueprint('api', __name__, url_prefix='/api/v1')

def get_valid_lab_ids():
    url = "https://csse6400.uqcloud.net/resources/labs.csv"
    response = requests.get(url)
    
    if response.status_code != 200:
        raise Exception("Failed to fetch lab data from the URL")
    
    valid_lab_ids = set()
    
    
    cleaned_text = response.text.lstrip('\ufeff')
    
    csv_reader = csv.reader(cleaned_text.splitlines())
    
    for row in csv_reader:
        if row:
            lab_id = row[0].strip()  
            valid_lab_ids.add(lab_id)
    
    return valid_lab_ids

VALID_LABS = get_valid_lab_ids()


@api.route('/health')
def health():
    return jsonify({"status": "ok"})

from celery.result import AsyncResult # type: ignore
from todo.tasks import ical
from todo.tasks.ical import ical
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@api.route('/analysis', methods=['POST'])
def analyze_image():
    """Validate and initiate image analysis for pathogen markers using Celery."""
 

    data = request.args

    if 'patient_id' not in data:
        return jsonify({'error': 'missing_patient_id'}), 400

    if 'lab_id' not in data:
        return jsonify({'error': 'missing_lab_id'}), 400

    lab_id = data.get('lab_id')
    patient_id = data.get('patient_id')

    if lab_id not in get_valid_lab_ids():
        return jsonify({'error': 'invalid_lab_id'}), 400

    if not (patient_id.isnumeric() and len(patient_id) == 11):
        return jsonify({'error': 'invalid_patient_id'}), 400

    allowed_params = {'lab_id', 'patient_id', 'urgent'}
    unexpected_params = [key for key in request.args.keys() if key not in allowed_params]
    if unexpected_params:
        return jsonify({'error': f'Unexpected query parameter(s): {", ".join(unexpected_params)}'}), 400

    urgent = request.args.get('urgent', 'false').lower() == 'true'

    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400

    if not request.json or 'image' not in request.json:
        return jsonify({'error': 'Missing image in request body'}), 400

    valid_body_keys = {'image'}
    extra_keys = [key for key in request.json.keys() if key not in valid_body_keys]
    if extra_keys:
        return jsonify({
            "error": "invalid_request",
            "detail": f"Unexpected key(s) in request body: {', '.join(extra_keys)}. Only 'image' is allowed."
        }), 400

    image_base64 = request.json['image']

    #try:
    # request_id = str(uuid.uuid4())
        # Create the database entry first with status 'pending' and generate the request_id
       
    new_job = Todo(
                request_id=str(uuid.uuid4()),
                patient_id=patient_id,
                lab_id=lab_id,
                urgent=urgent,
                result='pending',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
    db.session.add(new_job)
    db.session.commit()
    queue_name = "urgentqueue" if urgent else "celerytaskqueue"
    task = ical.apply_async(
    args=(patient_id, lab_id, image_base64, urgent, new_job.request_id),
    queue=queue_name,
   
)


    return jsonify({
             "id": new_job.request_id,
            "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "status": "pending"
        }), 201




@api.route('/todos/ical/<task_id>/status', methods=['GET'])
def get_task_status(task_id):
    task_result = AsyncResult(task_id)
    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "result_url": f'{request.host_url}api/v1/todos/ical/{task_id}/result'
    }
    return jsonify(result), 200


@api.route('/todos/ical/<task_id>/result', methods=['GET'])
def get_task_result(task_id):
    task_result = AsyncResult(task_id)
    if task_result.status == 'SUCCESS':
        return jsonify(task_result.result), 200
    else:
        return jsonify({'error': 'Task not finished'}), 404


@api.route('/labs/results/<string:lab_id>', methods=['GET'])
def get_lab_results(lab_id):
    """Retrieve lab analysis results with optional filters."""
    try:
        logger.debug(f"Received request for lab results with lab_id: {lab_id}")

        if not lab_id: 
            logger.debug("Missing lab_id in request")
            return jsonify({'error': 'missing_lab_id'}), 400

        if lab_id not in VALID_LABS:
            logger.debug(f"Invalid lab_id provided: {lab_id}")
            return jsonify({'error': 'invalid_lab_id'}), 404

        limit = request.args.get('limit', default=100, type=int)
        offset = request.args.get('offset', default=0, type=int)
        start = request.args.get('start')
        end = request.args.get('end')
        patient_id = request.args.get('patient_id')
        result = request.args.get('result')
        urgent = request.args.get('urgent')

        logger.debug(f"Parsed parameters - limit: {limit}, offset: {offset}, start: {start}, end: {end}, patient_id: {patient_id}, result: {result}, urgent: {urgent}")

        if limit <= 0 or limit > 1000:
            logger.debug(f"Invalid limit value: {limit}")
            return jsonify({'error': 'Limit must be between 1 and 1000'}), 400
        if offset < 0:
            logger.debug(f"Invalid offset value: {offset}")
            return jsonify({'error': 'Offset must be greater than or equal to 0'}), 400

        valid_statuses = {"pending", "covid", "h5n1", "healthy", "failed"}
        if result and result not in valid_statuses:
            logger.debug(f"Invalid result status: {result}")
            return jsonify({'error': 'Invalid status'}), 400

        try:
            if start:
                start = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if end:
                end = datetime.fromisoformat(end.replace("Z", "+00:00"))
            if start and end and start > end:
                logger.debug("Start date is after end date")
                return jsonify({'error': 'Start date must be before end date'}), 400
        except ValueError:
            logger.debug(f"Invalid date format provided: start={start}, end={end}")
            return jsonify({'error': 'Invalid date format. Must be in RFC3339 format'}), 400

        if patient_id and (not patient_id.isdigit() or len(patient_id) != 11):
            logger.debug(f"Invalid patient ID: {patient_id}")
            return jsonify({'error': 'Patient ID must be an 11-digit Medicare number'}), 400

        if urgent is not None:
            if urgent.lower() not in ["true", "false", "1", "0"]:
                logger.debug(f"Invalid urgent flag: {urgent}")
                return jsonify({'error': 'Invalid urgent flag. Must be true or false'}), 400
            urgent = urgent.lower() in ['true', '1']
        else:
            urgent = None

        logger.debug("Validation checks passed, proceeding to database query.")

        query = db.session.query(Todo).filter_by(lab_id=lab_id)

        if start:
            query = query.filter(Todo.created_at >= start)
            logger.debug(f"Filtering results with start date: {start}")
        if end:
            query = query.filter(Todo.created_at <= end)
            logger.debug(f"Filtering results with end date: {end}")
        if patient_id:
            query = query.filter(Todo.patient_id == patient_id)
            logger.debug(f"Filtering results by patient ID: {patient_id}")
        if result:
            query = query.filter(Todo.result == result)
            logger.debug(f"Filtering results by status: {result}")
        if urgent is not None:
            query = query.filter(Todo.urgent == urgent)
            logger.debug(f"Filtering results by urgent: {urgent}")

        query = query.order_by(Todo.created_at.asc())

        total_results = query.count()
        logger.debug(f"Total results found: {total_results}")

        if offset >= total_results:
            logger.debug("Offset is out of range, returning empty list.")
            return jsonify([]), 200

        results = query.offset(offset).limit(limit).all()
        logger.debug(f"Returning {len(results)} results.")

        response = [
            {
                "request_id": result.request_id,
                "lab_id": result.lab_id,
                "patient_id": result.patient_id,
                "result": result.result,
                "urgent": result.urgent,
                "created_at": result.created_at.isoformat() + "Z",
                "updated_at": result.updated_at.isoformat() + "Z"
            }
            for result in results
        ]
        logger.debug("Response successfully generated.")
        return jsonify(response), 200

    except Exception as e:
        logger.debug(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'error': 'An unknown error occurred trying to process the request'}), 500

@api.route('/patients/results', methods=['GET'])
def get_patient_results():
    """List all analysis jobs associated with a patient with optional filters."""
    
    patient_id = request.args.get('patient_id')
    start = request.args.get('start')
    end = request.args.get('end')
    status = request.args.get('status')
    urgent = request.args.get('urgent', type=bool)

  
    if not patient_id or not patient_id.isdigit() or len(patient_id) != 11:
        return jsonify({'error': 'Patient ID must be an 11-digit Medicare number'}), 400

   
    valid_statuses = {"pending", "covid", "h5n1", "healthy", "failed"}
    if status and status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400

   
    try:
        if start:
            start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if end:
            end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return jsonify({'error': 'Invalid date format. Must be in RFC3339 format'}), 400


    query = Todo.query.filter_by(patient_id=patient_id)

    if start:
        query = query.filter(Todo.created_at >= start)
    if end:
        query = query.filter(Todo.created_at <= end)
    if status:
        query = query.filter(Todo.result == status)
    if urgent is not None:
        query = query.filter(Todo.urgent == urgent)


    results = query.all()


    return jsonify([result.to_dict() for result in results])


@api.route('/labs', methods=['GET'])
def get_labs():
    """Retrieve the list of labs with permission to use this service."""
    
    labs = db.session.query(Todo.lab_id).distinct().all()
    

    lab_ids = [lab[0] for lab in labs]
    
    return jsonify(lab_ids)



from datetime import datetime

@api.route('/labs/results/<string:lab_id>/summary', methods=['GET'])
def get_lab_summary(lab_id):
    """Retrieve a summary of analysis jobs associated with the given lab ID."""
    
    if lab_id not in VALID_LABS:
        return jsonify({'error': 'Lab ID not found in the list of valid lab IDs'}), 404
    
   
    lab_exists = Todo.query.filter_by(lab_id=lab_id).first()
    print(f"DEBUG: Checking if lab_id {lab_id} exists in Todo: {lab_exists}")

    if not lab_exists:
        print(f"DEBUG: Lab ID {lab_id} does not exist in the database.")
        return jsonify({'error': 'Lab ID not found'}), 404

    start = request.args.get('start')
    end = request.args.get('end')


    print(f"DEBUG: Received lab_id={lab_id}, start={start}, end={end}")


    try:
        if start:
            start = parser.isoparse(start)
        if end:
            end = parser.isoparse(end)
    except ValueError:
        return jsonify({'error': 'Invalid date format. Must be in RFC3339 format'}), 400

    try:
 
        query = db.session.query(Todo).filter_by(lab_id=lab_id)

        if start:
            query = query.filter(Todo.created_at >= start)
        if end:
            query = query.filter(Todo.created_at <= end)

      
        if query.count() == 0:
            return jsonify({'error': 'Analysis request identifier does not correspond to any submitted analysis requests.'}), 404

   
        summary = {
            "lab_id": lab_id,
            "pending": query.filter(Todo.result == "pending").count(),
            "covid": query.filter(Todo.result == "covid").count(),
            "h5n1": query.filter(Todo.result == "h5n1").count(),
            "healthy": query.filter(Todo.result == "healthy").count(),
            "failed": query.filter(Todo.result == "failed").count(),
            "urgent": query.filter(Todo.result == True).count(),
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        }

        return jsonify(summary), 200
    
    except Exception as e:
   
        return jsonify({'error': f'An unknown error occurred: {str(e)}'}), 500

@api.route('/analysis', methods=['GET'])
def get_analysis_by_request_id():
    """Retrieve an analysis job by its request ID."""
    
    
    request_id = request.args.get('request_id')
    if not request_id:
      return jsonify({'error': 'Missing request_id'}), 400


  
    try:
        uuid.UUID(request_id) 
    except ValueError:
        return jsonify({'error': 'Invalid request_id format. It must be a valid UUIDv4.'}), 404


    analysis = Todo.query.filter_by(request_id=request_id).first()

    
  
    if analysis:
     return jsonify({
            "request_id": analysis.request_id,
            "lab_id": analysis.lab_id,
            "patient_id": analysis.patient_id,
            "result": analysis.result,
            "urgent": analysis.urgent,
            "created_at": analysis.created_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
            "updated_at": analysis.updated_at.strftime('%Y-%m-%dT%H:%M:%SZ')
        }), 200

    task_result = AsyncResult(request_id)
    if task_result.state == 'PENDING':
        # Return the same format as above, with result = "pending"
        # You can mock values or infer them if needed
        return jsonify({
            "request_id": request_id,
            "lab_id": None,
            "patient_id": None,
            "result": "pending",
            "urgent": None,
            "created_at": None,
            "updated_at": None
        }), 200
    elif task_result.state == 'SUCCESS':
    # Return the same format as the DB response but with 'pending' placeholder values
     return jsonify({
        "request_id": request_id,
        "lab_id": None,
        "patient_id": None,
        "result": "pending",
        "urgent": None,
        "created_at": None,
        "updated_at": None
    }), 200
    return jsonify({'error': 'Analysis not found'}), 404

@api.route('/analysis', methods=['PUT'])
def update_lab_for_analysis():

    request_id = request.args.get('request_id')
    lab_id = request.args.get('lab_id')

   
    if not request_id:
        return jsonify({'error': 'Missing request_id parameter'}), 404 

    try:
        uuid.UUID(request_id) 
    except ValueError:
        return jsonify({'error': 'Invalid request_id format'}), 404  

    todo_item = Todo.query.filter_by(request_id=request_id).first()
    
    if not todo_item:
        return jsonify({'error': 'Analysis job not found'}), 404  


   
    if not lab_id:
        return jsonify({'error': 'Missing lab_id parameter'}), 400  

   
    if lab_id not in VALID_LABS:
        return jsonify({'error': 'Invalid lab identifier'}), 400  

    
    if todo_item.lab_id == lab_id:
        return jsonify({
            "request_id": todo_item.request_id,
            "lab_id": todo_item.lab_id,
            "patient_id": todo_item.patient_id,
            "result": todo_item.result,
            "urgent": todo_item.urgent,


        }), 200 


    try:
        todo_item.lab_id = lab_id
        todo_item.updated_at = datetime.utcnow() 
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update the database'}), 500

    return jsonify({
        "request_id": todo_item.request_id,
        "lab_id": todo_item.lab_id,
        "patient_id": todo_item.patient_id,
        "result": todo_item.result,
        "urgent": todo_item.urgent,
       "created_at": todo_item.created_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
            "updated_at": todo_item.updated_at.strftime('%Y-%m-%dT%H:%M:%SZ')

   
    }), 200  