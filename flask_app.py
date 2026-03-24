import os
import uuid
import threading
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import pandas as pd
from gst_automation_playwright import run_batch_gst_search_excel, get_path

app = Flask(__name__)
# In production/deployment, these folders should be managed properly
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Global dictionary to track job statuses (simple in-memory)
jobs = {}

def process_excel_background(job_id, input_path, output_filename):
    """Background task to run the automation."""
    try:
        def callback(msg):
            jobs[job_id]['message'] = msg
            print(f"Job {job_id}: {msg}")

        jobs[job_id]['status'] = 'processing'
        jobs[job_id]['message'] = 'Initializing search engine...'
        
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        df = pd.read_excel(input_path)
        df.to_excel(output_path, index=False)
        
        # Run the automation with status callback
        run_batch_gst_search_excel(output_path, status_callback=callback)
        
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['message'] = 'All GSTINs processed successfully!'
        jobs[job_id]['result_file'] = output_filename
    except Exception as e:
        print(f"Error in job {job_id}: {e}")
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and file.filename.endswith(('.xlsx', '.xls')):
        filename = secure_filename(file.filename)
        job_id = str(uuid.uuid4())
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}_{filename}")
        file.save(input_path)
        
        output_filename = f"processed_{filename}"
        
        # Start processing in background thread
        jobs[job_id] = {'status': 'queued', 'progress': 0, 'message': 'Queued...'}
        thread = threading.Thread(target=process_excel_background, args=(job_id, input_path, output_filename))
        thread.start()
        
        return jsonify({'job_id': job_id})
    else:
        return jsonify({'error': 'Invalid file type. Only Excel files are supported.'}), 400

@app.route('/status/<job_id>')
def get_status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(jobs[job_id])

@app.route('/download/<job_id>')
def download_file(job_id):
    if job_id not in jobs or jobs[job_id]['status'] != 'completed':
        return jsonify({'error': 'File not ready or job failed'}), 404
    
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], jobs[job_id]['result_file'])
    return send_file(output_path, as_attachment=True)

if __name__ == '__main__':
    # When running locally
    app.run(debug=True, port=5000)
