import os
import uuid
import threading
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import openpyxl
from gst_automation_playwright import run_batch_gst_search_excel

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

jobs = {}

def process_excel_background(job_id, input_path, output_filename):
    try:
        def callback(msg):
            jobs[job_id]['message'] = msg
        jobs[job_id]['status'] = 'processing'
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        # Copy input to output using openpyxl
        wb = openpyxl.load_workbook(input_path)
        wb.save(output_path)
        
        run_batch_gst_search_excel(output_path, status_callback=callback)
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['result_file'] = output_filename
    except Exception as e:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({'error': 'No file'}), 400
    
    filename = secure_filename(file.filename)
    job_id = str(uuid.uuid4())
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}_{filename}")
    file.save(input_path)
    
    output_filename = f"processed_{filename}"
    jobs[job_id] = {'status': 'queued', 'message': 'Queued...'}
    threading.Thread(target=process_excel_background, args=(job_id, input_path, output_filename)).start()
    return jsonify({'job_id': job_id})

@app.route('/status/<job_id>')
def get_status(job_id):
    return jsonify(jobs.get(job_id, {'error': 'Not found'}))

@app.route('/download/<job_id>')
def download_file(job_id):
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], jobs[job_id]['result_file'])
    return send_file(output_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
