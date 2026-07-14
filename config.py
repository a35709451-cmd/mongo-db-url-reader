import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Telegram Bot Configuration
# You can set these in your Railway Environment Variables
# or edit them here directly.

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Replace 0 with your Telegram User ID (e.g. 123456789)
LOGS_CHAT_ID = int(os.getenv("LOGS_CHAT_ID", "0"))  # Replace 0 with your Logs Channel/Group ID (e.g. -1001234567890)

# Settings
MASK_LOG_URLS = True  # If True, masks password in MongoDB URLs sent to logs
MAX_DOCS_DISPLAY = 5  # Number of documents to display at a time
MAX_EXPORT_DOCS = 50000  # Safety limit for document exports to prevent memory exhaustion
DEFAULT_TIMEOUT_MS = 5000  # MongoDB connection timeout in milliseconds
