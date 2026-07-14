# MongoDB URL Reader Telegram Bot

An advanced, feature-rich Telegram Bot to explore, query, export, and manage MongoDB databases directly from Telegram chat using interactive inline keyboards and color-coded emojis. Fully configured for deployment on **Railway** (or VPS, Render, etc.).

## 🚀 Key Features
* **Database & Collection Explorer:** Browse all databases, sizes, and collection lists with record counts.
* **Document Viewer & Pagination:** Read documents page-by-page.
* **CRUD Operations:** Insert, update, or delete specific documents using interactive prompts.
* **Query Engine:** Execute custom JSON Find queries or Aggregation Pipelines from your chat.
* **Indexes Manager:** View existing collection indexes, create new ones, and drop unused ones.
* **File Exports:** Export complete collection contents to formatted JSON files.
* **Security & Log Channel:** Send logs of all user actions to a dedicated logging channel.
* **Admin Tools:** Broadcast messages to all users, view real-time statistics.

---

## 🛠️ Railway Hosting Setup (Quick Deploy)

1. Create a private repository on GitHub and upload all the files in this folder.
2. Log in to [Railway.app](https://railway.app) and click **"New Project"**.
3. Choose **"Deploy from GitHub repo"** and select your repository.
4. Go to the **Variables** tab in your Railway service dashboard and add the following:
   * `BOT_TOKEN`: Your Telegram Bot token from [@BotFather](tg://user?id=BotFather)
   * `OWNER_ID`: Your numerical Telegram user ID (for stats, broadcast controls)
   * `LOGS_CHAT_ID`: The Telegram group or channel ID where activity logs should be pushed (add your bot as admin there)
5. Railway will automatically detect the `Dockerfile` and build/deploy your bot as a background worker process.

---

## 💻 Local Run Setup

1. Make sure Python 3.9+ is installed.
2. Clone or place files in a directory and run:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the same folder:
   ```env
   BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
   OWNER_ID=YOUR_TELEGRAM_USER_ID
   LOGS_CHAT_ID=YOUR_LOGS_CHANNEL_OR_GROUP_ID
   ```
4. Run the bot:
   ```bash
   python bot.py
   ```
