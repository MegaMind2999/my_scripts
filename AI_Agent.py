#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
N8N_LOG_FILE="/tmp/n8n_startup.log"
N8N_URL="http://localhost:5678" # Default n8n URL

WEBUI_DIR="/home/ubuntu/open-webui/backend"
WEBUI_SCRIPT_NAME="start.sh" # The script that starts the Open WebUI backend
WEBUI_LOG_FILE="/tmp/open-webui_startup.log"
# URL for the backend component started by WEBUI_SCRIPT_NAME
WEBUI_BACKEND_URL="http://localhost:8080"
# Common URL for the Open WebUI user interface (frontend)
WEBUI_FRONTEND_URL="http://localhost:3000"

echo "--- Starting n8n ---"
# Check if n8n is already running
if pgrep -f "n8n" > /dev/null; then
    echo "n8n appears to be already running. Skipping start."
    N8N_PID=$(pgrep -f "n8n" | head -n 1) # Get one of the PIDs if multiple
    echo "Existing n8n PID(s) found: $(pgrep -f "n8n" | tr '\n' ' ')"
    echo "n8n should be accessible at: $N8N_URL"
else
    # Assuming n8n is in PATH. If not, use the full path to the n8n executable.
    echo "Starting n8n and logging to $N8N_LOG_FILE..."
    nohup n8n > "$N8N_LOG_FILE" 2>&1 &
    N8N_PID=$!
    # Give n8n a moment to start up
    sleep 5
    if ! ps -p $N8N_PID > /dev/null; then
        echo "ERROR: n8n failed to start. Check $N8N_LOG_FILE for details."
        N8N_PID="" # Ensure PID is not used if startup failed
    else
        echo "n8n started in the background with PID $N8N_PID."
        echo "Output is being logged to: $N8N_LOG_FILE"
        echo "n8n should be accessible at: $N8N_URL"
    fi
fi


echo ""
echo "--- Starting Open WebUI backend ---"

if [ ! -d "$WEBUI_DIR" ]; then
    echo "Error: Directory $WEBUI_DIR does not exist."
    exit 1
fi

if [ ! -f "$WEBUI_DIR/$WEBUI_SCRIPT_NAME" ]; then
    echo "Error: Script $WEBUI_DIR/$WEBUI_SCRIPT_NAME does not exist."
    exit 1
fi

# Check if the webui backend script seems to be already running
if pgrep -f "$WEBUI_SCRIPT_NAME" > /dev/null; then
    echo "Open WebUI backend ($WEBUI_SCRIPT_NAME) appears to be already running. Skipping start."
    WEBUI_PID=$(pgrep -f "$WEBUI_SCRIPT_NAME" | head -n 1)
    echo "Existing Open WebUI backend PID(s) found: $(pgrep -f "$WEBUI_SCRIPT_NAME" | tr '\n' ' ')"
    echo "The Open WebUI backend (managed by this script) might be at: $WEBUI_BACKEND_URL"
    echo "The main Open WebUI interface is typically at: $WEBUI_FRONTEND_URL"
else
    echo "Changing directory to $WEBUI_DIR"
    cd "$WEBUI_DIR"

    echo "Executing $WEBUI_SCRIPT_NAME and logging to $WEBUI_LOG_FILE..."
    nohup bash "$WEBUI_SCRIPT_NAME" > "$WEBUI_LOG_FILE" 2>&1 &
    WEBUI_PID=$!

    # Give it a moment to start up
    sleep 5
    if ! ps -p $WEBUI_PID > /dev/null; then
        echo "ERROR: Open WebUI backend ($WEBUI_SCRIPT_NAME) failed to start. Check $WEBUI_LOG_FILE for details."
        WEBUI_PID="" # Ensure PID is not used if startup failed
        cd - > /dev/null # Return to original directory before potentially exiting
    else
        echo "Open WebUI backend ($WEBUI_SCRIPT_NAME) started in the background with PID $WEBUI_PID."
        echo "Output is being logged to: $WEBUI_LOG_FILE"
        echo "The Open WebUI backend (managed by this script) might be at: $WEBUI_BACKEND_URL"
        echo "The main Open WebUI interface is typically at: $WEBUI_FRONTEND_URL"
        cd - > /dev/null # Return to the original directory
    fi
fi


echo ""
echo "--- Summary ---"
PIDS_TO_KILL_CMD="kill"
KILL_CMD_HAS_PIDS=false

if [ -n "$N8N_PID" ]; then
    echo "n8n running with PID: $N8N_PID"
    echo "  Log: $N8N_LOG_FILE (Monitor: tail -f $N8N_LOG_FILE)"
    echo "  Access n8n at: $N8N_URL"
    PIDS_TO_KILL_CMD="$PIDS_TO_KILL_CMD $N8N_PID"
    KILL_CMD_HAS_PIDS=true
fi

if [ -n "$WEBUI_PID" ]; then
    echo "Open WebUI backend ($WEBUI_SCRIPT_NAME) running with PID: $WEBUI_PID (This script manages the backend)"
    echo "  Log: $WEBUI_LOG_FILE (Monitor: tail -f $WEBUI_LOG_FILE)"
    echo "  Backend URL (if applicable for direct access): $WEBUI_BACKEND_URL"
    echo "  Main Open WebUI interface is typically at: $WEBUI_FRONTEND_URL (ensure frontend is also running if separate)"
    PIDS_TO_KILL_CMD="$PIDS_TO_KILL_CMD $WEBUI_PID"
    KILL_CMD_HAS_PIDS=true
fi

echo ""
if [ "$KILL_CMD_HAS_PIDS" = true ]; then
    echo "To stop the managed n8n and/or Open WebUI backend process(es):"
    echo "  $PIDS_TO_KILL_CMD"
else
    echo "No n8n or Open WebUI backend processes were found running or successfully started by this script."
fi

echo ""
echo "For manual PID lookup if needed:"
echo "  pgrep -af n8n"
echo "  pgrep -af $WEBUI_SCRIPT_NAME  # For the backend script"
echo "  # You might also need to check for specific server processes like uvicorn, gunicorn, node, etc."
echo ""
echo "Script finished."

exit 0
