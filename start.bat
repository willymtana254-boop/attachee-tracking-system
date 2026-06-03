@echo off
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║   Kilifi County ICT Attachee Tracking System     ║
echo ╚══════════════════════════════════════════════════╝
echo.

echo Checking dependencies...
python -c "import flask, flask_cors, flask_jwt_extended" 2>nul
if %errorlevel% neq 0 (
    echo Installing dependencies...
    pip install flask flask-cors flask-jwt-extended --quiet
)

echo Starting server on http://localhost:5000
echo Open your browser to: http://localhost:5000
echo Press Ctrl+C to stop
echo.

python server.py
pause
