#!/bin/bash

echo "Starting NAAC Compliance Intelligence System..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.8+ to continue."
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    print_error "Node.js is not installed. Please install Node.js 16+ to continue."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "naac_env" ]; then
    print_status "Creating virtual environment..."
    python3 -m venv naac_env
fi

# Activate virtual environment
print_status "Activating virtual environment..."
source naac_env/bin/activate

# Install/update dependencies
print_status "Installing Python dependencies..."
pip install -r requirements.txt

# Create required directories
print_status "Creating required directories..."
mkdir -p data/naac_documents data/mvsr_documents cache uploads chroma_db

# Copy environment file if it doesn't exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    print_warning "Created .env file from template. Please configure it before running the system."
    echo "Edit the .env file to match your configuration, then run this script again."
    exit 1
fi

# Check if Ollama is running
print_status "Checking Ollama service..."
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    print_error "Ollama is not running or not accessible at http://localhost:11434"
    echo "Please install and start Ollama with Llama3 model:"
    echo "  1. Install Ollama from https://ollama.ai/"
    echo "  2. Run: ollama pull llama3"
    echo "  3. Ensure Ollama service is running"
    exit 1
fi

# Install frontend dependencies if needed
if [ ! -d "frontend/node_modules" ]; then
    print_status "Installing npm dependencies..."
    cd frontend
    npm install
    cd ..
fi

print_status "Starting backend server..."
cd backend
python -m api.main &
BACKEND_PID=$!
cd ..

# Wait for backend to start
sleep 5

print_status "Starting frontend development server..."
cd frontend
npm start &
FRONTEND_PID=$!
cd ..

# Function to cleanup processes
cleanup() {
    print_status "Shutting down servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    print_status "System stopped."
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup SIGINT SIGTERM

print_status "NAAC Compliance Intelligence System is starting..."
echo ""
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop the system"

# Wait for user interrupt
wait