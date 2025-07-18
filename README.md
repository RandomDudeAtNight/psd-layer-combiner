# PSD Processing Service

A Flask-based web service that processes PSD files to generate JPG variants by combining different layers.

## Features

- Accepts PSD files via file upload or URL
- Processes PSD files to generate all layer combinations
- Provides a RESTful API for integration with other services
- Supports custom output formats and quality settings
- Secure file handling with unique job IDs

## Prerequisites

- Python 3.8+
- pip (Python package manager)
- Google Cloud account (if using Google Drive integration)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd psd-processor
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. Copy the example environment file and update it with your settings:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file with your configuration:
   ```
   # Flask settings
   FLASK_APP=app.py
   FLASK_ENV=development
   SECRET_KEY=your-secret-key
   
   # File storage
   UPLOAD_FOLDER=/tmp/psd_uploads
   OUTPUT_FOLDER=/tmp/psd_outputs
   
   # Google Drive API (optional)
   GOOGLE_CREDENTIALS=path/to/credentials.json
   ```

## Running the Service

### Development Mode

```bash
flask run --host=0.0.0.0 --port=5000
```

### Production Mode

For production, use Gunicorn:

```bash
gunicorn --bind 0.0.0.0:5000 app:app
```

## API Endpoints

### Health Check

```
GET /api/health
```

### Process PSD

```
POST /api/process
```

**Request Headers:**
```
Content-Type: multipart/form-data
```

**Form Data:**
- `file`: PSD file to process (either this or `url` is required)
- `url`: URL of PSD file to download and process (either this or `file` is required)
- `output_format`: Output image format (default: 'jpg')
- `quality`: JPEG quality (1-100, default: 90)

**Response:**
```json
{
  "job_id": "unique-job-id",
  "status": "completed",
  "input_file": "filename.psd",
  "output_dir": "/path/to/output/dir",
  "generated_files": ["file1.jpg", "file2.jpg"],
  "success": true
}
```

### Download Generated File

```
GET /api/results/<job_id>/<filename>
```

## Integration with Make.com

1. In Make.com, create a new scenario with a Google Drive trigger that watches for new files in your PSD uploads folder.

2. Add an HTTP request module with the following configuration:
   - Method: POST
   - URL: `https://your-service-url/api/process`
   - Body type: Form Data
   - Add a file parameter with the PSD file from the Google Drive trigger
   
3. Add error handling and notifications as needed.

## Deployment

### PythonAnywhere

1. Upload your code to a Git repository
2. Create a new Web App in PythonAnywhere
3. Set up a virtual environment and install dependencies
4. Configure the web app to use your WSGI file
5. Set up environment variables in the Web tab

### Docker

A `Dockerfile` is provided for containerized deployment:

```bash
docker build -t psd-processor .
docker run -p 5000:5000 psd-processor
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
