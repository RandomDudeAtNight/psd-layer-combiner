"""
PSD Processing Web Service

A Flask-based web service that processes PSD files to generate JPG variants.
"""

import os
import logging
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from psd_tools import PSDImage
from psd_layer_processor import PSDProcessor  # Import the PSD processor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = os.path.join(tempfile.gettempdir(), 'psd_uploads')
app.config['OUTPUT_FOLDER'] = os.path.join(tempfile.gettempdir(), 'psd_outputs')

# Ensure upload and output directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

def allowed_file(filename: str) -> bool:
    """Check if the file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'psd'}

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'psd-processor'
    })

@app.route('/api/process', methods=['POST'])
def process_psd():
    """
    Process a PSD file and generate JPG variants.
    
    Accepts a PSD file either as a file upload or a URL to download the file.
    
    Request format (multipart/form-data):
    - file: The PSD file to process (optional if url is provided)
    - url: URL to download the PSD file (optional if file is provided)
    - output_format: Desired output format (default: 'jpg')
    - quality: JPEG quality (1-100, default: 90)
    """
    # Check if the request has a file or URL
    if 'file' not in request.files and 'url' not in request.form:
        return jsonify({
            'error': 'No file or URL provided',
            'success': False
        }), 400
    
    # Create a unique job ID for this request
    job_id = str(uuid.uuid4())
    logger.info(f"Starting job {job_id}")
    
    try:
        # Create a temporary directory for this job
        job_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Handle file upload
        psd_path = None
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No selected file', 'success': False}), 400
                
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                psd_path = os.path.join(job_dir, filename)
                file.save(psd_path)
                logger.info(f"Saved uploaded file to {psd_path}")
            else:
                return jsonify({
                    'error': 'Invalid file type. Only PSD files are allowed.',
                    'success': False
                }), 400
        
        # Handle URL download
        elif 'url' in request.form:
            import requests
            from urllib.parse import urlparse
            
            url = request.form['url']
            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                # Extract filename from URL or generate one
                filename = os.path.basename(urlparse(url).path) or f'upload_{job_id}.psd'
                if not filename.lower().endswith('.psd'):
                    filename += '.psd'
                    
                psd_path = os.path.join(job_dir, filename)
                
                with open(psd_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"Downloaded file from {url} to {psd_path}")
                
            except Exception as e:
                logger.error(f"Error downloading file from URL: {e}")
                return jsonify({
                    'error': f'Failed to download file from URL: {str(e)}',
                    'success': False
                }), 400
        
        # Verify PSD file
        if not psd_path or not os.path.exists(psd_path):
            return jsonify({
                'error': 'Failed to process PSD file',
                'success': False
            }), 400
        
        # Process the PSD file
        logger.info(f"Processing PSD file: {psd_path}")
        
        # Get output format and quality from request
        output_format = request.form.get('output_format', 'jpg').lower()
        quality = int(request.form.get('quality', 90))
        
        # Create output directory for this job
        output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
        os.makedirs(output_dir, exist_ok=True)
        
        # Process the PSD file
        processor = PSDProcessor(psd_path, output_dir)
        if not processor.load_psd():
            return jsonify({
                'error': 'Invalid PSD file structure',
                'success': False
            }), 400
        
        # Process the PSD and get results
        success, variants = processor.process()
        if not success:
            return jsonify({
                'error': 'Failed to process PSD',
                'success': False
            }), 500
            
        # Get the list of generated files
        results = [v['filename'] for v in variants if 'filename' in v]
        
        # Prepare response
        response = {
            'job_id': job_id,
            'status': 'completed',
            'input_file': os.path.basename(psd_path),
            'output_dir': output_dir,
            'generated_files': [os.path.basename(f) for f in results],
            'success': True
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error processing PSD: {str(e)}", exc_info=True)
        return jsonify({
            'error': f'Failed to process PSD: {str(e)}',
            'success': False
        }), 500

@app.route('/api/results/<job_id>/<filename>')
def get_result_file(job_id: str, filename: str):
    """Serve a generated file."""
    output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
    return send_from_directory(output_dir, filename)

if __name__ == '__main__':
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)
