import uuid
import datetime
import re
from . import db
import requests  # type: ignore
import csv


def get_valid_lab_ids():
    url = "https://csse6400.uqcloud.net/resources/labs.csv"
    try:
        response = requests.get(url)
        response.raise_for_status() 
        
        valid_lab_ids = set()
        
       
        cleaned_text = response.text.lstrip('\ufeff')
        
        csv_reader = csv.reader(cleaned_text.splitlines())
        
        for row in csv_reader:
            if row:
                lab_id = row[0].strip()  # Ensure no leading/trailing spaces
                valid_lab_ids.add(lab_id)
        
        return valid_lab_ids
    except Exception as e:
        print(f"Warning: Failed to fetch valid lab IDs: {e}")
        return set() 


VALID_LABS = get_valid_lab_ids()


VALID_RESULTS = {"pending", "covid", "h5n1", "healthy", "failed"}

class Todo(db.Model):
    __tablename__ = 'Todo'
    
    request_id = db.Column(db.String(36), primary_key=True, nullable=False)
    lab_id = db.Column(db.String(50), nullable=False)
    patient_id = db.Column(db.String(11), nullable=False)  
    result = db.Column(db.String(50), nullable=False, default='pending')
    urgent = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs) 

      
        if self.result not in VALID_RESULTS:
            raise ValueError(f"Invalid result value: {self.result}. Must be one of {VALID_RESULTS}")

        
        if not re.match(r'^\d{11}$', self.patient_id):
            raise ValueError("Patient ID must be an 11-digit Medicare number")

        if self.lab_id not in VALID_LABS:
            raise ValueError(f"Invalid lab_id: {self.lab_id}. Must be one of {VALID_LABS}")


        if not isinstance(self.urgent, bool):
            raise ValueError("Urgent must be a boolean value (True/False)")

    def to_dict(self):
        return {
            'lab_id': self.lab_id,
            'request_id': self.request_id,
            'patient_id': self.patient_id,
            'result': self.result,
            'urgent': self.urgent,
            "created_at": self.created_at.replace(microsecond=0).isoformat() + "Z",
            "updated_at": self.updated_at.replace(microsecond=0).isoformat() + "Z",
        }

    def __repr__(self):
        return (f'<Todo request_id={self.request_id} '
                f'lab_id={self.lab_id} patient_id={self.patient_id} '
                f'result={self.result} urgent={self.urgent} '
                f'created_at={self.created_at} updated_at={self.updated_at}>')
