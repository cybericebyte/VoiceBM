#!/usr/bin/env python3
"""
Simple HTTP server for voice recording playback
Serves both /recordings/ and /pending/ paths
"""

import http.server
import socketserver
import os
import json
from pathlib import Path
from urllib.parse import unquote

# Load configuration
CONFIG_FILE = "/home/user/voicebm/config.json"
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
        PORT = config['audio_server']['port']
except:
    PORT = 9090  # Fallback

BASE_DIR = "/home/user/voicebm"


class VoiceBMHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler that routes to different directories based on path"""
    
    def __init__(self, *args, **kwargs):
        # Don't set directory in parent - we handle routing manually
        super().__init__(*args, **kwargs)
    
    def translate_path(self, path):
        """Translate URL path to filesystem path"""
        # Decode URL encoding
        path = unquote(path)
        
        # Remove leading slash
        path = path.lstrip('/')
        
        # Route based on first path component
        if path.startswith('pending/'):
            # Serve from pending_active/recordings
            relative = path[8:]  # Remove 'pending/'
            return os.path.join(BASE_DIR, 'pending_active', 'recordings', relative)
        
        elif path.startswith('living/'):
            # Serve from recordings/living
            relative = path[7:]  # Remove 'living/'
            return os.path.join(BASE_DIR, 'recordings', 'living', relative)
        
        elif path.startswith('recordings/'):
            # Direct recordings path
            relative = path[11:]  # Remove 'recordings/'
            return os.path.join(BASE_DIR, 'recordings', relative)
        
        else:
            # Default to recordings directory
            return os.path.join(BASE_DIR, 'recordings', path)
    
    def end_headers(self):
        # Add CORS headers so Home Assistant can access
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.end_headers()
    
    def log_message(self, format, *args):
        """Custom logging"""
        print(f"[{self.log_date_time_string()}] {args[0]}")


def main():
    # Ensure directories exist
    Path(f"{BASE_DIR}/recordings/living").mkdir(parents=True, exist_ok=True)
    Path(f"{BASE_DIR}/pending_active/recordings").mkdir(parents=True, exist_ok=True)
    
    with socketserver.TCPServer(("", PORT), VoiceBMHTTPRequestHandler) as httpd:
        print(f"=" * 60)
        print(f"VoiceBM Audio Server")
        print(f"=" * 60)
        print(f"Listening on port {PORT}")
        print(f"")
        print(f"URL Paths:")
        print(f"  /living/          -> {BASE_DIR}/recordings/living/")
        print(f"  /recordings/      -> {BASE_DIR}/recordings/")
        print(f"  /pending/         -> {BASE_DIR}/pending_active/recordings/")
        print(f"")
        print(f"Example URLs:")
        print(f"  http://127.0.0.1:{PORT}/living/living_20251128_120000.wav")
        print(f"  http://127.0.0.1:{PORT}/pending/active_1732825200000.wav")
        print(f"=" * 60)
        print(f"Press Ctrl+C to stop")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")


if __name__ == "__main__":
    main()
