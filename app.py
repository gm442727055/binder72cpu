#!/usr/bin/env python3
# app.py
from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string, abort, session, jsonify, render_template
import os
import urllib.parse # For safe URL encoding
from flask_uploads import UploadSet, configure_uploads, ALL
import time
from werkzeug.utils import secure_filename # Import for security

UPLOAD_FOLDER = os.path.abspath('uploads') # Use absolute path for security, relative to THIS file's location
# If uploads dir is at same level as file_service dir, you might need '../uploads' or full path
# UPLOAD_FOLDER = os.path.abspath('../uploads') # Example if uploads is outside file_service
# Or explicitly define the path
# UPLOAD_FOLDER = "/home/node/.openclaw/workspace/wenjian/uploads"

ALLOWED_EXTENSIONS = {'*'} # Allow any extension (using flask-uploads syntax)

PASSWORD = 'xiamuma' # Simple password. For production, use environment variables or secure storage.

# Define the sub-path where the application will be served
SUB_PATH = '/wenjian'
# Construct the full script name that Flask expects
SCRIPT_NAME = SUB_PATH

app = Flask(__name__)
app.secret_key = 'your_secret_key_here' # Change this to a random secret key for security in production!
# Set APPLICATION_ROOT to inform Flask about the sub-path
app.config.update(
    SECRET_KEY='your_secret_key_here',
    UPLOADED_FILES_DEST=UPLOAD_FOLDER,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024 * 1024, # 16GB limit
    APPLICATION_ROOT=SUB_PATH, # <-- This tells Flask its base URL path
    # SCRIPT_NAME=SCRIPT_NAME  # Alternative method, often used with proxies; APPLICATION_ROOT is usually sufficient for routing
)
# Configure UploadSet *before* ensuring directory exists
files = UploadSet('files', ALL) # Allows all file types
configure_uploads(app, files)


# Store upload progress (in a real app, use Redis, DB, or shared memory for multi-worker scenarios)
upload_progress = {}

def allowed_file(filename):
    # Flask-Uploads handles this based on configuration
    return True

# Decorator to require password for certain routes
def require_password(f):
    def decorated_function(*args, **kwargs):
        # Check if user is logged in
        if not session.get('logged_in'):
            # Redirect to login, preserving the intended next URL relative to the sub-path
            next_url = request.url.replace(request.url_root, '') # Get path relative to root
            # Ensure we pass the correct path including sub-path to url_for
            # Important: url_for might not automatically prepend APPLICATION_ROOT for 'next' arg in redirect
            # So construct the full path manually if necessary, but usually url_for('index') works due to APPLICATION_ROOT
            # The original approach should work fine with APPLICATION_ROOT set
            return redirect(url_for('login', next=next_url))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__ # Necessary for Flask
    return decorated_function

# HTML template for the login page - ADJUST URL FORM ACTION TO INCLUDE SUBPATH
LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Login Required</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f4; display: flex; justify-content: center; align-items: center; height: 100vh; }
        .login-container { width: 300px; padding: 20px; background: white; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        h2 { text-align: center; color: #333; }
        form { display: flex; flex-direction: column; }
        input[type="password"] { padding: 10px; margin-bottom: 10px; border: 1px solid #ccc; border-radius: 4px; }
        input[type="submit"] { background-color: #4CAF50; color: white; padding: 10px; border: none; border-radius: 4px; cursor: pointer; }
        input[type="submit"]:hover { background-color: #45a049; }
        .error { color: red; text-align: center; }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>Login Required</h2>
        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}
        <!-- IMPORTANT: Action must point to the login route under the sub-path -->
        <form method="post" action="{{ url_for('login') }}">
            <input type="password" name="password" placeholder="Enter Password" required>
            <input type="submit" value="Login">
        </form>
    </div>
</body>
</html>
'''

# HTML template for the main page (upload/download) - UPDATED for progress bar and SUBPATH
INDEX_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Caddy File Service</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f4; }
        .container { max-width: 800px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        h1, h2 { color: #333; }
        form { margin-bottom: 20px; }
        input[type="file"] { margin-right: 10px; }
        input[type="submit"] { background-color: #4CAF50; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; }
        input[type="submit"]:hover { background-color: #45a049; }
        input[type="submit"][disabled] { background-color: #cccccc; cursor: not-allowed; }
        ul { list-style-type: none; padding: 0; }
        li { padding: 8px; margin: 5px 0; background-color: #f9f9f9; border-left: 4px solid #4CAF50; word-break: break-all; }
        a { text-decoration: none; color: #007bff; font-weight: bold; }
        a:hover { text-decoration: underline; }
        .error { color: red; }
        .logout-link { float: right; }
        /* Progress Bar Styles */
        .progress-container { width: 100%; background-color: #f0f0f0; border-radius: 4px; overflow: hidden; margin-top: 10px; }
        .progress-bar { height: 20px; background-color: #4CAF50; width: 0%; transition: width 0.3s ease; }
        .progress-text { margin-top: 5px; font-size: 0.9em; color: #555; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Caddy File Upload & Download Service</h1>
        <a href="{{ url_for('logout') }}" class="logout-link">Logout</a>
        <h2>Upload File</h2>
        <!-- IMPORTANT: Action must point to the upload route under the sub-path -->
        <form id="uploadForm" method="POST" action="{{ url_for('upload_file') }}" enctype="multipart/form-data">
            <input type="file" name="file" id="fileInput" required>
            <input type="submit" value="Upload File" id="uploadButton">
        </form>
        <div id="progressContainer" style="display: none;">
            <div class="progress-container">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            <div class="progress-text" id="progressText">0%</div>
        </div>

        <h2>Download Files</h2>
        {% if files %}
            <ul>
            {% for filename in files %}
                <!-- IMPORTANT: Link must point to the download route under the sub-path -->
                <li><a href="{{ url_for('download_file', filename=filename) }}" target="_blank">{{ filename }}</a></li>
            {% endfor %}
            </ul>
        {% else %}
            <p>No files available for download.</p>
        {% endif %}
    </div>

    <script>
        document.getElementById('uploadForm').addEventListener('submit', function(e) {
            e.preventDefault(); // Prevent default form submission

            const fileInput = document.getElementById('fileInput');
            const file = fileInput.files[0];
            if (!file) {
                alert("Please select a file.");
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            // Use the action attribute from the form itself, which now includes the sub-path
            const actionUrl = document.getElementById('uploadForm').action;

            const xhr = new XMLHttpRequest();

            // Show progress container
            const progressContainer = document.getElementById('progressContainer');
            const progressBar = document.getElementById('progressBar');
            const progressText = document.getElementById('progressText');
            const uploadButton = document.getElementById('uploadButton');
            const uploadForm = document.getElementById('uploadForm');

            progressContainer.style.display = 'block';
            uploadButton.disabled = true; // Disable button during upload
            uploadForm.style.opacity = '0.6'; // Dim form during upload

            // Handle upload progress
            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const percentComplete = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = percentComplete + '%';
                    // Calculate speed (simple average over the duration so far)
                    const elapsed = (Date.now() - startTime) / 1000; // in seconds
                    const speedBps = e.loaded / elapsed;
                    const speedKbps = (speedBps / 1024).toFixed(2);
                    const speedMbps = (speedBps / (1024 * 1024)).toFixed(2);
                    let speedStr = speedBps < 1024 ? `${speedBps.toFixed(2)} B/s` : speedBps < (1024 * 1024) ? `${speedKbps} KB/s` : `${speedMbps} MB/s`;
                    progressText.textContent = `${percentComplete}% (${speedStr})`;
                }
            });

            // Handle completion
            xhr.addEventListener('load', function() {
                if (xhr.status === 200) {
                    // Reload page or update UI as needed after successful upload
                    location.reload(); // Simplest way to refresh the file list
                } else {
                    console.error("Upload failed:", xhr.statusText);
                    alert("Upload failed. Please try again.");
                     // Reset UI on failure
                    uploadButton.disabled = false;
                    uploadForm.style.opacity = '1';
                    progressContainer.style.display = 'none';
                }
            });

            // Handle errors
            xhr.addEventListener('error', function() {
                console.error("Upload error:", xhr.statusText);
                alert("Upload error occurred.");
                 // Reset UI on error
                uploadButton.disabled = false;
                uploadForm.style.opacity = '1';
                progressContainer.style.display = 'none';
            });

            const startTime = Date.now();
            xhr.open('POST', actionUrl); // Use the action URL from the form
            xhr.send(formData);
        });
    </script>
</body>
</html>
'''


@app.route(SUB_PATH + '/login', methods=['GET', 'POST']) # <-- Update route to include sub-path
def login():
    if request.method == 'POST':
        password_attempt = request.form.get('password')
        if password_attempt == PASSWORD:
            session['logged_in'] = True
            # Get the 'next' parameter, defaulting to the index page under the sub-path
            next_url = request.args.get('next', url_for('index')) # url_for respects APPLICATION_ROOT
            # Ensure next_url is relative to the sub-path context if it's an absolute path
            if next_url.startswith(SUB_PATH):
                 return redirect(next_url)
            else:
                # If next_url doesn't start with SUB_PATH but should, prepend it.
                # This handles cases where 'next' might come back without the prefix.
                # However, the redirect logic inside require_password should handle this correctly.
                # The simple redirect(url_for(...)) should work because url_for uses APPLICATION_ROOT.
                return redirect(next_url)
        else:
            return render_template_string(LOGIN_HTML, error="Incorrect password.")
    else: # GET request
        return render_template_string(LOGIN_HTML)


@app.route(SUB_PATH + '/logout') # <-- Update route to include sub-path
def logout():
    session.pop('logged_in', None)
    # Redirect to login under the sub-path
    return redirect(url_for('login')) # url_for respects APPLICATION_ROOT


@app.route(SUB_PATH + '/') # <-- Update route to include sub-path
@require_password
def index():
    try:
        files = []
        for f in os.listdir(app.config['UPLOADED_FILES_DEST']):
            file_path = os.path.join(app.config['UPLOADED_FILES_DEST'], f)
            if os.path.isfile(file_path):
                 files.append(f)
        files.sort()
        return render_template_string(INDEX_HTML, files=files)
    except OSError as e:
        print(f"Error reading upload directory: {e}")
        return "<div class='container'><h2>Error</h2><p class='error'>Could not read the file directory.</p><a href='{}'>Go Back</a></div>".format(url_for('index')), 500 # Use url_for for internal link


@app.route(SUB_PATH + '/upload', methods=['GET', 'POST']) # <-- Update route to include sub-path
@require_password
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template_string('<div class="container"><h2>Upload Error</h2><p class="error">No file part in the request.</p><a href="{}">Go Back</a></div>'.format(url_for('index'))), 400 # Use url_for for internal link
        file = request.files['file']
        if file.filename == '':
            return render_template_string('<div class="container"><h2>Upload Error</h2><p class="error">No file selected.</p><a href="{}">Go Back</a></div>'.format(url_for('index'))), 400 # Use url_for for internal link
        if file and allowed_file(file.filename):
            # Secure the filename for safety
            filename = secure_filename(file.filename)
            # Use flask-uploads to save the file
            filename = files.save(file, name=filename)
            return '', 200 # Return empty response for success, page reloads via JS
        else:
            return render_template_string('<div class="container"><h2>Upload Error</h2><p class="error">File upload failed due to validation rules.</p><a href="{}">Go Back</a></div>'.format(url_for('index'))), 400 # Use url_for for internal link
    else: # GET request to /upload -> redirect to index under sub-path
         return redirect(url_for('index')) # url_for respects APPLICATION_ROOT


@app.route(SUB_PATH + '/download/<path:filename>') # <-- Update route to include sub-path
def download_file(filename):
    # Add password protection here too, as mentioned previously for security
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if '..' in filename or filename.startswith('/'):
         abort(404)
    filepath = os.path.join(app.config['UPLOADED_FILES_DEST'], filename)
    if os.path.commonpath([app.config['UPLOADED_FILES_DEST']]) != os.path.commonpath([app.config['UPLOADED_FILES_DEST'], filepath]):
         abort(404)
    if not os.path.isfile(filepath):
         abort(404)
    try:
         return send_from_directory(app.config['UPLOADED_FILES_DEST'], filename, as_attachment=True)
    except FileNotFoundError:
         abort(404)


if __name__ == '__main__':
    # Configure UploadSet first
    # files = UploadSet('files', ALL) # Moved up before configure_uploads
    configure_uploads(app, files) # This must happen before the directory check below if it modifies config

    # Ensure the upload folder exists *after* configuring uploads, just in case
    # Make sure UPLOAD_FOLDER points to the correct location
    print(f"Ensuring upload directory exists: {app.config['UPLOADED_FILES_DEST']}")
    os.makedirs(app.config['UPLOADED_FILES_DEST'], exist_ok=True)

    # Note: When running directly with app.run, the host/port are used.
    # If running behind a proxy like Caddy, you might need to consider proxy headers.
    # For direct access via app.run, this is fine.
    app.run(debug=False, host='127.0.0.1', port=44056, threaded=True)
