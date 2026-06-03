#!/bin/bash
# Kilifi ICT Attachee System — Start Script

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Kilifi County ICT Attachee Tracking System     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌  Python 3 is required. Install from https://python.org"
  exit 1
fi

# Install dependencies if needed
echo "📦  Checking dependencies..."
python3 -c "import flask, flask_cors, flask_jwt_extended" 2>/dev/null
if [ $? -ne 0 ]; then
  echo "📦  Installing dependencies..."
  pip3 install flask flask-cors flask-jwt-extended --quiet
fi

echo "✅  Starting server on http://localhost:5000"
echo "🌐  Open your browser to: http://localhost:5000"
echo "⏹   Press Ctrl+C to stop"
echo ""

python3 server.py
