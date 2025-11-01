#!/bin/bash

# Job Ace Startup Script

echo "Starting Job Ace..."
echo "API will be available at: http://172.239.66.45:3000"
echo "Web UI will be available at: http://172.239.66.45:3000"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Activate virtual environment and start server
.venv/bin/python -m backend.main
