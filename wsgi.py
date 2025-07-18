import sys
import os

# Add your project directory to the Python path
path = '/home/yourusername/psd-processor'  # Update with your PythonAnywhere username
if path not in sys.path:
    sys.path.append(path)

# Import your Flask app
from app import app as application

# Set up logging
import logging
logging.basicConfig(stream=sys.stderr)