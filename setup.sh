#!/bin/bash

# Telegram Spoiler Bot Setup Script
# This script helps you set up and run the Telegram Spoiler Bot

echo "🤖 Telegram Spoiler Bot Setup"
echo "=============================="

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip3."
    exit 1
fi

echo "✅ pip3 found"

# Install requirements
echo ""
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies. Please check your internet connection and try again."
    exit 1
fi

echo "✅ Dependencies installed successfully"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo ""
    echo "⚙️  Setting up configuration..."
    
    # Copy example env file
    cp .env.example .env
    
    echo "📝 Please edit the .env file and add your bot token:"
    echo "   1. Get a bot token from @BotFather on Telegram"
    echo "   2. Edit the .env file and replace 'your_bot_token_here' with your actual token"
    echo ""
    echo "After setting up your token, run: python3 spoiler_bot.py"
else
    echo "✅ Configuration file (.env) already exists"
    echo ""
    echo "🚀 Ready to run! Execute: python3 spoiler_bot.py"
fi

echo ""
echo "📖 Quick Start Guide:"
echo "   1. Get your bot token from @BotFather"
echo "   2. Edit .env file with your token"
echo "   3. Run: python3 spoiler_bot.py"
echo "   4. Add the bot to your group chat"
echo "   5. Make the bot an admin with delete/send message permissions"
echo "   6. Use /enable_chat to activate spoiler detection"
echo "   7. Use /add_keyword to add words that should be spoiler-tagged"
echo ""
echo "For detailed instructions, see the README.md file."

