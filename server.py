from flask import Flask, request, render_template, redirect, url_for, session, flash, Response, send_file
import os
import requests
import time
import io
import threading
import socket
import datetime
import hashlib
import secrets
import uuid # Added for unique IDs
import logging
import atexit
import fcntl
import sys

# Optional psutil import for process monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not available. Process monitoring features will be limited.")

from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import cv2
import numpy as np
from google import genai
from google.genai import types

app = Flask(__name__)
# Use a strong random secret key
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
# Set session to expire after the longer duration to let our custom logic handle timeouts
app.permanent_session_lifetime = datetime.timedelta(days=30)  # Use the longer duration

# Configure logging for person detection
logging.basicConfig(level=logging.INFO)

# Create a dedicated logger for person detection
person_logger = logging.getLogger('person_detection')
person_logger.setLevel(logging.DEBUG)

# Create file handler for person detection logs
if not os.path.exists('logs'):
    os.makedirs('logs')

person_log_handler = logging.FileHandler('logs/person_detection.log')
person_log_handler.setLevel(logging.INFO)

# Create console handler for person detection
person_console_handler = logging.StreamHandler()
person_console_handler.setLevel(logging.INFO)

# Create formatter
person_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
person_log_handler.setFormatter(person_formatter)
person_console_handler.setFormatter(person_formatter)

# Add handlers to logger
person_logger.addHandler(person_log_handler)
person_logger.addHandler(person_console_handler)

# Prevent duplicate logs
person_logger.propagate = False

# Session duration constants
DEFAULT_SESSION_LIFETIME = datetime.timedelta(hours=1)  # 1 hour
REMEMBER_ME_LIFETIME = datetime.timedelta(days=30)      # 30 days

# Simple in-memory user database
users = {
    "admin": {
        "password_hash": "scrypt:32768:8:1$i5jNdDrzrubCBYyP$13216c1446d99f31ac24502bc5da50f48ec6040d7a6254cd28f8f745d057e9ee044ad3a60462d52111778811d9a2720587f9ee3b0087c859abb4bb538454e6e5",
        "failed_attempts": 0,
        "locked_until": None,
        "last_activity": time.time(),
        "role": "admin"
    }
}

# Login attempt tracking
login_attempts = {}
# IP-based rate limiting
ip_attempts = {}
# Maximum failed attempts before temporary lockout
MAX_FAILED_ATTEMPTS = 5
# Lockout duration in seconds (10 minutes)
LOCKOUT_DURATION = 600

# Directory for saving person detection images
PERSON_IMAGE_DIR = 'detected_persons'

# State for person detection
# Stores {'camera_id': {'person_present': bool, 'last_detection': timestamp, 'first_detection': timestamp, 'detection_count': int}}
person_detection_state = {}

# Image save rate limiting - minimum time between saves when person is continuously present (in seconds)
MIN_IMAGE_SAVE_INTERVAL = 60  # Save image at most every 60 seconds when person is continuously present

# Per-camera locks for thread-safe person detection
camera_detection_locks = {}
camera_lock_creation_lock = threading.Lock()

def get_camera_lock(camera_id):
    """Get or create a lock for the specified camera_id in a thread-safe manner."""
    with camera_lock_creation_lock:
        if camera_id not in camera_detection_locks:
            camera_detection_locks[camera_id] = threading.Lock()
            person_logger.debug(f"Created detection lock for {camera_id}")
        return camera_detection_locks[camera_id]

# Rate limiting
def is_rate_limited(ip):
    current_time = time.time()
    if ip not in ip_attempts:
        ip_attempts[ip] = {"attempts": 0, "reset_time": current_time + 60}
        return False
    
    # Reset count after 1 minute
    if current_time > ip_attempts[ip]["reset_time"]:
        ip_attempts[ip] = {"attempts": 0, "reset_time": current_time + 60}
        return False
    
    # Limit to 10 attempts per minute
    if ip_attempts[ip]["attempts"] >= 10:
        return True
    
    ip_attempts[ip]["attempts"] += 1
    return False

# Require login for protected routes
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        
        # Check if user still exists
        if session['username'] not in users:
            session.clear()
            return redirect(url_for('login'))
            
        # Update last activity time
        users[session['username']]['last_activity'] = time.time()
        
        # Check for session timeout
        last_active = session.get('last_active', 0)
        session_created = session.get('session_created', 0)
        current_time = time.time()
        
        # If remember_me is set, use the longer timeout
        if session.get('remember_me', False):
            inactivity_timeout = REMEMBER_ME_LIFETIME.total_seconds()
            absolute_timeout = REMEMBER_ME_LIFETIME.total_seconds()
        else:
            inactivity_timeout = DEFAULT_SESSION_LIFETIME.total_seconds()
            absolute_timeout = DEFAULT_SESSION_LIFETIME.total_seconds()
            
        # Check if session has timed out due to inactivity
        time_since_last_active = current_time - last_active
        if time_since_last_active > inactivity_timeout:
            print(f"Session timeout due to inactivity for {session['username']} after {time_since_last_active} seconds")
            session.clear()
            return redirect(url_for('login'))
            
        # Check if session has exceeded absolute lifetime (for security)
        time_since_creation = current_time - session_created
        if time_since_creation > absolute_timeout:
            print(f"Session timeout due to absolute lifetime for {session['username']} after {time_since_creation} seconds")
            session.clear()
            return redirect(url_for('login'))
            
        # Update last active time
        session['last_active'] = current_time
        
        return f(*args, **kwargs)
    return decorated_function

# Clean up inactive sessions
def cleanup_inactive_sessions():
    while True:
        time.sleep(300)  # Check every 5 minutes
        current_time = time.time()
        
        # Reset locked accounts after lockout period
        for username, user_data in users.items():
            if user_data.get('locked_until') and current_time > user_data['locked_until']:
                users[username]['locked_until'] = None
                users[username]['failed_attempts'] = 0
                print(f"Account unlocked: {username}")

# Global variables
cameras = {}
active_streams = {}
active_connections = {}

# Path to placeholder image
PLACEHOLDER_PATH = os.path.join(app.static_folder, 'placeholder.svg')

# Base camera configuration
base_cameras = {
    "camera1": {
        "name": "Camera 1",
        "url": "http://localhost:10001/stream"  # Internal URL not exposed to clients
    },
    "camera2": {
        "name": "Camera 2",
        "url": "http://localhost:10002/stream"  # Internal URL not exposed to clients
    }
}

# Dynamic camera detection
def scan_for_cameras():
    """Scan for available cameras on ports starting from 10001 in steps of 2."""
    available_cameras = {}
    # Scan base ports 10001, 10003, ... up to 10099
    for stream_port in range(10001, 10100, 2):
        capture_port = stream_port + 1
        host = 'localhost'

        # Check if stream port is open and has /stream
        stream_url = f"http://{host}:{stream_port}/stream"
        stream_responsive = False
        if is_port_open(host, stream_port):
            try:
                resp_stream = requests.get(stream_url, timeout=1, stream=True)
                if resp_stream.status_code >= 200 and resp_stream.status_code < 300:
                    stream_responsive = True
                    print(f"Found responsive /stream endpoint on port {stream_port}")
                else:
                    print(f"/stream endpoint on port {stream_port} returned status {resp_stream.status_code}")
                resp_stream.close()
            except requests.exceptions.RequestException as e:
                print(f"Could not connect to /stream for potential camera on port {stream_port}: {e}")
        
        # Check if capture port is open and has /capture
        capture_url = f"http://{host}:{capture_port}/capture"
        capture_responsive = False
        if is_port_open(host, capture_port):
            try:
                # Use HEAD request for efficiency if only checking existence
                resp_capture = requests.get(capture_url, timeout=1, stream=True)
                if resp_capture.status_code >= 200 and resp_capture.status_code < 300:
                    capture_responsive = True
                    print(f"Found responsive /capture endpoint on port {capture_port}")
                else:
                     print(f"/capture endpoint on port {capture_port} returned status {resp_capture.status_code}")
                resp_capture.close()
            except requests.exceptions.RequestException as e:
                print(f"Could not connect to /capture for potential camera on port {capture_port}: {e}")

        # If both endpoints are responsive, add the camera
        if stream_responsive and capture_responsive:
            camera_id = f"camera{(stream_port - 10001) // 2 + 1}" # camera1, camera2, etc.
            available_cameras[camera_id] = {
                "name": f"Camera {(stream_port - 10001) // 2 + 1}",
                "stream_url": stream_url,
                "capture_url": capture_url,
                "stream_port": stream_port,
                "capture_port": capture_port
            }
            print(f"Successfully added camera {camera_id} (Stream: {stream_port}, Capture: {capture_port})")

    return available_cameras

def is_port_open(host, port, timeout=1):
    """Check if a port is open on the given host"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        print(f"Connected to {host}:{port}")

        s.shutdown(socket.SHUT_RDWR)
        return True
       
    except:
        return False
    finally:
        s.close()

# Initial camera scan
cameras = scan_for_cameras()

# Clean up stale connections
def cleanup_connections():
    """Clean up stale camera connections"""
    while True:
        time.sleep(60)  # Check every minute
        current_time = time.time()
        connections_to_remove = []
        
        for conn_id, conn_info in active_connections.items():
            # If connection is older than 5 minutes without activity, close it
            if current_time - conn_info['last_access'] > 300:
                print(f"Cleaning up stale connection {conn_id}")
                try:
                    # Check if response has a close method
                    if hasattr(conn_info['response'], 'close') and callable(conn_info['response'].close):
                        conn_info['response'].close()
                except Exception as e:
                    print(f"Error closing stale connection {conn_id}: {e}")
                connections_to_remove.append(conn_id)
        
        # Remove closed connections
        for conn_id in connections_to_remove:
            del active_connections[conn_id]
            
        print(f"Active connections: {len(active_connections)}")

cleanup_thread = threading.Thread(target=cleanup_connections, daemon=True)
cleanup_thread.start()

# Start session cleanup thread
session_cleanup_thread = threading.Thread(target=cleanup_inactive_sessions, daemon=True)
session_cleanup_thread.start()

# FPS calculation variables
frame_times = {} # Dictionary to store last frame time per camera stream
FPS_ROLLING_AVG_COUNT = 10 # Number of frames to average FPS over

@app.before_request
def log_request_info():
    """Log the origin IP and path for every request."""
    if request.endpoint != 'static': # Avoid logging static file requests
        print(f"Request from IP: {request.remote_addr} to path: {request.path}")

@app.route('/')
@login_required
def home():
    # Trigger a fresh camera scan
    global cameras
    cameras = scan_for_cameras()

    print("cameras", cameras)
    
    # Update camera connection status based on stream port
    for camera_id, camera_config in cameras.items():
        stream_port = camera_config.get('stream_port', 0)
        camera_config['is_connected'] = is_port_open('localhost', stream_port)
    
    return render_template(
        'dashboard.html',
        username=session['username'],
        cameras=cameras,
        camera_count=len(cameras),
        timestamp=int(time.time())
    )

@app.route('/snapshot/<camera_id>')
@login_required
def camera_snapshot(camera_id):
    global cameras
    # Verify camera exists
    if camera_id not in cameras:
        # Attempt to rescan if camera is not found, it might be a new one.
        # To keep it simple, we'll try to find a stream port that would match the ID.
        # e.g., camera1 -> stream_port 10001, camera2 -> stream_port 10003
        try:
            camera_num = int(camera_id.replace('camera', ''))
            potential_stream_port = 10001 + (camera_num - 1) * 2
            potential_capture_port = potential_stream_port + 1

            # Check if corresponding stream and capture ports are open
            if is_port_open('localhost', potential_stream_port) and is_port_open('localhost', potential_capture_port):
                print(f"Potential new camera {camera_id} detected by ports, rescanning...")
                cameras = scan_for_cameras() # Rescan to populate details
            else:
                print(f"Ports for {camera_id} not found, redirecting to placeholder.")
                return redirect(url_for('placeholder_image'))

        except ValueError:
            # Invalid camera_id format
            print(f"Invalid camera_id format for snapshot: {camera_id}")
            return redirect(url_for('placeholder_image'))
        
        # Check again after scan
        if camera_id not in cameras:
            print(f"Camera {camera_id} not found after rescan, redirecting to placeholder.")
            return redirect(url_for('placeholder_image'))
    
    camera_config = cameras[camera_id]
    if 'capture_url' not in camera_config:
        print(f"Capture URL not configured for {camera_id}")
        return redirect(url_for('placeholder_image'))

    try:
        capture_url = camera_config['capture_url']
        # Make a GET request to the capture URL
        resp = requests.get(capture_url, timeout=5) # Increased timeout slightly for capture
        
        if resp.status_code == 200:
            content_type = resp.headers.get('content-type', 'image/jpeg') # Default to jpeg
            # Return the image content directly
            return Response(resp.content, content_type=content_type)
        else:
            print(f"Error {resp.status_code} getting snapshot from {capture_url} for {camera_id}")
            return redirect(url_for('placeholder_image'))
            
    except requests.exceptions.Timeout:
        print(f"Timeout getting snapshot for {camera_id} from {capture_url}")
        return redirect(url_for('placeholder_image'))
    except Exception as e:
        print(f"Error getting snapshot for {camera_id}: {e}")
        return redirect(url_for('placeholder_image'))

@app.route('/cameras')
def camera_list():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Redirect to home page which now shows all cameras
    return redirect(url_for('home'))

@app.route('/camera/<camera_id>')
@login_required
def view_camera(camera_id):
    global cameras
    if camera_id not in cameras:
        # Optional: attempt a rescan if camera not found, similar to snapshot endpoint
        # For simplicity, we'll rely on the dashboard's scan for now.
        return "Camera not found. <a href='/'>Back to Dashboard</a>", 404
        
    camera_config = cameras[camera_id]
    stream_port = camera_config.get('stream_port', 0)
    # is_connected status here refers to the stream port for the live view page
    is_connected = is_port_open('localhost', stream_port)
    
    # Pass the entire camera_config to the template for flexibility
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{camera_config["name"]} - Live Stream</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1 {{ color: #333; }}
            .stream-container {{ 
                max-width: 100%; 
                text-align: center;
                margin: 20px 0;
                background: #f9f9f9;
                border-radius: 8px;
                padding: 20px;
            }}
            .stream-container img {{ 
                max-width: 100%; 
                border: 1px solid #ddd;
                border-radius: 8px;
                background: white;
                object-fit: contain;
            }}
            .nav {{ 
                margin-top: 20px;
            }}
            a {{ 
                color: #0066cc; 
                text-decoration: none;
                margin-right: 15px;
            }}
            a:hover {{ 
                text-decoration: underline; 
            }}
            .status-indicator {{
                display: inline-block;
                margin-left: 10px;
                padding: 5px 10px;
                border-radius: 4px;
                background: #f0f0f0;
                color: #666;
                font-size: 14px;
            }}
            .status-connected {{ color: green; }}
            .status-disconnected {{ color: red; }}
            .button-disabled {{
                opacity: 0.5;
                cursor: not-allowed;
            }}
            .control-button {{
                display: inline-block;
                padding: 8px 15px;
                margin-right: 10px;
                border-radius: 4px;
                text-decoration: none;
                font-weight: bold;
                cursor: pointer;
                color: white;
                border: none;
                font-size: 14px;
            }}
            .pause-button {{ background-color: #f0ad4e; }}
            .pause-button:hover {{ background-color: #ec971f; text-decoration: none; }}
            .resume-button {{ background-color: #5cb85c; }}
            .resume-button:hover {{ background-color: #449d44; text-decoration: none; }}
        </style>
        <script>
            let streamImg = null;
            let streamActive = {str(is_connected).lower()};
            let pauseCheckInterval = null;
            let cameraConnected = {str(is_connected).lower()};
            
            // When page loads
            window.addEventListener('load', function() {{
                streamImg = document.getElementById('stream');
                updateButtonStates();
                
                if (cameraConnected) {{
                    startStreamManagement();
                }} else {{
                    // If camera is offline, show placeholder immediately
                    if (streamImg) {{
                        streamImg.src = '/placeholder?t=' + new Date().getTime();
                        
                        const statusIndicator = document.getElementById('status-indicator');
                        if (statusIndicator) {{
                            statusIndicator.textContent = 'Offline';
                            statusIndicator.className = 'status-indicator status-disconnected';
                        }}
                    }}
                    
                    // Disable buttons as needed
                    updateButtonStates();
                }}
            }});
            
            // Update button states based on current status
            function updateButtonStates() {{
                const pauseBtn = document.getElementById('pause-btn');
                const resumeBtn = document.getElementById('resume-btn');
                
                if (pauseBtn && resumeBtn) {{
                    // Handle pause button
                    if (!cameraConnected || !streamActive) {{
                        // Disable pause if camera is offline or stream is already paused
                        pauseBtn.classList.add('button-disabled');
                        pauseBtn.onclick = function(e) {{
                            e.preventDefault();
                            alert('Stream is already paused or camera is offline.');
                        }};
                    }} else {{
                        // Enable pause if stream is active
                        pauseBtn.classList.remove('button-disabled');
                        pauseBtn.onclick = stopStream;
                    }}
                    
                    // Handle resume button
                    if (!cameraConnected || streamActive) {{
                        // Disable resume if camera is offline or already streaming
                        resumeBtn.classList.add('button-disabled');
                        resumeBtn.onclick = function(e) {{
                            e.preventDefault();
                            if (!cameraConnected) {{
                                alert('Camera is offline. Cannot resume stream.');
                            }} else if (streamActive) {{
                                alert('Stream is already active.');
                            }}
                        }};
                    }} else {{
                        // Enable resume if paused and camera is online
                        resumeBtn.classList.remove('button-disabled');
                        resumeBtn.onclick = restartStream;
                    }}
                }}
            }}
            
            // When user navigates away
            window.addEventListener('beforeunload', function() {{
                stopStream();
            }});
            
            // Handle page visibility changes
            document.addEventListener('visibilitychange', function() {{
                if (document.visibilityState === 'hidden') {{
                    // User switched tabs or minimized
                    stopStream();
                }} else if (document.visibilityState === 'visible' && !streamActive && cameraConnected) {{
                    // User returned to tab and camera is connected
                    restartStream();
                }}
            }});
            
            function startStreamManagement() {{
                const statusIndicator = document.getElementById('status-indicator');
                
                // Check if stream is frozen every 5 seconds
                pauseCheckInterval = setInterval(function() {{
                    if (!streamActive) return;
                    
                    // Update status text
                    if (streamImg) {{
                        if (statusIndicator) {{
                            statusIndicator.textContent = 'Connected';
                            statusIndicator.className = 'status-indicator status-connected';
                        }}
                    }}
                }}, 5000);
            }}
            
            function stopStream() {{
                // Don't do anything if already paused
                if (!streamActive) return;
                
                streamActive = false;
                
                // Replace stream with placeholder
                if (streamImg) {{
                    const originalSrc = streamImg.getAttribute('data-original-src');
                    streamImg.src = '/placeholder?t=' + new Date().getTime();
                    streamImg.setAttribute('data-original-src', originalSrc);
                    
                    const statusIndicator = document.getElementById('status-indicator');
                    if (statusIndicator) statusIndicator.textContent = 'Paused';
                }}
                
                // Call the server to stop the connection
                fetch('/stop-stream/{camera_id}', {{ method: 'POST' }});
                
                // Update button states
                updateButtonStates();
            }}
            
            function restartStream() {{
                // Don't do anything if already streaming or camera offline
                if (streamActive || !cameraConnected) return;
                
                streamActive = true;
                
                // Restore original stream
                if (streamImg) {{
                    const originalSrc = streamImg.getAttribute('data-original-src');
                    if (originalSrc) {{
                        streamImg.src = originalSrc + '?t=' + new Date().getTime();
                        
                        const statusIndicator = document.getElementById('status-indicator');
                        if (statusIndicator) {{
                            statusIndicator.textContent = 'Connecting...';
                            
                            // Update status after a short delay
                            setTimeout(function() {{
                                if (statusIndicator) {{
                                    statusIndicator.textContent = 'Connected';
                                    statusIndicator.className = 'status-indicator status-connected';
                                }}
                            }}, 2000);
                        }}
                    }}
                }}
                
                // Update button states
                updateButtonStates();
            }}
            
            // Check camera connectivity
            function checkCameraConnection() {{
                fetch('/check-camera/{camera_id}')
                .then(response => response.json())
                .then(data => {{
                    const oldConnected = cameraConnected;
                    cameraConnected = data.connected;
                    
                    const statusIndicator = document.getElementById('status-indicator');
                    
                    if (cameraConnected) {{
                        // Camera is now connected
                        if (statusIndicator) {{
                            statusIndicator.textContent = streamActive ? 'Connected' : 'Paused';
                            statusIndicator.className = 'status-indicator' + (streamActive ? ' status-connected' : '');
                        }}
                        
                        // If camera newly connected, enable the appropriate buttons
                        if (!oldConnected) {{
                            updateButtonStates();
                        }}
                    }} else {{
                        // Camera is disconnected
                        if (statusIndicator) {{
                            statusIndicator.textContent = 'Offline';
                            statusIndicator.className = 'status-indicator status-disconnected';
                        }}
                        
                        // Show placeholder if camera disconnected while streaming
                        if (streamActive) {{
                            streamImg.src = '/placeholder?t=' + new Date().getTime();
                            streamActive = false;
                        }}
                        
                        // Update buttons
                        updateButtonStates();
                    }}
                }})
                .catch(err => console.error('Error checking camera connection:', err));
            }}
            
            // Check camera status periodically
            setInterval(checkCameraConnection, 10000);
            
            function handleImageError(img) {{
                img.src = '/placeholder?t=' + new Date().getTime();
                const statusIndicator = document.getElementById('status-indicator');
                if (statusIndicator) {{
                    statusIndicator.textContent = 'Offline';
                    statusIndicator.className = 'status-indicator status-disconnected';
                }}
                cameraConnected = false;
                streamActive = false;
                
                // Update button states
                updateButtonStates();
            }}
        </script>
    </head>
    <body>
        <h1>
            {camera_config["name"]} - Live Stream
            <span id="status-indicator" class="status-indicator {is_connected and 'status-connected' or 'status-disconnected'}">
                {is_connected and 'Connected' or 'Offline'}
            </span>
        </h1>
        
        <div class="stream-container">
            <img id="stream" 
                 src="{is_connected and f'/stream/{camera_id}?t={int(time.time())}' or '/placeholder'}" 
                 data-original-src="/stream/{camera_id}"
                 alt="{camera_config['name']} Live Stream" 
                 onerror="handleImageError(this)">
        </div>
        
        <div class="nav">
            <a href="/">Back to Dashboard</a>
            <a href="/detected-persons/{camera_id}">Person History</a>
            <a id="pause-btn" href="javascript:void(0);" 
               class="control-button pause-button {(not is_connected) and 'button-disabled' or ''}" 
               onclick="{is_connected and 'stopStream()' or ''}"
            >Pause Stream</a>
            <a id="resume-btn" href="javascript:void(0);" 
               class="control-button resume-button {(not is_connected) and 'button-disabled' or ''}" 
               onclick="{is_connected and 'restartStream()' or ''}"
            >Resume Stream</a>
            <a href="/logout">Logout</a>
        </div>
    </body>
    </html>
    '''

@app.route('/stop-stream/<camera_id>', methods=['POST'])
@login_required
def stop_stream(camera_id):
    """Endpoint to handle stream cleanup when user navigates away"""
    global active_streams, active_connections
    username = session['username']
    # Log that the stream was stopped
    print(f"Stream for {camera_id} stopped by user {username}")
    
    # Find and close the connections for this user and camera
    connections_to_close = []
    for conn_id, conn_info in active_connections.items():
        if conn_info['camera_id'] == camera_id and conn_info['username'] == username:
            connections_to_close.append(conn_id)
    
    # Close connections
    for conn_id in connections_to_close:
        try:
            conn_info = active_connections[conn_id]
            # Check if the response object has a close method instead of closed attribute
            if hasattr(conn_info['response'], 'close') and callable(conn_info['response'].close):
                conn_info['response'].close()
            del active_connections[conn_id]
            print(f"Closed connection {conn_id}")
        except Exception as e:
            print(f"Error closing connection {conn_id}: {e}")
    
    # Remove from active streams tracking
    if camera_id in active_streams and username in active_streams[camera_id]:
        del active_streams[camera_id][username]
    
    return "Stream stopped", 200

@app.route('/stream/<camera_id>')
@login_required
def stream_proxy(camera_id):
    global cameras, active_streams, frame_times
    # Verify camera exists
    if camera_id not in cameras:
        # Attempt to rescan, similar to snapshot logic
        try:
            camera_num = int(camera_id.replace('camera', ''))
            potential_stream_port = 10001 + (camera_num - 1) * 2
            potential_capture_port = potential_stream_port + 1
            if is_port_open('localhost', potential_stream_port) and is_port_open('localhost', potential_capture_port):
                cameras = scan_for_cameras()
        except ValueError:
            pass # Invalid ID format, will be caught below
        
        # Check again after scan
        if camera_id not in cameras:
            return "Camera not found. <a href='/'>Back to Dashboard</a>", 404
    
    camera_config = cameras[camera_id]
    if 'stream_url' not in camera_config or 'stream_port' not in camera_config:
        print(f"Stream URL or Port not configured for {camera_id}")
        return redirect(url_for('placeholder_image'))

    # Make sure the camera's stream port is connected before trying to stream
    stream_port = camera_config['stream_port']
    if not is_port_open('localhost', stream_port):
        print(f"Stream port {stream_port} for {camera_id} is not open.")
        return redirect(url_for('placeholder_image'))
    
    # Track this stream for the current user
    if camera_id not in active_streams:
        active_streams[camera_id] = {}
    active_streams[camera_id][session['username']] = time.time()
    
    # Initialize FPS tracking for this stream instance
    conn_id = f"{camera_id}_{session['username']}_{time.time()}"
    frame_times[conn_id] = {'times': [], 'last_time': time.time()}
    
    try:
        stream_url = camera_config['stream_url']
        resp = requests.get(stream_url, stream=True, timeout=10) # Increased timeout
        
        if resp.status_code == 200:
            # Get the boundary string for MJPEG
            content_type = resp.headers.get('content-type', '')
            boundary = None
            if 'multipart/x-mixed-replace' in content_type:
                parts = content_type.split(';')
                for part in parts:
                    if 'boundary=' in part:
                        boundary = part.split('=')[1].strip()
                        break
            
            if not boundary:
                print(f"Could not find boundary for MJPEG stream: {camera_id}")
                # Fallback or attempt to stream raw if not MJPEG? For now, redirect.
                return redirect(url_for('placeholder_image'))

            # Track the connection for cleanup
            active_connections[conn_id] = {
                'camera_id': camera_id,
                'username': session['username'],
                'response': resp,
                'created': time.time(),
                'last_access': time.time()
            }
            
            def generate():
                global frame_times
                buffer = b''
                last_frame_time = time.time()
                
                try:
                    for chunk in resp.iter_content(chunk_size=4096): # Process in smaller chunks
                        # Update last access time
                        if conn_id in active_connections:
                            active_connections[conn_id]['last_access'] = time.time()
                        else: # Connection closed by cleanup or stop_stream
                           break 

                        if not chunk:
                            continue

                        buffer += chunk
                        
                        # Check if connection should be closed externally
                        if conn_id not in active_connections:
                            print(f"Connection {conn_id} terminated externally.")
                            break

                        # Process buffer looking for frames
                        while True:
                            # Find the start of the boundary
                            start_boundary = buffer.find(b'--' + boundary.encode())
                            if start_boundary == -1:
                                break # Need more data

                            # Find the end of the boundary marker (start of headers)
                            end_boundary_marker = buffer.find(b'\r\n', start_boundary)
                            if end_boundary_marker == -1:
                                break # Need more data

                            # Find the start of the image data (after headers)
                            start_image = buffer.find(b'\r\n\r\n', end_boundary_marker)
                            if start_image == -1:
                                break # Need more data
                                
                            # We now have the headers between end_boundary_marker+2 and start_image
                            # header_part = buffer[end_boundary_marker+2:start_image]

                            # Find the start of the *next* boundary to get the end of the current image
                            next_boundary = buffer.find(b'--' + boundary.encode(), start_image + 4)
                            if next_boundary == -1:
                                break # Need more data for the complete frame

                            # Extract the image data
                            image_data = buffer[start_image + 4 : next_boundary]
                            
                            # Process the frame if it's not empty
                            if image_data:
                                try:
                                    # Decode frame
                                    np_arr = np.frombuffer(image_data, np.uint8)
                                    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                                    if frame is not None:
                                        # Calculate FPS
                                        current_time = time.time()
                                        time_diff = current_time - frame_times[conn_id]['last_time']
                                        frame_times[conn_id]['last_time'] = current_time
                                        
                                        if time_diff > 0:
                                            fps = 1.0 / time_diff
                                            # Use rolling average
                                            frame_times[conn_id]['times'].append(fps)
                                            if len(frame_times[conn_id]['times']) > FPS_ROLLING_AVG_COUNT:
                                                frame_times[conn_id]['times'].pop(0)
                                            avg_fps = sum(frame_times[conn_id]['times']) / len(frame_times[conn_id]['times'])
                                            fps_text = f"FPS: {avg_fps:.1f}"
                                        else:
                                            fps_text = "FPS: N/A"

                                        # Add FPS overlay
                                        cv2.putText(frame, fps_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)

                                        # Re-encode frame
                                        ret, buffer_encoded = cv2.imencode('.jpg', frame)
                                        if ret:
                                            frame_bytes = buffer_encoded.tobytes()
                                            
                                            # Yield the MJPEG part
                                            yield (b'--' + boundary.encode() + b'\r\n' +
                                                   b'Content-Type: image/jpeg\r\n' +
                                                   b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' +
                                                   frame_bytes + b'\r\n')
                                    else:
                                         print(f"Frame decoding failed for {camera_id}")

                                except Exception as decode_error:
                                    print(f"Error processing frame for {camera_id}: {decode_error}")
                                    # Optionally yield the original data if processing fails?
                                    # yield (b'--' + boundary.encode() + b'\r\n' +
                                    #       b'Content-Type: image/jpeg\r\n' + # Assuming it's jpeg
                                    #       b'Content-Length: ' + str(len(image_data)).encode() + b'\r\n\r\n' +
                                    #       image_data + b'\r\n')
                            
                            # Remove the processed part from the buffer
                            buffer = buffer[next_boundary:]

                except Exception as e:
                    print(f"Stream error for {camera_id} ({conn_id}): {e}")
                finally:
                    # Cleanup FPS tracking for this specific connection
                    if conn_id in frame_times:
                        del frame_times[conn_id]
                        
                    # Cleanup connection from active_connections when stream ends naturally
                    if conn_id in active_connections:
                        try:
                            response_obj = active_connections[conn_id]['response']
                            if hasattr(response_obj, 'close') and callable(response_obj.close):
                                response_obj.close()
                        except Exception as close_error:
                            print(f"Error closing stream connection during cleanup {conn_id}: {close_error}")
                        
                        del active_connections[conn_id]
                        print(f"Stream ended for {conn_id}")
            
            # Return the response with the generator
            return Response(generate(), content_type=f'multipart/x-mixed-replace; boundary={boundary}')
        else:
            # If camera returns an error, serve the placeholder
            print(f"Camera {camera_id} (stream URL: {stream_url}) returned status {resp.status_code}")
            return redirect(url_for('placeholder_image'))
            
    except requests.exceptions.Timeout:
        print(f"Timeout connecting to camera stream {camera_id}: {stream_url}")
        return redirect(url_for('placeholder_image'))
    except Exception as e:
        print(f"Error connecting to camera stream {camera_id} ({stream_url}): {e}")
        # Clean up FPS state if connection failed early
        if conn_id in frame_times:
            del frame_times[conn_id]
        return redirect(url_for('placeholder_image'))

@app.route('/placeholder')
@login_required
def placeholder_image():
    """Dedicated endpoint for serving the placeholder image"""
    try:
        if os.path.exists(PLACEHOLDER_PATH):
            with open(PLACEHOLDER_PATH, 'rb') as f:
                svg_content = f.read()
            
            # Ensure proper Content-Type header
            response = Response(svg_content, mimetype='image/svg+xml')
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        else:
            # Fallback SVG if file doesn't exist
            svg = '''<svg width="320" height="240" xmlns="http://www.w3.org/2000/svg">
                <rect width="320" height="240" fill="#f0f0f0"/>
                <rect x="10" y="10" width="300" height="220" rx="8" fill="#e0e0e0" stroke="#ccc" stroke-width="2"/>
                <circle cx="160" cy="100" r="50" fill="#d0d0d0" stroke="#bbb" stroke-width="2"/>
                <circle cx="160" cy="100" r="25" fill="#c0c0c0" stroke="#aaa" stroke-width="2"/>
                <rect x="80" y="160" width="160" height="30" rx="5" fill="#d0d0d0" stroke="#bbb" stroke-width="2"/>
                <text x="160" y="180" font-family="Arial" font-size="16" text-anchor="middle" fill="#666">Camera Offline</text>
            </svg>'''
            
            response = Response(svg, mimetype='image/svg+xml')
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
    except Exception as e:
        print(f"Error serving placeholder: {e}")
        return "Camera Offline", 503

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Clear any existing session
    if 'username' in session:
        session.clear()
        
    error_message = None
    
    if request.method == 'POST':
        ip = request.remote_addr
        
        # Check for rate limiting
        if is_rate_limited(ip):
            return render_template('rate_limited.html'), 429
            
        username = request.form['username']
        password = request.form['password']
        remember_me = 'remember' in request.form
        
        # Check if user exists
        if username in users:
            user = users[username]
            
            # Check if account is locked
            if user.get('locked_until') and time.time() < user['locked_until']:
                lock_minutes = int((user['locked_until'] - time.time()) / 60) + 1
                error_message = f"Account is locked. Please try again after {lock_minutes} minutes."
            elif check_password_hash(user['password_hash'], password):
                # Successful login
                user['failed_attempts'] = 0
                
                # Set up the session
                session.permanent = True
                session['username'] = username
                session['last_active'] = time.time()
                session['session_created'] = time.time()  # Track when session was created
                session['ip'] = request.remote_addr
                session['user_agent'] = request.user_agent.string
                session['remember_me'] = remember_me
                
                # Log the successful login
                session_lifetime = REMEMBER_ME_LIFETIME if remember_me else DEFAULT_SESSION_LIFETIME
                print(f"Successful login: {username} from {request.remote_addr} (Remember me: {remember_me})")
                print(f"Session will expire after: {session_lifetime}")
                
                return redirect(url_for('home'))
            else:
                # Failed login
                user['failed_attempts'] = user.get('failed_attempts', 0) + 1
                
                if user['failed_attempts'] >= MAX_FAILED_ATTEMPTS:
                    user['locked_until'] = time.time() + LOCKOUT_DURATION
                    error_message = f"Too many failed attempts. Account locked for 10 minutes."
                    print(f"Account locked: {username} after {user['failed_attempts']} failed attempts")
                else:
                    remaining = MAX_FAILED_ATTEMPTS - user['failed_attempts']
                    error_message = f"Invalid password. {remaining} attempts remaining before lockout."
        else:
            # User doesn't exist, but don't reveal this information
            error_message = "Invalid username or password."
        
        # Log the failed attempt
        print(f"Failed login attempt: {username} from {request.remote_addr}")
        
        if error_message:
            return render_template('login_error.html', error_message=error_message)
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    username = session.get('username')
    if username:
        print(f"User logged out: {username}")
    
    session.clear()
    return redirect(url_for('login'))

@app.route('/test-placeholder')
@login_required
def test_placeholder():
    return render_template('test_placeholder.html')

@app.route('/camera-details')
@login_required
def camera_details():
    # Trigger a fresh camera scan
    global cameras
    cameras = scan_for_cameras()
    
    # Update camera connection status based on stream port
    for camera_id, camera_config in cameras.items():
        stream_port = camera_config.get('stream_port', 0)
        camera_config['is_connected'] = is_port_open('localhost', stream_port)
    
    return render_template('camera_details.html', cameras=cameras)

@app.route('/check-camera/<camera_id>')
@login_required
def check_camera(camera_id):
    """API endpoint to check if a camera's stream port is connected"""
    global cameras # Ensure we are using the latest scanned cameras

    # It's possible the camera list is stale, or this camera ID is new.
    # A quick check if the camera_id exists, if not, a rescan might be needed
    # or the ID is simply invalid. For this check, if not immediately found,
    # we report as disconnected. The main dashboard scan will pick up new cameras.
    if camera_id not in cameras:
        # To be more robust, we could try a targeted check like in stream_proxy/snapshot
        # but for a simple status check, if it's not in the current list, report disconnected.
        return {"connected": False}
        
    camera_config = cameras[camera_id]
    stream_port = camera_config.get('stream_port', 0)
    
    if stream_port == 0:
        # Invalid configuration for this camera_id if stream_port is missing
        return {"connected": False}
        
    is_connected = is_port_open('localhost', stream_port)
    
    # Optionally, update the 'is_connected' status in the global cameras dict
    # This might be useful if other parts rely on this, but can also lead to frequent updates.
    # cameras[camera_id]['is_connected'] = is_connected 

    return {"connected": is_connected}

@app.errorhandler(404)
def page_not_found(e):
    if 'username' in session:
        return render_template('404.html'), 404
    else:
        return redirect(url_for('login'))

# --- Person Detection Logic ---

def detect_persons_google_ai(image_bytes):
    """
    Uses Google AI Vision API to detect persons in an image.

    Args:
        image_bytes: The image data as bytes.

    Returns:
        True if a person is detected with sufficient confidence, False otherwise.
    """

    # save image_bytes to a file
    with open('image.jpg', 'wb') as f:
        f.write(image_bytes)

    api_key = os.environ.get('GEMINI_API_KEY') # Updated to GEMINI_API_KEY
    
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set. Cannot perform person detection.")
        return False

    try:
        client = genai.Client(
            api_key=api_key,
        )

        file = client.files.upload(file='image.jpg')
        response = client.models.generate_content(
            model='gemini-2.0-flash-001',
            contents=["Is there a person clearly visible in this image? Answer with only 'yes' or 'no'.", file]
        )
        print(response.text)
        

        # Parse the response
        if response.text:
            answer = response.text.strip().lower()
            print(f"Gemini AI response for person detection: '{answer}'")
            if 'yes' in answer:
                print("Person detected by Gemini AI.")
                return True
            elif 'no' in answer:
                print("No person detected by Gemini AI.")
                return False
            else:
                print(f"Unexpected response from Gemini AI: {response.text}")
                return False
        else:
            print("Empty response from Gemini AI.")
            return False

    except Exception as e:
        print(f"Error during Google AI person detection: {e}")
        # Log the full error for debugging if needed
        # import traceback
        # print(traceback.format_exc())
        return False

    # Fallback if not implemented or error
    # print("WARN: Person detection logic using google-genai encountered an issue or an unexpected response.")
    # return False # Covered by the try-except block


def check_camera_for_persons(camera_id):
    """Checks camera snapshot for persons and logs/saves image on change with comprehensive logging."""
    # Get the lock for this specific camera
    camera_lock = get_camera_lock(camera_id)
    
    # Use the lock to prevent concurrent checks of the same camera
    with camera_lock:
        person_logger.debug(f"Acquired detection lock for {camera_id}")
        
        global cameras, person_detection_state
        
        current_time = time.time()
        current_datetime = datetime.datetime.now()
        
        person_logger.info(f"Starting person detection check for {camera_id}")

        # Ensure camera config is available
        if camera_id not in cameras:
            person_logger.warning(f"Camera {camera_id} not found in current camera list. Attempting rescan...")
            # Attempt a quick rescan, maybe it just connected
            cameras = scan_for_cameras()
            if camera_id not in cameras:
                person_logger.error(f"Camera {camera_id} still not found after rescan. Skipping detection check.")
                return

        camera_config = cameras[camera_id]
        capture_url = camera_config.get('capture_url')

        if not capture_url:
            person_logger.error(f"Capture URL not configured for {camera_id}. Skipping detection check.")
            return

        # Initialize state if not present
        if camera_id not in person_detection_state:
            person_detection_state[camera_id] = {
                'person_present': False,
                'last_detection': None,
                'first_detection': None,
                'detection_count': 0,
                'session_start': None,
                'total_detection_time': 0,
                'last_check_time': current_time,
                'last_image_save_time': None  # Track when we last saved an image
            }
            person_logger.info(f"Initialized detection state for {camera_id}")

        state = person_detection_state[camera_id]
        was_present = state['person_present']
        is_present = False
        image_bytes = None

        # Log check attempt
        person_logger.debug(f"Fetching snapshot from {camera_id} at {capture_url}")

        # Fetch the snapshot
        snapshot_start_time = time.time()
        try:
            resp = requests.get(capture_url, timeout=5)
            snapshot_duration = time.time() - snapshot_start_time
            
            if resp.status_code == 200:
                image_bytes = resp.content
                person_logger.debug(f"Successfully fetched snapshot from {camera_id} ({len(image_bytes)} bytes in {snapshot_duration:.2f}s)")
            else:
                person_logger.error(f"HTTP {resp.status_code} error getting snapshot from {camera_id} ({capture_url})")
                return # Cannot proceed without image
        except requests.exceptions.RequestException as e:
            snapshot_duration = time.time() - snapshot_start_time
            person_logger.error(f"Network error fetching snapshot for {camera_id} after {snapshot_duration:.2f}s: {e}")
            return # Cannot proceed without image

        if image_bytes:
            # Call detection function
            detection_start_time = time.time()
            person_logger.info(f"Running AI person detection for {camera_id}")
            
            is_present = detect_persons_google_ai(image_bytes)
            
            detection_duration = time.time() - detection_start_time
            person_logger.info(f"AI detection completed for {camera_id} in {detection_duration:.2f}s - Result: {'PERSON DETECTED' if is_present else 'NO PERSON'}")

            # Update statistics
            time_since_last_check = current_time - state['last_check_time']
            state['last_check_time'] = current_time

            # Compare with previous state and handle state changes
            if is_present and not was_present:
                # Person just appeared
                state['person_present'] = True
                state['first_detection'] = current_time
                state['last_detection'] = current_time
                state['detection_count'] += 1
                state['session_start'] = current_time
                
                person_logger.info(f"a PERSON DETECTED on {camera_id} - Session #{state['detection_count']} started")
                person_logger.info(f"Detection timing - Snapshot: {snapshot_duration:.2f}s, AI: {detection_duration:.2f}s, Total: {snapshot_duration + detection_duration:.2f}s")
                
                # Always save image when person first appears
                should_save_image = True
                save_reason = "Person first detected"
                
            elif not is_present and was_present:
                # Person just disappeared
                if state['session_start']:
                    session_duration = current_time - state['session_start']
                    state['total_detection_time'] += session_duration
                    
                    person_logger.info(f"🚶‍♂️ PERSON LEFT {camera_id} - Session duration: {session_duration:.1f}s ({session_duration/60:.1f} minutes)")
                    person_logger.info(f"📊 Camera {camera_id} stats - Total sessions: {state['detection_count']}, Total time: {state['total_detection_time']:.1f}s ({state['total_detection_time']/60:.1f} minutes)")
                
                state['person_present'] = False
                state['session_start'] = None
                should_save_image = False  # Don't save when person leaves
                
            elif is_present and was_present:
                # Person still present - update last detection time
                state['last_detection'] = current_time
                if state['session_start']:
                    current_session_duration = current_time - state['session_start']
                    person_logger.debug(f"👁️ Person still present on {camera_id} - Current session: {current_session_duration:.1f}s")
                
                # Check if we should save another image (rate limited)
                last_save_time = state.get('last_image_save_time', 0)
                time_since_last_save = current_time - (last_save_time or 0)
                
                if time_since_last_save >= MIN_IMAGE_SAVE_INTERVAL:
                    should_save_image = True
                    save_reason = f"Continuous presence - {time_since_last_save:.0f}s since last save"
                else:
                    should_save_image = False
                    
            else:
                # No person detected and none was present before
                person_logger.debug(f"👀 No person detected on {camera_id} - Status unchanged")
                should_save_image = False

            # Save image if needed (when person is present and conditions are met)
            if should_save_image and is_present:
                # Create directory if it doesn't exist
                if not os.path.exists(PERSON_IMAGE_DIR):
                    try:
                        os.makedirs(PERSON_IMAGE_DIR)
                        person_logger.info(f"Created detection images directory: {PERSON_IMAGE_DIR}")
                    except OSError as e:
                        person_logger.error(f"Failed to create directory {PERSON_IMAGE_DIR}: {e}")
                        return
                
                # Generate unique filename
                unique_id = uuid.uuid4()
                timestamp = current_datetime.strftime("%Y%m%d_%H%M%S")
                filename = f"{PERSON_IMAGE_DIR}/{camera_id}_{timestamp}_{unique_id}.jpg"

                # Save the image
                try:
                    with open(filename, 'wb') as f:
                        f.write(image_bytes)
                    state['last_image_save_time'] = current_time  # Update last save time
                    person_logger.info(f"💾 Saved detection image: {filename} ({len(image_bytes)} bytes) - {save_reason}")
                except IOError as e:
                    person_logger.error(f"Failed to save detection image {filename}: {e}")

            # FIXED: Log statistics with correct calculations - always show current totals when person is present
            if is_present:
                # When person is present, always show current statistics
                if state['detection_count'] > 0:
                    avg_session_time = state['total_detection_time'] / state['detection_count'] if state['detection_count'] > 0 else 0
                    current_session_time = current_time - state['session_start'] if state['session_start'] else 0
                    total_time_including_current = state['total_detection_time'] + current_session_time
                    person_logger.info(f"📈 {camera_id} Statistics - Sessions: {state['detection_count']}, Current session: {current_session_time:.1f}s, Total time: {total_time_including_current:.1f}s")
            elif state['detection_count'] % 10 == 0 and state['detection_count'] > 0:
                # When no person present, log stats every 10th check
                avg_session_time = state['total_detection_time'] / state['detection_count'] if state['detection_count'] > 0 else 0
                person_logger.info(f"📈 {camera_id} Statistics - Sessions: {state['detection_count']}, Avg session: {avg_session_time:.1f}s, Total time: {state['total_detection_time']:.1f}s")

        person_logger.debug(f"Completed person detection check for {camera_id} - releasing lock")

def periodic_person_check():
    """Background task to periodically check cameras for persons with comprehensive logging."""
    # Log process information for debugging multiple instance issues
    current_pid = os.getpid()
    
    if PSUTIL_AVAILABLE:
        try:
            current_process = psutil.Process(current_pid)
            parent_pid = current_process.ppid()
            
            person_logger.info(f"🔄 Starting periodic person detection service - PID: {current_pid}, Parent PID: {parent_pid}")
            person_logger.info(f"📋 Process command: {' '.join(current_process.cmdline())}")
            
            # Check for other running instances
            try:
                other_instances = []
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if proc.info['name'] and 'python' in proc.info['name'].lower():
                            cmdline = proc.info['cmdline'] or []
                            if any('server.py' in cmd for cmd in cmdline) and proc.info['pid'] != current_pid:
                                other_instances.append(f"PID {proc.info['pid']}: {' '.join(cmdline)}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                if other_instances:
                    person_logger.warning(f"⚠️ Detected {len(other_instances)} other server.py instances running!")
                    for instance in other_instances:
                        person_logger.warning(f"   → {instance}")
                    person_logger.warning("⚠️ Multiple instances may cause detection cycle conflicts and inconsistent state!")
                else:
                    person_logger.info("✅ No other server.py instances detected - proceeding normally")
                    
            except Exception as e:
                person_logger.warning(f"Could not check for other instances: {e}")
                
        except Exception as e:
            person_logger.warning(f"Could not get process information: {e}")
            person_logger.info(f"🔄 Starting periodic person detection service - PID: {current_pid}")
    else:
        person_logger.info(f"🔄 Starting periodic person detection service - PID: {current_pid}")
        person_logger.info("📋 Process monitoring disabled (psutil not available)")
    
    check_count = 0
    
    while True:
        try:
            check_count += 1
            person_logger.info(f"🔍 Starting detection cycle #{check_count} for all cameras (PID: {current_pid})")
            
            start_time = time.time()
            
            # Check each camera
            cameras_checked = 0
            for camera_id in ["camera1", "camera2"]:
                try:
                    check_camera_for_persons(camera_id)
                    cameras_checked += 1
                except Exception as camera_error:
                    person_logger.error(f"❌ Error checking {camera_id} in cycle #{check_count}: {camera_error}")
                    # Log full traceback for debugging
                    import traceback
                    person_logger.error(f"📋 Full traceback: {traceback.format_exc()}")
                    
            cycle_duration = time.time() - start_time
            person_logger.info(f"✅ Completed detection cycle #{check_count} - Checked {cameras_checked}/2 cameras in {cycle_duration:.2f}s (PID: {current_pid})")
            
            # Log system stats every 12 cycles (1 hour)
            if check_count % 12 == 0:
                person_logger.info("📊 === HOURLY DETECTION SUMMARY ===")
                for camera_id, state in person_detection_state.items():
                    if state['detection_count'] > 0:
                        avg_session = state['total_detection_time'] / state['detection_count']
                        current_session_time = time.time() - state['session_start'] if state.get('session_start') else 0
                        total_including_current = state['total_detection_time'] + current_session_time
                        person_logger.info(f"📈 {camera_id}: {state['detection_count']} sessions, {total_including_current:.1f}s total, {avg_session:.1f}s avg")
                    else:
                        person_logger.info(f"📈 {camera_id}: No detections recorded")
                person_logger.info("=================================")
                        
        except Exception as e:
            person_logger.error(f"💥 Critical error in periodic person check cycle #{check_count}: {e}")
            # Log full traceback for debugging
            import traceback
            person_logger.error(f"📋 Full traceback: {traceback.format_exc()}")
            
        # Wait 5 minutes (300 seconds) before next check
        person_logger.info(f"💤 Sleeping for 5 minutes before next detection cycle... (PID: {current_pid})")
        time.sleep(300)

# Start the background thread for person detection
person_checker_thread = threading.Thread(target=periodic_person_check, daemon=True)
person_checker_thread.start()

@app.route('/detected-persons/<camera_id>')
@login_required
def person_gallery(camera_id):
    """Display gallery of detected persons for a specific camera"""
    global cameras
    
    # Verify camera exists
    if camera_id not in cameras:
        cameras = scan_for_cameras()
        if camera_id not in cameras:
            flash(f"Camera {camera_id} not found.")
            return redirect(url_for('home'))
    
    camera_config = cameras[camera_id]
    
    # Get all detected person images for this camera
    images = []
    if os.path.exists(PERSON_IMAGE_DIR):
        try:
            all_files = os.listdir(PERSON_IMAGE_DIR)
            # Filter files for this camera and sort by timestamp (newest first)
            camera_files = [f for f in all_files if f.startswith(f"{camera_id}_") and f.endswith('.jpg')]
            camera_files.sort(reverse=True)  # Newest first
            
            for filename in camera_files:
                # Parse timestamp from filename
                try:
                    parts = filename.split('_')
                    if len(parts) >= 3:
                        date_str = parts[1]
                        time_str = parts[2]
                        # Parse timestamp: YYYYMMDD_HHMMSS
                        timestamp = datetime.datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                        
                        images.append({
                            'filename': filename,
                            'timestamp': timestamp,
                            'unix_timestamp': int(timestamp.timestamp()),  # Add Unix timestamp for JS
                            'formatted_time': timestamp.strftime("%Y-%m-%d %H:%M:%S")  # Keep for fallback
                        })
                except (ValueError, IndexError) as e:
                    print(f"Error parsing timestamp from {filename}: {e}")
                    # Still include the file but without parsed timestamp
                    images.append({
                        'filename': filename,
                        'timestamp': None,
                        'unix_timestamp': None,
                        'formatted_time': 'Unknown'
                    })
        except OSError as e:
            print(f"Error reading detected persons directory: {e}")
            flash("Error reading detected persons directory.")
    
    return render_template('person_gallery.html', 
                         camera_id=camera_id, 
                         camera_name=camera_config.get('name', camera_id),
                         images=images,
                         image_count=len(images))

@app.route('/detected-persons/image/<filename>')
@login_required
def serve_detected_person_image(filename):
    """Serve a specific detected person image"""
    # Security check - ensure filename doesn't contain path traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        return "Invalid filename", 400
    
    file_path = os.path.join(PERSON_IMAGE_DIR, filename)
    
    # Check if file exists and is actually a file
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return "Image not found", 404
    
    try:
        return send_file(file_path, mimetype='image/jpeg')
    except Exception as e:
        print(f"Error serving image {filename}: {e}")
        return "Error serving image", 500

@app.route('/detected-persons/logs')
@login_required
def person_detection_logs():
    """Display person detection logs"""
    log_file_path = 'logs/person_detection.log'
    
    logs = []
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, 'r') as f:
                # Read last 100 lines for performance
                lines = f.readlines()
                recent_lines = lines[-100:] if len(lines) > 100 else lines
                
                for line in recent_lines:
                    if line.strip():  # Skip empty lines
                        logs.append(line.strip())
                        
            # Reverse to show newest first
            logs.reverse()
            
        except Exception as e:
            person_logger.error(f"Error reading log file: {e}")
            logs = [f"Error reading log file: {e}"]
    else:
        logs = ["Log file not found. Person detection may not have started yet."]
    
    # Get current detection states
    current_states = {}
    for camera_id, state in person_detection_state.items():
        last_detection_unix = int(state['last_detection']) if state.get('last_detection') else None
        current_states[camera_id] = {
            'person_present': state.get('person_present', False),
            'detection_count': state.get('detection_count', 0),
            'total_detection_time': state.get('total_detection_time', 0),
            'last_detection': datetime.datetime.fromtimestamp(state['last_detection']).strftime("%Y-%m-%d %H:%M:%S") if state.get('last_detection') else 'Never',
            'last_detection_unix': last_detection_unix,  # Add Unix timestamp for JS conversion
            'current_session_duration': time.time() - state['session_start'] if state.get('session_start') else 0
        }
    
    # Get server timezone offset in seconds from UTC
    server_timezone_offset = -time.timezone  # timezone is seconds west of UTC, so negate it
    
    return render_template('person_logs.html', 
                         logs=logs, 
                         log_count=len(logs),
                         current_states=current_states,
                         server_timezone_offset=server_timezone_offset)

# --- End Person Detection Logic ---

if __name__ == '__main__':
    # Check for multiple instances before starting
    lock_file_path = '/tmp/camera_server.lock'
    lock_file = None
    
    try:
        lock_file = open(lock_file_path, 'w')
        # Try to acquire exclusive lock
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        
        print(f"✅ Acquired lock file: {lock_file_path}")
        
        # Register cleanup function
        def cleanup_lock():
            try:
                if lock_file and not lock_file.closed:
                    lock_file.close()
                if os.path.exists(lock_file_path):
                    os.unlink(lock_file_path)
                    print(f"🧹 Cleaned up lock file: {lock_file_path}")
            except Exception as e:
                print(f"Warning: Could not clean up lock file: {e}")
        
        atexit.register(cleanup_lock)
        
    except (IOError, OSError) as e:
        print(f"❌ ERROR: Another camera server instance is already running!")
        print(f"Lock file: {lock_file_path}")
        print(f"Error: {e}")
        print()
        print("To check running instances: python3 check_instances.py")
        print("To force stop all instances: python3 check_instances.py --kill-all")
        sys.exit(1)
    
    print("Server running on http://localhost:8080")
    
    # Ensure the person image directory exists on startup, though the check function also does this
    if not os.path.exists(PERSON_IMAGE_DIR):
        try:
            os.makedirs(PERSON_IMAGE_DIR)
            print(f"Ensured directory exists: {PERSON_IMAGE_DIR}")
        except OSError as e:
            print(f"Error creating directory {PERSON_IMAGE_DIR} on startup: {e}")
    
    try:        
        app.run(host='0.0.0.0', port=8080, debug=False)  # Disable debug mode when running as service
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"💥 Server error: {e}")
    finally:
        # Cleanup will be handled by atexit
        pass
