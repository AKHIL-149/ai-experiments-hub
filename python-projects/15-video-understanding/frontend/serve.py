#!/usr/bin/env python3
"""
Simple HTTP server to serve the frontend
"""

import http.server
import socketserver
import os
import sys

PORT = 3001

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

if __name__ == '__main__':
    # Change to frontend directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
        print(f"=" * 80)
        print(f"🚀 Video Understanding Platform - Frontend Server")
        print(f"=" * 80)
        print(f"\n✅ Server running at: http://localhost:{PORT}")
        print(f"📡 API server should be running at: http://localhost:8000")
        print(f"\n💡 Open http://localhost:{PORT} in your browser")
        print(f"\nPress Ctrl+C to stop\n")
        print(f"=" * 80)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down server...")
            sys.exit(0)
