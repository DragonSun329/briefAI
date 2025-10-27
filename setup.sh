#!/bin/bash
# Quick setup script for AI Briefing Agent

set -e

echo "========================================"
echo "AI Briefing Agent - Quick Setup"
echo "========================================"
echo ""

# Check Python version
echo "[1/5] Checking Python version..."
python3 --version || { echo "Error: Python 3 not found. Please install Python 3.10+"; exit 1; }

# Create virtual environment
echo ""
echo "[2/5] Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate and install dependencies
echo ""
echo "[3/5] Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Dependencies installed"

# Setup .env file
echo ""
echo "[4/5] Setting up environment file..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✓ .env file created from template"
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env and add your ANTHROPIC_API_KEY"
    echo "   Run: nano .env"
else
    echo "✓ .env file already exists"
fi

# Create cache directories
echo ""
echo "[5/5] Creating data directories..."
mkdir -p data/cache data/reports logs
touch data/cache/.gitkeep data/reports/.gitkeep logs/.gitkeep
echo "✓ Directories created"

echo ""
echo "========================================"
echo "✓ Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Add your Anthropic API key to .env:"
echo "   nano .env"
echo ""
echo "2. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "3. Run the agent:"
echo "   python main.py --interactive"
echo ""
echo "For more information, see README.md"
echo ""
