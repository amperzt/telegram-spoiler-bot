#!/usr/bin/env python3
"""
Telegram Spoiler Bot

A bot that automatically adds spoiler tags to messages containing specific keywords
in Telegram group chats. Features per-chat keyword management and robust error handling.

🎯 Per-chat keywords - Each group manages its own list
🔧 Auto-admin sync - Group admins become bot admins automatically
📍 Topic preservation - Works perfectly with forum groups
🛡️ Robust error handling - Won't crash on network issues
🔄 Keep-alive system - Prevents Render sleeping


"""


import logging
import re
import asyncio
import os
import json
import threading
import time
import requests
from typing import List, Set, Dict
from flask import Flask
from telegram import Update, Message
from telegram.ext import (
    Application, 
    MessageHandler, 
    filters, 
    ContextTypes,
    CommandHandler,
    ChatMemberHandler
)
from telegram.error import TelegramError, Conflict

# Create a simple web server to keep Render happy
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Spoiler Bot is running!", 200

@app.route('/health')
def health():
    return {"status": "healthy", "timestamp": time.time()}, 200

@app.route('/ping')
def ping():
    return "pong", 200

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def keep_alive():
    """Ping the service every 10 minutes to prevent sleeping"""
    app_url = os.getenv('RENDER_EXTERNAL_URL')
    if not app_url:
        return
    
    while True:
        try:
            time.sleep(600)  # Wait 10 minutes
            response = requests.get(f"{app_url}/health", timeout=30)
            print(f"🏓 Keep-alive ping: {response.status_code}")
        except Exception as e:
            print(f"⚠️ Keep-alive failed: {e}")

class SpoilerBot:
    """Main bot class for handling spoiler tag functionality"""
    
    def __init__(self, token: str, config_file: str = "spoiler_config.json"):
        self.token = token
        self.config_file = config_file
        self.spoiler_keywords = {}  # Dict: {chat_id: set_of_keywords}
        self.case_sensitive = False
        self.admin_users = set()
        self.enabled_chats = set()
        
        # Load configuration
        self.load_config()
        
        # Initialize application with error handling
        self.application = Application.builder().token(token).build()
        
        # Add error handler
        self.application.add_error_handler(self.error_handler)
        
        # Add handlers
        self.setup_handlers()
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in the bot"""
        error_msg = str(context.error)
        logger.error(f"Exception while handling an update: {error_msg}")
        
        # Handle specific Telegram errors
        if "Conflict" in error_msg:
            logger.error("🚨 CONFLICT: Another bot instance is running with the same token!")
            logger.error("Please stop all other instances of this bot.")
        elif "Unauthorized" in error_msg:
            logger.error("🚨 UNAUTHORIZED: Bot token is invalid or revoked!")
        elif "Network" in error_msg:
            logger.error("🌐 NETWORK: Connection issue with Telegram servers")
        
        return
    
    def load_config(self):
        """Load configuration from JSON file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                    # Load per-chat keywords
                    keywords_data = config.get('spoiler_keywords', {})
                    if isinstance(keywords_data, list):
                        # Migrate old global format to new per-chat format
                        self.spoiler_keywords = {}
                        logger.info("Migrated old global keywords format")
                    else:
                        # New format: {chat_id: [keywords]}
                        self.spoiler_keywords = {
                            int(chat_id): set(keywords) 
                            for chat_id, keywords in keywords_data.items()
                        }
                    
                    self.case_sensitive = config.get('case_sensitive', False)
                    self.admin_users = set(config.get('admin_users', []))
                    self.enabled_chats = set(config.get('enabled_chats', []))
                    
                    total_keywords = sum(len(keywords) for keywords in self.spoiler_keywords.values())
                    logger.info(f"Loaded configuration: {total_keywords} keywords across {len(self.spoiler_keywords)} chats")
            else:
                # Create default config
                self.save_config()
                logger.info("Created default configuration file")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    
    def save_config(self):
        """Save current configuration to JSON file"""
        try:
            config = {
                'spoiler_keywords': {
                    str(chat_id): list(keywords) 
                    for chat_id, keywords in self.spoiler_keywords.items()
                },
                'case_sensitive': self.case_sensitive,
                'admin_users': list(self.admin_users),
                'enabled_chats': list(self.enabled_chats)
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info("Configuration saved")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def get_chat_keywords(self, chat_id: int) -> set:
        """Get keywords for a specific chat"""
        return self.spoiler_keywords.get(chat_id, set())
    
    def add_chat_keyword(self, chat_id: int, keyword: str):
        """Add a keyword to a specific chat"""
        if chat_id not in self.spoiler_keywords:
            self.spoiler_keywords[chat_id] = set()
        
        processed_keyword = keyword.lower() if not self.case_sensitive else keyword
        self.spoiler_keywords[chat_id].add(processed_keyword)
    
    def remove_chat_keyword(self, chat_id: int, keyword: str) -> bool:
        """Remove a keyword from a specific chat. Returns True if removed."""
        if chat_id not in self.spoiler_keywords:
            return False
        
        processed_keyword = keyword.lower() if not self.case_sensitive else keyword
        if processed_keyword in self.spoiler_keywords[chat_id]:
            self.spoiler_keywords[chat_id].remove(processed_keyword)
            # Clean up empty sets
            if not self.spoiler_keywords[chat_id]:
                del self.spoiler_keywords[chat_id]
            return True
        return False
    
    def setup_handlers(self):
        """Setup message and command handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("add_keyword", self.add_keyword_command))
        self.application.add_handler(CommandHandler("remove_keyword", self.remove_keyword_command))
        self.application.add_handler(CommandHandler("list_keywords", self.list_keywords_command))
        self.application.add_handler(CommandHandler("list_all_keywords", self.list_all_keywords_command))
        self.application.add_handler(CommandHandler("enable_chat", self.enable_chat_command))
        self.application.add_handler(CommandHandler("disable_chat", self.disable_chat_command))
        self.application.add_handler(CommandHandler("toggle_case", self.toggle_case_command))
        self.application.add_handler(CommandHandler("add_admin", self.add_admin_command))
        self.application.add_handler(CommandHandler("sync_admins", self.sync_admins_command))
        self.application.add_handler(ChatMemberHandler(self.handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
        
        # Message handler for spoiler detection
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.handle_message
            )
        )
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_text = """
🤖 **Spoiler Bot** is now active!

I automatically add spoiler tags to messages containing specific keywords.

**Commands:**
• `/help` - Show all commands
• `/add_keyword <word>` - Add a spoiler keyword to this chat
• `/remove_keyword <word>` - Remove a spoiler keyword from this chat
• `/list_keywords` - Show keywords for this chat
• `/enable_chat` - Enable bot in this chat
• `/disable_chat` - Disable bot in this chat
• `/sync_admins` - Sync group admins with bot admins

**Note:** I need admin permissions to delete and send messages in group chats.
Each chat has its own independent keyword list!
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
🔧 **Spoiler Bot Commands**

**Keyword Management (Per Chat):**
• `/add_keyword <word>` - Add a keyword that triggers spoiler tags in this chat
• `/remove_keyword <word>` - Remove a keyword from this chat
• `/list_keywords` - Show all keywords for this chat
• `/toggle_case` - Toggle case sensitivity

**Chat Management:**
• `/enable_chat` - Enable spoiler detection in this chat
• `/disable_chat` - Disable spoiler detection in this chat

**Admin Commands:**
• `/add_admin <user_id>` - Add a bot administrator
• `/sync_admins` - Sync group admins with bot admins
• `/list_all_keywords` - Show keywords for all chats (admin only)

**How it works:**
1. Each chat has its own keyword list
2. When someone sends a message containing a spoiler keyword
3. I delete the original message
4. I send a new message with spoiler tags: ||spoiler text||

**Example:**
If "endgame" is a keyword in this chat and someone writes:
"I loved the endgame battle scene!"

I'll replace it with:
"I loved the ||endgame|| battle scene!"
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is a bot administrator"""
        return user_id in self.admin_users
    
    async def add_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_keyword command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot administrators can manage keywords.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Please provide a keyword. Usage: `/add_keyword spoiler_word`", parse_mode='Markdown')
            return
        
        keyword = ' '.join(context.args).strip()
        chat_id = update.effective_chat.id
        
        if keyword:
            self.add_chat_keyword(chat_id, keyword)
            self.save_config()
            await update.message.reply_text(f"✅ Added keyword `{keyword}` to this chat", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Keyword cannot be empty.")
    
    async def remove_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /remove_keyword command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot administrators can manage keywords.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Please provide a keyword. Usage: `/remove_keyword spoiler_word`", parse_mode='Markdown')
            return
        
        keyword = ' '.join(context.args).strip()
        chat_id = update.effective_chat.id
        
        if self.remove_chat_keyword(chat_id, keyword):
            self.save_config()
            await update.message.reply_text(f"✅ Removed keyword `{keyword}` from this chat", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Keyword `{keyword}` not found in this chat.", parse_mode='Markdown')
    
    async def list_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list_keywords command"""
        chat_id = update.effective_chat.id
        chat_keywords = self.get_chat_keywords(chat_id)
        
        if not chat_keywords:
            await update.message.reply_text("📝 No spoiler keywords configured for this chat.")
            return
        
        keywords_list = '\n'.join([f"• `{keyword}`" for keyword in sorted(chat_keywords)])
        case_info = "Case sensitive" if self.case_sensitive else "Case insensitive"
        chat_name = update.effective_chat.title or "this chat"
        
        message = f"📝 **Spoiler Keywords for {chat_name}** ({case_info}):\n\n{keywords_list}"
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def list_all_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list_all_keywords command - shows keywords for all chats"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot administrators can view global keywords.")
            return
        
        if not self.spoiler_keywords:
            await update.message.reply_text("📝 No spoiler keywords configured in any chat.")
            return
        
        message_parts = ["📝 **All Spoiler Keywords by Chat:**\n"]
        
        for chat_id, keywords in self.spoiler_keywords.items():
            try:
                chat = await context.bot.get_chat(chat_id)
                chat_name = chat.title or f"Chat {chat_id}"
            except:
                chat_name = f"Chat {chat_id}"
            
            keywords_list = ', '.join([f"`{keyword}`" for keyword in sorted(keywords)])
            message_parts.append(f"**{chat_name}:** {keywords_list}")
        
        message = '\n\n'.join(message_parts)
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def enable_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /enable_chat command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot administrators can enable/disable chats.")
            return
        
        chat_id = update.effective_chat.id
        self.enabled_chats.add(chat_id)
        self.save_config()
        await update.message.reply_text("✅ Spoiler detection enabled in this chat.")
    
    async def disable_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /disable_chat command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot administrators can enable/disable chats.")
            return
        
        chat_id = update.effective_chat.id
        self.enabled_chats.discard(chat_id)
        self.save_config()
        await update.message.reply_text("✅ Spoiler detection disabled in this chat.")
    
    async def toggle_case_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /toggle_case command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot administrators can change settings.")
            return
        
        self.case_sensitive = not self.case_sensitive
        
        # Update existing keywords to match new case sensitivity
        if not self.case_sensitive:
            for chat_id in self.spoiler_keywords:
                self.spoiler_keywords[chat_id] = {keyword.lower() for keyword in self.spoiler_keywords[chat_id]}
        
        self.save_config()
        status = "enabled" if self.case_sensitive else "disabled"
        await update.message.reply_text(f"✅ Case sensitivity {status} globally.")
    
    async def add_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_admin command"""
        if not self.is_admin(update.effective_user.id) and len(self.admin_users) > 0:
            await update.message.reply_text("❌ Only existing administrators can add new admins.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Please provide a user ID. Usage: `/add_admin 123456789`", parse_mode='Markdown')
            return
        
        try:
            user_id = int(context.args[0])
            self.admin_users.add(user_id)
            self.save_config()
            await update.message.reply_text(f"✅ Added administrator: `{user_id}`", parse_mode='Markdown')
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Please provide a numeric user ID.")
    
    async def sync_group_admins(self, chat_id):
        """Automatically add Telegram group admins as bot admins"""
        try:
            # Get list of chat administrators
            chat_admins = await self.application.bot.get_chat_administrators(chat_id)
            
            added_admins = []
            for admin in chat_admins:
                user_id = admin.user.id
                # Skip the bot itself and anonymous admins
                if not admin.user.is_bot and user_id not in self.admin_users:
                    self.admin_users.add(user_id)
                    added_admins.append(f"{admin.user.first_name} ({user_id})")
            
            if added_admins:
                self.save_config()
                logger.info(f"Auto-added {len(added_admins)} group admins as bot admins")
                return added_admins
            return []
        except Exception as e:
            logger.error(f"Error syncing group admins: {e}")
            return []
    
    async def sync_admins_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sync_admins command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot administrators can sync admins.")
            return
        
        chat_id = update.effective_chat.id
        added_admins = await self.sync_group_admins(chat_id)
        
        if added_admins:
            admin_list = '\n'.join([f"• {admin}" for admin in added_admins])
            message = f"✅ **Added group admins as bot admins:**\n\n{admin_list}"
            await update.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text("ℹ️ No new admins to add. All group admins are already bot admins.")
    
    async def handle_my_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle when bot is added/removed from chats"""
        if update.my_chat_member.new_chat_member.status == "administrator":
            # Bot was made admin, sync group admins
            chat_id = update.effective_chat.id
            added_admins = await self.sync_group_admins(chat_id)
            
            if added_admins:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🤖 **Bot Setup Complete!**\n\nAuto-added {len(added_admins)} group admins as bot administrators.\n\nUse `/enable_chat` to activate spoiler detection!\n\nEach chat has its own keyword list. Use `/add_keyword` to start adding spoiler words for this chat.",
                    parse_mode='Markdown'
                )
    
    def contains_spoiler_keywords(self, text: str, chat_id: int) -> List[str]:
        """Check if text contains any spoiler keywords for this chat and return found keywords"""
        chat_keywords = self.get_chat_keywords(chat_id)
        
        if not chat_keywords:
            return []
        
        found_keywords = []
        search_text = text if self.case_sensitive else text.lower()
        
        for keyword in chat_keywords:
            # Use word boundaries to match whole words only
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, search_text, re.IGNORECASE if not self.case_sensitive else 0):
                found_keywords.append(keyword)
        
        return found_keywords
    
    def apply_spoiler_tags(self, text: str, keywords: List[str]) -> str:
        """Apply spoiler tags to keywords in text"""
        result_text = text
        
        for keyword in keywords:
            # Create pattern for case-insensitive replacement if needed
            flags = 0 if self.case_sensitive else re.IGNORECASE
            pattern = r'\b' + re.escape(keyword) + r'\b'
            
            # Replace with spoiler tags
            result_text = re.sub(
                pattern, 
                f'||{keyword}||', 
                result_text, 
                flags=flags
            )
        
        return result_text
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages and apply spoiler tags if needed"""
        try:
            # Skip if chat is not enabled
            if update.effective_chat.id not in self.enabled_chats:
                return
            
            message = update.message
            if not message or not message.text:
                return
            
            # Check for spoiler keywords in this specific chat
            found_keywords = self.contains_spoiler_keywords(message.text, update.effective_chat.id)
            
            if found_keywords:
                logger.info(f"Found spoiler keywords {found_keywords} in message from {message.from_user.username} in chat {update.effective_chat.id}")
                
                # Apply spoiler tags
                spoiler_text = self.apply_spoiler_tags(message.text, found_keywords)
                
                # Get user info for attribution
                user = message.from_user
                user_mention = f"@{user.username}" if user.username else user.first_name
                
                # Create new message with spoiler tags
                new_message = f"{user_mention}: {spoiler_text}"
                
                try:
                    # Delete original message
                    await message.delete()
                    
                    # Send new message with spoiler tags (preserve topic)
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=new_message,
                        message_thread_id=message.message_thread_id,  # Preserve topic
                        parse_mode='MarkdownV2' if '||' in spoiler_text else None
                    )
                    
                    logger.info(f"Successfully applied spoiler tags for keywords: {found_keywords}")
                    
                except TelegramError as e:
                    logger.error(f"Error handling spoiler message: {e}")
                    # If we can't delete the original message, send a warning
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="⚠️ I need admin permissions to delete messages and apply spoiler tags automatically.",
                        message_thread_id=message.message_thread_id  # Also preserve topic for warnings
                    )
        
        except Exception as e:
            logger.error(f"Unexpected error in handle_message: {e}")
    
    def run(self):
        """Start the bot"""
        logger.info("Starting Spoiler Bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

async def test_bot_connection(token: str):
    """Test bot connection and check for conflicts"""
    try:
        print("🔍 Testing bot token and checking for conflicts...")
        test_app = Application.builder().token(token).build()
        
        async with test_app:
            await test_app.initialize()
            bot_info = await test_app.bot.get_me()
            print(f"✅ Bot connected successfully: @{bot_info.username}")
            await test_app.shutdown()
        
        return True
        
    except Conflict as e:
        print("🚨 ERROR: Another instance of this bot is already running!")
        print("Please stop all other instances before starting this one.")
        print("Check:")
        print("- Local computer terminal")
        print("- Other hosting services") 
        print("- Multiple Render deployments")
        return False
        
    except Exception as e:
        print(f"❌ Bot connection test failed: {e}")
        if "Unauthorized" in str(e):
            print("🚨 Bot token is invalid or revoked!")
        return False

def main():
    """Main function to run the bot - let Render handle restarts"""
    try:
        # Get bot token from environment variable
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        
        if not token:
            print("Error: TELEGRAM_BOT_TOKEN environment variable not set!")
            return
        
        # Test connection before starting
        if not asyncio.run(test_bot_connection(token)):
            return
        
        # Create and run bot
        bot = SpoilerBot(token)
        
        # Auto-add admin from environment variable (fallback)
        admin_id = os.getenv('ADMIN_USER_ID')
        if admin_id and admin_id.isdigit():
            bot.admin_users.add(int(admin_id))
            bot.save_config()
            print(f"Added {admin_id} as administrator.")
        else:
            print("No ADMIN_USER_ID set. Group admins will be auto-detected.")
        
        print("\n🤖 Bot is starting...")
        print("Bot is now running in the cloud!")
        print("Each chat will have its own independent keyword list.")
        print("Group admins will be automatically detected when bot is made admin.")
        
        # Start web server for Render
        port = int(os.environ.get('PORT', 5000))
        web_thread = threading.Thread(
            target=lambda: app.run(
                host='0.0.0.0', 
                port=port, 
                debug=False,
                use_reloader=False
            )
        )
        web_thread.daemon = True
        web_thread.start()
        print(f"🌐 Web server started on port {port}")
        
        # Start keep-alive if on Render
        if os.getenv('RENDER_EXTERNAL_URL'):
            keep_alive_thread = threading.Thread(target=keep_alive)
            keep_alive_thread.daemon = True
            keep_alive_thread.start()
            print("🔄 Keep-alive service started")
        
        # Run the bot
        bot.run()
        
    except Exception as e:
        print(f"❌ Bot error: {e}")
        if "Conflict" in str(e):
            print("🚨 Multiple bot instances detected!")
        raise  # Let Render handle the restart

if __name__ == '__main__':
    main()



"""
Author: Manus AI Assistant
Date: June 2025
"""