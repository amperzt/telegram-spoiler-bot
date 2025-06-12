#!/usr/bin/env python3
"""
Telegram Spoiler Bot

A bot that automatically adds spoiler tags to messages containing specific keywords
in Telegram group chats.

Author: Manus AI Assistant
Date: June 2025
"""

import logging
import re
import asyncio
from typing import List, Set
from telegram import Update, Message
from telegram.ext import (
    Application, 
    MessageHandler, 
    filters, 
    ContextTypes,
    CommandHandler
)
from telegram.error import TelegramError
import json
import os

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class SpoilerBot:
    """Main bot class for handling spoiler tag functionality"""
    
    def __init__(self, token: str, config_file: str = "spoiler_config.json"):
        self.token = token
        self.config_file = config_file
        self.spoiler_keywords = set()
        self.case_sensitive = False
        self.admin_users = set()
        self.enabled_chats = set()
        
        # Load configuration
        self.load_config()
        
        # Initialize application
        self.application = Application.builder().token(token).build()
        
        # Add handlers
        self.setup_handlers()
    
    def load_config(self):
        """Load configuration from JSON file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.spoiler_keywords = set(config.get('spoiler_keywords', []))
                    self.case_sensitive = config.get('case_sensitive', False)
                    self.admin_users = set(config.get('admin_users', []))
                    self.enabled_chats = set(config.get('enabled_chats', []))
                    logger.info(f"Loaded configuration: {len(self.spoiler_keywords)} keywords")
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
                'spoiler_keywords': list(self.spoiler_keywords),
                'case_sensitive': self.case_sensitive,
                'admin_users': list(self.admin_users),
                'enabled_chats': list(self.enabled_chats)
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info("Configuration saved")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def setup_handlers(self):
        """Setup message and command handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("add_keyword", self.add_keyword_command))
        self.application.add_handler(CommandHandler("remove_keyword", self.remove_keyword_command))
        self.application.add_handler(CommandHandler("list_keywords", self.list_keywords_command))
        self.application.add_handler(CommandHandler("enable_chat", self.enable_chat_command))
        self.application.add_handler(CommandHandler("disable_chat", self.disable_chat_command))
        self.application.add_handler(CommandHandler("toggle_case", self.toggle_case_command))
        self.application.add_handler(CommandHandler("add_admin", self.add_admin_command))
        
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
• `/add_keyword <word>` - Add a spoiler keyword
• `/remove_keyword <word>` - Remove a spoiler keyword
• `/list_keywords` - Show all keywords
• `/enable_chat` - Enable bot in this chat
• `/disable_chat` - Disable bot in this chat

**Note:** I need admin permissions to delete and send messages in group chats.
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
🔧 **Spoiler Bot Commands**

**Keyword Management:**
• `/add_keyword <word>` - Add a keyword that triggers spoiler tags
• `/remove_keyword <word>` - Remove a keyword
• `/list_keywords` - Show all current keywords
• `/toggle_case` - Toggle case sensitivity

**Chat Management:**
• `/enable_chat` - Enable spoiler detection in this chat
• `/disable_chat` - Disable spoiler detection in this chat

**Admin Commands:**
• `/add_admin <user_id>` - Add a bot administrator

**How it works:**
1. When someone sends a message containing a spoiler keyword
2. I delete the original message
3. I send a new message with spoiler tags: ||spoiler text||

**Example:**
If "endgame" is a keyword and someone writes:
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
        if keyword:
            self.spoiler_keywords.add(keyword.lower() if not self.case_sensitive else keyword)
            self.save_config()
            await update.message.reply_text(f"✅ Added keyword: `{keyword}`", parse_mode='Markdown')
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
        keyword_to_remove = keyword.lower() if not self.case_sensitive else keyword
        
        if keyword_to_remove in self.spoiler_keywords:
            self.spoiler_keywords.remove(keyword_to_remove)
            self.save_config()
            await update.message.reply_text(f"✅ Removed keyword: `{keyword}`", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Keyword `{keyword}` not found.", parse_mode='Markdown')
    
    async def list_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list_keywords command"""
        if not self.spoiler_keywords:
            await update.message.reply_text("📝 No spoiler keywords configured.")
            return
        
        keywords_list = '\n'.join([f"• `{keyword}`" for keyword in sorted(self.spoiler_keywords)])
        case_info = "Case sensitive" if self.case_sensitive else "Case insensitive"
        
        message = f"📝 **Spoiler Keywords** ({case_info}):\n\n{keywords_list}"
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
            self.spoiler_keywords = {keyword.lower() for keyword in self.spoiler_keywords}
        
        self.save_config()
        status = "enabled" if self.case_sensitive else "disabled"
        await update.message.reply_text(f"✅ Case sensitivity {status}.")
    
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
    
    def contains_spoiler_keywords(self, text: str) -> List[str]:
        """Check if text contains any spoiler keywords and return found keywords"""
        if not self.spoiler_keywords:
            return []
        
        found_keywords = []
        search_text = text if self.case_sensitive else text.lower()
        
        for keyword in self.spoiler_keywords:
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
            
            # Skip if no keywords configured
            if not self.spoiler_keywords:
                return
            
            message = update.message
            if not message or not message.text:
                return
            
            # Check for spoiler keywords
            found_keywords = self.contains_spoiler_keywords(message.text)
            
            if found_keywords:
                logger.info(f"Found spoiler keywords {found_keywords} in message from {message.from_user.username}")
                
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
                    
                    # Send new message with spoiler tags
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=new_message,
                        parse_mode='MarkdownV2' if '||' in spoiler_text else None
                    )
                    
                    logger.info(f"Successfully applied spoiler tags for keywords: {found_keywords}")
                    
                except TelegramError as e:
                    logger.error(f"Error handling spoiler message: {e}")
                    # If we can't delete the original message, send a warning
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="⚠️ I need admin permissions to delete messages and apply spoiler tags automatically."
                    )
        
        except Exception as e:
            logger.error(f"Unexpected error in handle_message: {e}")
    
    def run(self):
        """Start the bot"""
        logger.info("Starting Spoiler Bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Main function to run the bot"""
    # Get bot token from environment variable or prompt user
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("Please set the TELEGRAM_BOT_TOKEN environment variable or enter it below:")
        token = input("Bot Token: ").strip()
    
    if not token:
        print("Error: Bot token is required!")
        return
    
    # Create and run bot
    bot = SpoilerBot(token)
    
    # Add the first admin (the person running the bot)
    print("\nTo get started, you need to add yourself as an administrator.")
    print("You can find your Telegram user ID by messaging @userinfobot")
    
    try:
        admin_id = input("Enter your Telegram user ID: ").strip()
        if admin_id.isdigit():
            bot.admin_users.add(int(admin_id))
            bot.save_config()
            print(f"Added {admin_id} as administrator.")
        else:
            print("Invalid user ID. You can add administrators later using /add_admin command.")
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        return
    
    print("\n🤖 Bot is starting...")
    print("Add the bot to your group chat and use /enable_chat to activate spoiler detection.")
    print("Use /help to see all available commands.")
    print("Press Ctrl+C to stop the bot.\n")
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped.")

if __name__ == '__main__':
    main()

