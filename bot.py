import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
import html
import json
import time
import os
import io
import humanize

from config import BOT_TOKEN, OWNER_ID, LOGS_CHAT_ID, MASK_LOG_URLS, MAX_DOCS_DISPLAY, MAX_EXPORT_DOCS
import database as db
from mongo_helper import MongoHelper, mask_mongo_url

# Initialize Bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# In-memory dictionary for user input states
USER_STATES = {}
# Temporary data store for users during complex multi-step inputs (e.g. doc editing)
USER_TEMP_DATA = {}

# Help text message
HELP_TEXT = """
🔥 <b>MongoDB URL Reader - Advanced Telegram Bot Features</b>

Welcome to the ultimate MongoDB management companion. Connect once, manage indefinitely!

🚀 <b>Core Capabilities:</b>
1. <b>Easy Connection:</b> Paste any <code>mongodb://</code> or <code>mongodb+srv://</code> connection string.
2. <b>Database Explorer:</b> Browse all databases, see disk sizes, and access collections.
3. <b>Collection Manager:</b> Create collections, drop collections, and clone collection data instantly.
4. <b>Interactive CRUD:</b>
   • View documents with smooth pagination and formatting.
   • Insert new documents via raw JSON.
   • Update documents by specifying their unique ID and replacement fields.
   • Delete specific documents with simple interactive buttons.
5. <b>Query Engine:</b>
   • Execute advanced JSON Find queries (e.g. <code>{"status": "active", "age": {"$gt": 18}}</code>).
   • Run Aggregation Pipelines directly from Telegram.
6. <b>Indexes Manager:</b> List existing indexes, create compound/unique indexes, and drop unused ones.
7. <b>High-Speed Export:</b> Export collection records to a neat JSON file.
8. <b>Full Logging:</b> Real-time logs are pushed to the administrator logs channel keeping actions transparent.

⚠️ <b>Quick Disconnect:</b> Send /disconnect or click the disconnect button to clear your session credentials from the database.
"""

# Helper to escape HTML characters
def safe_html(text):
    return html.escape(str(text))

# Logger function to log user actions to Logs Channel
def log_action(user, action, details=None):
    try:
        # Save to user database first
        db.add_user(user.id, user.username, user.first_name)
        
        if not LOGS_CHAT_ID:
            return
            
        username_formatted = f"@{user.username}" if user.username else "No Username"
        log_message = (
            f"🔔 <b>[USER ACTIVITY LOG]</b>\n\n"
            f"👤 <b>User:</b> {safe_html(user.first_name)} ({username_formatted})\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"🛠️ <b>Action:</b> <code>{action}</code>\n"
            f"📅 <b>Timestamp:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        
        if details:
            log_message += f"📝 <b>Details:</b>\n{safe_html(details)}"
            
        # Send to logs channel
        bot.send_message(LOGS_CHAT_ID, log_message)
    except Exception as e:
        print(f"Logging error: {e}")

# Check if user has an active MongoDB session and return client
def get_mongo_client(user_id):
    session = db.get_session(user_id)
    if not session or not session.get("mongo_url"):
        return None, "No active database session found. Please send a valid MongoDB connection string to get started."
        
    helper = MongoHelper(session["mongo_url"])
    success, msg = helper.connect()
    if not success:
        return None, f"❌ <b>Connection Refused:</b>\n<code>{safe_html(msg)}</code>\n\nYour session was disconnected due to authentication/network issues. Send a new connection string to reconnect."
        
    return helper, session

# Standard connection status panel builder
def get_main_dashboard_markup(session_info=None):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📁 Databases", callback_data="action_list_dbs"),
        InlineKeyboardButton("📊 Server Stats", callback_data="action_server_stats")
    )
    markup.add(
        InlineKeyboardButton("🔑 Connection Details", callback_data="action_conn_details"),
        InlineKeyboardButton("🔌 Disconnect Session", callback_data="action_disconnect")
    )
    return markup

# ----------------- Command Handlers -----------------

@bot.message_handler(commands=['start'])
def handle_start(message):
    user = message.from_user
    db.add_user(user.id, user.username, user.first_name)
    
    log_action(user, "Started Bot")
    
    welcome_text = (
        f"👋 <b>Hey, {safe_html(user.first_name)}!</b>\n\n"
        f"🤖 Welcome to <b>MongoDB URL Reader Bot</b> - the most advanced, colored-UI database client built directly in Telegram!\n\n"
        f"💡 <b>To begin:</b> Please send your MongoDB connection URL (starts with <code>mongodb://</code> or <code>mongodb+srv://</code>).\n\n"
        f"🔒 <i>All passwords are encrypted or masked in public actions. Check /help to learn more about the 500+ operations you can run.</i>"
    )
    
    # Check if user already has an active session
    session = db.get_session(user.id)
    if session:
        masked_url = mask_mongo_url(session["mongo_url"])
        welcome_text += f"\n\n🔄 <b>Existing Session Detected:</b>\n<code>{safe_html(masked_url)}</code>\n\nYou can access your session dashboard below."
        bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_dashboard_markup(session))
    else:
        bot.send_message(message.chat.id, welcome_text)

@bot.message_handler(commands=['help'])
def handle_help(message):
    log_action(message.from_user, "Requested Help Guide")
    bot.send_message(message.chat.id, HELP_TEXT)

@bot.message_handler(commands=['disconnect'])
def handle_disconnect_cmd(message):
    user_id = message.from_user.id
    session = db.get_session(user_id)
    if session:
        masked_url = mask_mongo_url(session["mongo_url"])
        db.delete_session(user_id)
        log_action(message.from_user, "Disconnected MongoDB Session", f"URL: {masked_url}")
        bot.send_message(message.chat.id, "🔌 <b>Database Disconnected.</b> Your session variables and connection URI have been completely deleted from our system cache.")
    else:
        bot.send_message(message.chat.id, "ℹ️ You do not have any active MongoDB sessions running.")

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    user_id = message.from_user.id
    if user_id != OWNER_ID:
        return
        
    users_count = db.get_users_count()
    log_action(message.from_user, "Viewed Admin Stats")
    bot.send_message(
        message.chat.id,
        f"📈 <b>Bot Usage Analytics:</b>\n\n"
        f"👥 <b>Total Registered Users:</b> {users_count}\n"
        f"⚙️ <b>Active Cache Databases:</b> SQLite 3"
    )

@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message):
    user_id = message.from_user.id
    if user_id != OWNER_ID:
        return
        
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        # Prompt user for broadcast message
        USER_STATES[user_id] = "WAITING_FOR_BROADCAST"
        bot.send_message(message.chat.id, "📣 <b>Please reply/send the message you want to broadcast to all bot users.</b> Type <code>cancel</code> to abort.")
        return
        
    broadcast_msg = parts[1]
    execute_broadcast(broadcast_msg, user_id)

def execute_broadcast(text, owner_id):
    users = db.get_all_users()
    bot.send_message(owner_id, f"⚡ <b>Sending Broadcast to {len(users)} users...</b>")
    
    success = 0
    failed = 0
    
    for u_id in users:
        try:
            bot.send_message(u_id, text)
            success += 1
            time.sleep(0.05) # Prevent spam limits
        except Exception:
            failed += 1
            
    log_action(bot.get_chat(owner_id), "Executed Broadcast Message", f"Content: {text[:200]}\nSuccess: {success}, Failed: {failed}")
    bot.send_message(owner_id, f"✅ <b>Broadcast Completed!</b>\n\n🟢 Successful: {success}\n🔴 Failed: {failed}")

# ----------------- Document Input Handlers -----------------

@bot.message_handler(func=lambda message: True)
def handle_text_inputs(message):
    user = message.from_user
    user_id = user.id
    text = message.text.strip()
    
    # Check if cancelling
    if text.lower() == "cancel":
        USER_STATES.pop(user_id, None)
        USER_TEMP_DATA.pop(user_id, None)
        bot.send_message(message.chat.id, "❌ Action cancelled. Returning to main menu.")
        session = db.get_session(user_id)
        if session:
            bot.send_message(message.chat.id, "📊 Session active.", reply_markup=get_main_dashboard_markup(session))
        return

    # Check states
    state = USER_STATES.get(user_id)
    
    # 1. Waiting for broadcast text
    if state == "WAITING_FOR_BROADCAST" and user_id == OWNER_ID:
        USER_STATES.pop(user_id, None)
        execute_broadcast(text, user_id)
        return
        
    # 2. Connection MongoDB URL check
    if text.startswith("mongodb://") or text.startswith("mongodb+srv://"):
        masked = mask_mongo_url(text)
        bot.send_message(message.chat.id, "⏳ <b>Verifying Connection...</b>\nPinging server, please wait.")
        
        helper = MongoHelper(text)
        connected, msg = helper.connect()
        if connected:
            db.save_session(user_id, text)
            log_action(user, "Connected to MongoDB", f"URL: {masked}")
            bot.send_message(
                message.chat.id,
                f"✅ <b>Connection Established!</b>\n\n"
                f"🔗 <b>URI:</b> <code>{safe_html(masked)}</code>\n\n"
                f"Use the dashboard below to navigate databases.",
                reply_markup=get_main_dashboard_markup()
            )
        else:
            log_action(user, "Connection Failed", f"URL: {masked}\nError: {msg}")
            bot.send_message(message.chat.id, f"❌ <b>Connection Failed:</b>\n<code>{safe_html(msg)}</code>\n\nPlease double check credentials and firewall settings.")
        helper.close()
        return

    # For other states, we need an active DB connection
    if state:
        helper, session = get_mongo_client(user_id)
        if not helper:
            USER_STATES.pop(user_id, None)
            bot.send_message(message.chat.id, session)
            return
            
        current_db = session.get("current_db")
        current_coll = session.get("current_coll")
        
        # 3. Create Collection
        if state == "WAITING_FOR_CREATE_COLL":
            USER_STATES.pop(user_id, None)
            success, msg = helper.create_collection(current_db, text)
            log_action(user, "Create Collection", f"DB: {current_db}, Coll Name: {text}, Status: {success}")
            if success:
                bot.send_message(message.chat.id, f"✅ {msg}")
                # Set as active collection and return to collection menu
                db.update_session_db_coll(user_id, current_db, text)
                send_collection_dashboard(message.chat.id, helper, current_db, text)
            else:
                bot.send_message(message.chat.id, f"❌ <b>Error:</b> {safe_html(msg)}")
                
        # 4. Clone Collection
        elif state == "WAITING_FOR_CLONE_COLL":
            USER_STATES.pop(user_id, None)
            success, msg = helper.clone_collection(current_db, current_coll, text)
            log_action(user, "Clone Collection", f"DB: {current_db}, Src: {current_coll}, Dest: {text}, Status: {success}")
            if success:
                bot.send_message(message.chat.id, f"✅ {msg}")
                db.update_session_db_coll(user_id, current_db, text)
                send_collection_dashboard(message.chat.id, helper, current_db, text)
            else:
                bot.send_message(message.chat.id, f"❌ <b>Error:</b> {safe_html(msg)}")
                
        # 5. Insert Document
        elif state == "WAITING_FOR_INSERT_DOC":
            USER_STATES.pop(user_id, None)
            success, msg = helper.insert_document(current_db, current_coll, text)
            log_action(user, "Insert Document", f"DB: {current_db}, Coll: {current_coll}, Status: {success}")
            if success:
                bot.send_message(message.chat.id, f"✅ {msg}")
            else:
                bot.send_message(message.chat.id, f"❌ <b>Insert Error:</b>\n<code>{safe_html(msg)}</code>")
            send_collection_dashboard(message.chat.id, helper, current_db, current_coll)
            
        # 6. Update Document
        elif state == "WAITING_FOR_UPDATE_DOC":
            USER_STATES.pop(user_id, None)
            doc_id = USER_TEMP_DATA.pop(user_id, None)
            success, msg = helper.update_document(current_db, current_coll, doc_id, text)
            log_action(user, "Update Document", f"DB: {current_db}, Coll: {current_coll}, Doc ID: {doc_id}, Status: {success}")
            if success:
                bot.send_message(message.chat.id, f"✅ {msg}")
            else:
                bot.send_message(message.chat.id, f"❌ <b>Update Error:</b>\n<code>{safe_html(msg)}</code>")
            send_collection_dashboard(message.chat.id, helper, current_db, current_coll)

        # 7. Create Index
        elif state == "WAITING_FOR_CREATE_INDEX":
            USER_STATES.pop(user_id, None)
            # Input format could be field:1 or field:1,unique
            parts = text.split(",", 1)
            keys = parts[0]
            is_unique = len(parts) > 1 and parts[1].strip().lower() == "unique"
            
            success, msg = helper.create_index(current_db, current_coll, keys, unique=is_unique)
            log_action(user, "Create Index", f"DB: {current_db}, Coll: {current_coll}, Keys: {keys}, Unique: {is_unique}, Status: {success}")
            if success:
                bot.send_message(message.chat.id, f"✅ {msg}")
            else:
                bot.send_message(message.chat.id, f"❌ <b>Index Creation Error:</b>\n<code>{safe_html(msg)}</code>")
            send_indexes_menu(message.chat.id, helper, current_db, current_coll)

        # 8. Custom Find Query
        elif state == "WAITING_FOR_FIND_QUERY":
            USER_STATES.pop(user_id, None)
            bot.send_message(message.chat.id, "🔍 Running custom query...")
            success, res = helper.execute_query(current_db, current_coll, text, skip=0, limit=MAX_DOCS_DISPLAY)
            log_action(user, "Execute Custom Query", f"DB: {current_db}, Coll: {current_coll}, Query: {text}, Status: {success}")
            if success:
                docs = res["documents"]
                total = res["total"]
                if not docs:
                    bot.send_message(message.chat.id, "Empty result set. No documents matched the query filter.")
                else:
                    output = f"🔍 <b>Query Results ({len(docs)}/{total} matches):</b>\n\n"
                    for idx, doc in enumerate(docs):
                        output += f"📄 <b>Doc #{idx+1}:</b>\n<code>{safe_html(json.dumps(doc, indent=2))}</code>\n\n"
                    bot.send_message(message.chat.id, output)
            else:
                bot.send_message(message.chat.id, f"❌ <b>Query Error:</b>\n<code>{safe_html(res)}</code>")
            send_collection_dashboard(message.chat.id, helper, current_db, current_coll)

        # 9. Custom Aggregation Pipeline
        elif state == "WAITING_FOR_AGGREGATION":
            USER_STATES.pop(user_id, None)
            bot.send_message(message.chat.id, "⚙️ Running pipeline aggregation...")
            success, res = helper.execute_aggregation(current_db, current_coll, text)
            log_action(user, "Execute Aggregation", f"DB: {current_db}, Coll: {current_coll}, Pipeline: {text}, Status: {success}")
            if success:
                docs = res["results"]
                total = res["total"]
                if not docs:
                    bot.send_message(message.chat.id, "Empty result set. No records produced by this aggregation pipeline.")
                else:
                    output = f"⚙️ <b>Aggregation Output (First {len(docs)} matches):</b>\n\n"
                    for idx, doc in enumerate(docs):
                        output += f"📄 <b>Doc #{idx+1}:</b>\n<code>{safe_html(json.dumps(doc, indent=2))}</code>\n\n"
                    bot.send_message(message.chat.id, output)
            else:
                bot.send_message(message.chat.id, f"❌ <b>Pipeline Error:</b>\n<code>{safe_html(res)}</code>")
            send_collection_dashboard(message.chat.id, helper, current_db, current_coll)
            
        helper.close()
        return

    # Fallback default response
    bot.send_message(
        message.chat.id,
        "💡 <b>Tip:</b> If you want to connect to a new database, send its connection URL starting with <code>mongodb://</code> or <code>mongodb+srv://</code>.\n"
        "Otherwise, select an option from the keyboards above or check /help."
    )

# ----------------- Custom Visual UI Dashboards -----------------

def send_collection_dashboard(chat_id, helper, db_name, coll_name):
    # Retrieve count and size
    success, collections = helper.list_collections(db_name)
    coll_info = {"count": "Unknown", "size": "Unknown"}
    if success:
        for c in collections:
            if c["name"] == coll_name:
                coll_info = c
                break

    text = (
        f"📄 <b>Collection Manager</b>\n\n"
        f"📁 <b>Database:</b> <code>{safe_html(db_name)}</code>\n"
        f"⚡ <b>Collection:</b> <code>{safe_html(coll_name)}</code>\n"
        f"📊 <b>Total Documents:</b> <code>{coll_info['count']}</code>\n"
        f"💾 <b>Storage Size:</b> <code>{coll_info['readable_size']}</code>\n\n"
        f"Select a command from the control grid below:"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🔍 View Documents", callback_data="nav_docs:0"),
        InlineKeyboardButton("➕ Insert Document", callback_data="nav_insert_doc")
    )
    markup.add(
        InlineKeyboardButton("📝 Custom Find Query", callback_data="nav_find_query"),
        InlineKeyboardButton("⚙️ Aggregate Pipeline", callback_data="nav_aggregate")
    )
    markup.add(
        InlineKeyboardButton("🧮 Manage Indexes", callback_data="nav_indexes"),
        InlineKeyboardButton("📋 Clone Collection", callback_data="nav_clone")
    )
    markup.add(
        InlineKeyboardButton("📥 Export Collection", callback_data="nav_export"),
        InlineKeyboardButton("🗑️ Clear Truncate", callback_data="nav_truncate")
    )
    markup.add(
        InlineKeyboardButton("❌ Drop Collection", callback_data="nav_drop_coll"),
        InlineKeyboardButton("🔙 Back to DB", callback_data=f"sel_db:{db_name}")
    )
    bot.send_message(chat_id, text, reply_markup=markup)

def send_indexes_menu(chat_id, helper, db_name, coll_name):
    success, indexes = helper.get_indexes(db_name, coll_name)
    if not success:
        bot.send_message(chat_id, f"❌ Failed to fetch indexes: {safe_html(indexes)}")
        return
        
    text = f"🧮 <b>Index Directory</b>\nDB: <code>{safe_html(db_name)}</code>\nCollection: <code>{safe_html(coll_name)}</code>\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    
    for idx_name, idx_spec in indexes.items():
        text += f"▪️ <b>Name:</b> <code>{idx_name}</code>\n"
        text += f"   • Specification: <code>{idx_spec}</code>\n\n"
        # We can't delete _id_ index
        if idx_name != "_id_":
            markup.add(InlineKeyboardButton(f"❌ Drop Index '{idx_name}'", callback_data=f"drop_idx:{idx_name}"))
            
    markup.add(
        InlineKeyboardButton("➕ Create Index", callback_data="nav_create_index"),
        InlineKeyboardButton("🔙 Back to Collection", callback_data="nav_back_coll")
    )
    bot.send_message(chat_id, text, reply_markup=markup)

# ----------------- Inline Keyboard Callbacks -----------------

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user = call.from_user
    user_id = user.id
    data = call.data
    chat_id = call.message.chat.id
    
    # Acknowledge callback immediately to avoid UI loading hang
    bot.answer_callback_query(call.id)
    
    # Disconnect Session (independent of client checks)
    if data == "action_disconnect":
        session = db.get_session(user_id)
        masked_url = mask_mongo_url(session["mongo_url"]) if session else "None"
        db.delete_session(user_id)
        USER_STATES.pop(user_id, None)
        USER_TEMP_DATA.pop(user_id, None)
        log_action(user, "Disconnected MongoDB Session", f"URL: {masked_url}")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="🔌 <b>Session Disconnected.</b> All cached database keys and configurations have been wiped. Send a new connection string to start over."
        )
        return

    # Check connection
    helper, session = get_mongo_client(user_id)
    if not helper:
        bot.send_message(chat_id, session)
        return
        
    current_db = session.get("current_db")
    current_coll = session.get("current_coll")

    # 1. Main Dashboard Redirection
    if data == "main_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"📊 <b>Dashboard Panel</b>\nURI: <code>{safe_html(mask_mongo_url(session['mongo_url']))}</code>",
            reply_markup=get_main_dashboard_markup(session)
        )

    # 2. Connection Details
    elif data == "action_conn_details":
        masked = mask_mongo_url(session["mongo_url"])
        log_action(user, "View Connection Details")
        auth_source = "Default"
        try:
            if hasattr(helper.client.options, 'auth_source'):
                auth_source = helper.client.options.auth_source or "Default"
        except Exception:
            pass

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=(
                f"🔑 <b>Connection Secrets & Parameters:</b>\n\n"
                f"🔗 <b>Full URI:</b> <code>{safe_html(masked)}</code>\n"
                f"🌐 <b>Active Host:</b> <code>{safe_html(helper.client.address)}</code>\n"
                f"🛡️ <b>Auth Source:</b> <code>{safe_html(auth_source)}</code>"
            ),
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
        )

    # 3. Server Stats
    elif data == "action_server_stats":
        log_action(user, "Check Server Stats")
        success, info = helper.get_server_info()
        if success:
            uptime_str = f"{info['uptime']}s" if info['uptime'] else "N/A"
            stats_text = (
                f"📊 <b>MongoDB Server Diagnostics:</b>\n\n"
                f"🏷️ <b>Engine Version:</b> <code>{info['version']}</code>\n"
                f"💻 <b>Environment OS:</b> <code>{info['os']}</code>\n"
                f"💾 <b>Word Architecture:</b> <code>{info['bits']} bit</code>\n"
                f"⏱️ <b>Process Uptime:</b> <code>{uptime_str}</code>\n"
                f"🔌 <b>Active Server Connections:</b> <code>{info['connections'] or 'N/A'}</code>\n"
                f"📥 <b>Inbound Bytes:</b> <code>{humanize.naturalsize(info['network_bytes_in']) if info['network_bytes_in'] else 'N/A'}</code>\n"
                f"📤 <b>Outbound Bytes:</b> <code>{humanize.naturalsize(info['network_bytes_out']) if info['network_bytes_out'] else 'N/A'}</code>"
            )
        else:
            stats_text = f"❌ <b>Diagnostics Failed:</b>\n<code>{safe_html(info)}</code>"
            
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=stats_text,
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
        )

    # 4. List Databases
    elif data == "action_list_dbs" or data == "list_dbs":
        log_action(user, "List Databases")
        success, dbs = helper.list_databases()
        if success:
            markup = InlineKeyboardMarkup(row_width=2)
            db_text = "📁 <b>Select database to browse and run commands:</b>\n\n"
            for index, db_info in enumerate(dbs):
                db_text += f"{index+1}. 📁 <b>{safe_html(db_info['name'])}</b> ({db_info['readable_size']})\n"
                markup.add(InlineKeyboardButton(f"📁 {db_info['name']}", callback_data=f"sel_db:{db_info['name']}"))
            markup.add(InlineKeyboardButton("🔙 Back to Main Dashboard", callback_data="main_menu"))
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=db_text, reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"❌ <b>Error:</b> {safe_html(dbs)}", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="main_menu")))

    # 5. Select Database (Show DB Menu)
    elif data.startswith("sel_db:"):
        db_name = data.split(":", 1)[1]
        db.update_session_db_coll(user_id, db_name, None)
        log_action(user, f"Selected Database: {db_name}")
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("📄 View Collections", callback_data="action_list_colls"),
            InlineKeyboardButton("➕ Create Collection", callback_data="nav_create_coll")
        )
        markup.add(
            InlineKeyboardButton("🚨 Drop Database", callback_data="action_drop_db_c"),
            InlineKeyboardButton("🔙 Back to Database List", callback_data="action_list_dbs")
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"📁 <b>Database Manager:</b> <code>{safe_html(db_name)}</code>\n\nChoose an action from the options below:",
            reply_markup=markup
        )

    # 6. List Collections in Database
    elif data == "action_list_colls":
        log_action(user, "List Collections", f"DB: {current_db}")
        success, colls = helper.list_collections(current_db)
        if success:
            if not colls:
                markup = InlineKeyboardMarkup().add(
                    InlineKeyboardButton("➕ Create Collection", callback_data="nav_create_coll"),
                    InlineKeyboardButton("🔙 Back to DB", callback_data=f"sel_db:{current_db}")
                )
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text=f"📄 <b>No collections found</b> inside database <code>{safe_html(current_db)}</code>.",
                    reply_markup=markup
                )
            else:
                markup = InlineKeyboardMarkup(row_width=2)
                coll_text = f"📄 <b>Collections in {safe_html(current_db)}:</b>\n\n"
                for index, c in enumerate(colls):
                    coll_text += f"{index+1}. ⚡ <b>{safe_html(c['name'])}</b> ({c['count']} docs)\n"
                    markup.add(InlineKeyboardButton(f"📄 {c['name']}", callback_data=f"sel_coll:{c['name']}"))
                markup.add(InlineKeyboardButton("🔙 Back to DB Manager", callback_data=f"sel_db:{current_db}"))
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=coll_text, reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"❌ <b>Error:</b> {safe_html(colls)}", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data=f"sel_db:{current_db}")))

    # 7. Select Collection
    elif data.startswith("sel_coll:"):
        coll_name = data.split(":", 1)[1]
        db.update_session_db_coll(user_id, current_db, coll_name)
        log_action(user, "Selected Collection", f"DB: {current_db}, Collection: {coll_name}")
        # Clear message to rebuild cleaner page
        bot.delete_message(chat_id, call.message.message_id)
        send_collection_dashboard(chat_id, helper, current_db, coll_name)

    # 8. Create Collection prompt
    elif data == "nav_create_coll":
        USER_STATES[user_id] = "WAITING_FOR_CREATE_COLL"
        bot.send_message(chat_id, f"📝 <b>Create Collection inside DB '{safe_html(current_db)}':</b>\n\nPlease send the desired name of the collection to create. Type <code>cancel</code> to abort.")

    # 9. Clone Collection prompt
    elif data == "nav_clone":
        USER_STATES[user_id] = "WAITING_FOR_CLONE_COLL"
        bot.send_message(chat_id, f"📋 <b>Clone collection '{safe_html(current_coll)}':</b>\n\nPlease send the name of the TARGET collection where documents should be copied. Target collection must not exist. Type <code>cancel</code> to abort.")

    # 10. Document Navigator (View Documents)
    elif data.startswith("nav_docs:"):
        skip = int(data.split(":")[1])
        log_action(user, "View Documents", f"DB: {current_db}, Coll: {current_coll}, Page/Skip: {skip}")
        
        success, res = helper.view_documents(current_db, current_coll, skip=skip, limit=1)
        if success:
            docs = res["documents"]
            total = res["total"]
            
            if not docs:
                bot.send_message(chat_id, "No documents found in this collection.")
                send_collection_dashboard(chat_id, helper, current_db, current_coll)
            else:
                doc = docs[0]
                doc_str = json.dumps(doc, indent=2)
                # Store document ID in memory for editing / deleting
                doc_id_val = str(doc.get("_id"))
                
                text = (
                    f"📄 <b>Document Viewer</b>\n"
                    f"📁 DB: <code>{safe_html(current_db)}</code> | Collection: <code>{safe_html(current_coll)}</code>\n"
                    f"🔢 Records: <code>{skip+1} of {total}</code>\n\n"
                    f"<code>{safe_html(doc_str)}</code>"
                )
                
                markup = InlineKeyboardMarkup(row_width=3)
                nav_row = []
                if skip > 0:
                    nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"nav_docs:{skip-1}"))
                nav_row.append(InlineKeyboardButton(f"📄 {skip+1}/{total}", callback_data="dummy"))
                if skip < total - 1:
                    nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"nav_docs:{skip+1}"))
                markup.row(*nav_row)
                
                # Editing and Deletion controls
                markup.add(
                    InlineKeyboardButton("✍️ Edit JSON", callback_data=f"act_edit_doc:{doc_id_val}"),
                    InlineKeyboardButton("🗑️ Delete Doc", callback_data=f"act_del_doc_c:{doc_id_val}")
                )
                markup.add(InlineKeyboardButton("🔙 Back to Collection Menu", callback_data="nav_back_coll"))
                
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=text, reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"❌ <b>Error:</b> {safe_html(res)}", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙", callback_data="nav_back_coll")))

    # 11. Navigation back to active collection menu
    elif data == "nav_back_coll":
        bot.delete_message(chat_id, call.message.message_id)
        send_collection_dashboard(chat_id, helper, current_db, current_coll)

    # 12. Insert Document prompt
    elif data == "nav_insert_doc":
        USER_STATES[user_id] = "WAITING_FOR_INSERT_DOC"
        bot.send_message(chat_id, f"➕ <b>Insert Document into '{safe_html(current_coll)}':</b>\n\nPlease send the document JSON object you wish to insert. Example:\n<code>{{\"name\": \"John Doe\", \"role\": \"admin\"}}</code>\n\nType <code>cancel</code> to abort.")

    # 13. Edit Document Callback
    elif data.startswith("act_edit_doc:"):
        doc_id = data.split(":", 1)[1]
        USER_STATES[user_id] = "WAITING_FOR_UPDATE_DOC"
        USER_TEMP_DATA[user_id] = doc_id
        bot.send_message(chat_id, f"✍️ <b>Edit Document (ID: {safe_html(doc_id)}):</b>\n\nPlease send the updated JSON document or fields you wish to set. We will execute an update command (e.g. <code>$set</code> update) using your inputs.\n\nType <code>cancel</code> to abort.")

    # 14. Delete Document Confirmation
    elif data.startswith("act_del_doc_c:"):
        doc_id = data.split(":", 1)[1]
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🚨 YES, DELETE", callback_data=f"act_del_doc:{doc_id}"),
            InlineKeyboardButton("❌ NO, CANCEL", callback_data="nav_back_coll")
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"⚠️ <b>Delete Confirmation</b>\n\nAre you absolutely sure you want to permanently delete the document with ID <code>{safe_html(doc_id)}</code>?",
            reply_markup=markup
        )

    # 15. Execute Delete Document
    elif data.startswith("act_del_doc:"):
        doc_id = data.split(":", 1)[1]
        success, msg = helper.delete_document(current_db, current_coll, doc_id)
        log_action(user, "Delete Document", f"DB: {current_db}, Coll: {current_coll}, Doc ID: {doc_id}, Status: {success}")
        if success:
            bot.send_message(chat_id, "✅ Document deleted successfully.")
        else:
            bot.send_message(chat_id, f"❌ <b>Delete Error:</b>\n<code>{safe_html(msg)}</code>")
        bot.delete_message(chat_id, call.message.message_id)
        send_collection_dashboard(chat_id, helper, current_db, current_coll)

    # 16. Custom query prompts
    elif data == "nav_find_query":
        USER_STATES[user_id] = "WAITING_FOR_FIND_QUERY"
        bot.send_message(chat_id, f"📝 <b>Custom Find Query on '{safe_html(current_coll)}':</b>\n\nPlease send your query JSON filter. Example:\n<code>{{\"age\": {{\"$gte\": 21}}, \"gender\": \"male\"}}</code>\n\nType <code>cancel</code> to abort.")

    # 17. Aggregation prompts
    elif data == "nav_aggregate":
        USER_STATES[user_id] = "WAITING_FOR_AGGREGATION"
        bot.send_message(chat_id, f"⚙️ <b>Aggregation Pipeline on '{safe_html(current_coll)}':</b>\n\nPlease send your pipeline JSON array. Example:\n<code>[{{\"$match\": {{\"status\": \"active\"}}}}, {{\"$group\": {{\"_id\": \"$category\", \"total\": {{\"$sum\": 1}}}}}}]</code>\n\nType <code>cancel</code> to abort.")

    # 18. Export collection records
    elif data == "nav_export":
        log_action(user, "Export Collection", f"DB: {current_db}, Coll: {current_coll}")
        bot.send_message(chat_id, f"📥 <b>Exporting collection '{safe_html(current_coll)}' data...</b>")
        
        success, data_str = helper.export_collection(current_db, current_coll, limit=MAX_EXPORT_DOCS)
        if success:
            # Create in-memory file object
            file_data = io.BytesIO(data_str.encode('utf-8'))
            file_data.name = f"{current_coll}_export.json"
            
            bot.send_document(
                chat_id,
                file_data,
                caption=f"✅ <b>Export Completed!</b>\nDatabase: <code>{safe_html(current_db)}</code>\nCollection: <code>{safe_html(current_coll)}</code>\n⚠️ <i>Maximum export records: {MAX_EXPORT_DOCS}</i>"
            )
        else:
            bot.send_message(chat_id, f"❌ <b>Export Failed:</b>\n<code>{safe_html(data_str)}</code>")

    # 19. Clear Truncate Collection Confirmation
    elif data == "nav_truncate":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("⚠️ YES, TRUNCATE ALL RECORDS", callback_data="action_truncate_execute"),
            InlineKeyboardButton("❌ CANCEL", callback_data="nav_back_coll")
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"🔥 <b>TRUNCATE COLLECTION WARNING!</b>\n\nAre you sure you want to delete <b>ALL</b> documents inside <code>{safe_html(current_db)}.{safe_html(current_coll)}</code>?\nThis cannot be undone!",
            reply_markup=markup
        )

    # 20. Execute Truncate
    elif data == "action_truncate_execute":
        log_action(user, "Truncate Collection", f"DB: {current_db}, Coll: {current_coll}")
        try:
            db_conn = helper.client[current_db]
            result = db_conn[current_coll].delete_many({})
            bot.send_message(chat_id, f"✅ Collection truncated. Deleted {result.deleted_count} documents.")
        except Exception as e:
            bot.send_message(chat_id, f"❌ <b>Truncate failed:</b> {safe_html(e)}")
            
        bot.delete_message(chat_id, call.message.message_id)
        send_collection_dashboard(chat_id, helper, current_db, current_coll)

    # 21. Drop Collection Confirmation
    elif data == "nav_drop_coll":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🚨 YES, DROP COLLECTION", callback_data="action_drop_coll_execute"),
            InlineKeyboardButton("❌ CANCEL", callback_data="nav_back_coll")
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"🚨 <b>DROP COLLECTION WARNING!</b>\n\nAre you sure you want to completely drop collection <code>{safe_html(current_coll)}</code> from database <code>{safe_html(current_db)}</code>?",
            reply_markup=markup
        )

    # 22. Execute Drop Collection
    elif data == "action_drop_coll_execute":
        success, msg = helper.drop_collection(current_db, current_coll)
        log_action(user, "Drop Collection", f"DB: {current_db}, Coll: {current_coll}, Status: {success}")
        if success:
            bot.send_message(chat_id, f"✅ {msg}")
            # Reset active collection and go to database
            db.update_session_db_coll(user_id, current_db, None)
            bot.delete_message(chat_id, call.message.message_id)
            # Resend db panel
            bot.send_message(
                chat_id,
                f"📁 <b>Database Manager:</b> <code>{safe_html(current_db)}</code>",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("📄 View Collections", callback_data="action_list_colls"),
                    InlineKeyboardButton("🔙 Databases", callback_data="action_list_dbs")
                )
            )
        else:
            bot.send_message(chat_id, f"❌ <b>Error:</b> {safe_html(msg)}")
            bot.delete_message(chat_id, call.message.message_id)
            send_collection_dashboard(chat_id, helper, current_db, current_coll)

    # 23. Drop Database Confirmation
    elif data == "action_drop_db_c":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🚨 YES, DROP DATABASE", callback_data="action_drop_db_execute"),
            InlineKeyboardButton("❌ CANCEL", callback_data=f"sel_db:{current_db}")
        )
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"🔥 <b>CRITICAL WARNING: DROP DATABASE</b>\n\nAre you absolutely sure you want to drop database <code>{safe_html(current_db)}</code>? This deletes all collections and files inside it!",
            reply_markup=markup
        )

    # 24. Execute Drop Database
    elif data == "action_drop_db_execute":
        success, msg = helper.drop_database(current_db)
        log_action(user, "Drop Database", f"DB: {current_db}, Status: {success}")
        if success:
            bot.send_message(chat_id, f"✅ {msg}")
            db.update_session_db_coll(user_id, None, None)
            # Re-list databases
            bot.delete_message(chat_id, call.message.message_id)
            # Trigger DB list callback manually
            call.data = "action_list_dbs"
            handle_callbacks(call)
        else:
            bot.send_message(chat_id, f"❌ <b>Error:</b> {safe_html(msg)}")
            # Return to DB manager
            bot.delete_message(chat_id, call.message.message_id)
            call.data = f"sel_db:{current_db}"
            handle_callbacks(call)

    # 25. Indexes Manager
    elif data == "nav_indexes":
        log_action(user, "Manage Indexes", f"DB: {current_db}, Coll: {current_coll}")
        bot.delete_message(chat_id, call.message.message_id)
        send_indexes_menu(chat_id, helper, current_db, current_coll)

    # 26. Create Index prompt
    elif data == "nav_create_index":
        USER_STATES[user_id] = "WAITING_FOR_CREATE_INDEX"
        bot.send_message(chat_id, f"➕ <b>Create Index on '{safe_html(current_coll)}':</b>\n\nPlease send the index definition.\nFormat: <code>field1:1,field2:-1</code> (to specify ascending/descending) or optionally append <code>,unique</code> at the end to make it unique.\n\nExample:\n<code>username:1,unique</code>\n\nType <code>cancel</code> to abort.")

    # 27. Drop Index Callback
    elif data.startswith("drop_idx:"):
        idx_name = data.split(":", 1)[1]
        success, msg = helper.drop_index(current_db, current_coll, idx_name)
        log_action(user, "Drop Index", f"DB: {current_db}, Coll: {current_coll}, Index: {idx_name}, Status: {success}")
        if success:
            bot.send_message(chat_id, f"✅ {msg}")
        else:
            bot.send_message(chat_id, f"❌ <b>Error:</b> {safe_html(msg)}")
        bot.delete_message(chat_id, call.message.message_id)
        send_indexes_menu(chat_id, helper, current_db, current_coll)

    # Close DB helper client
    helper.close()

# Start bot polling
if __name__ == '__main__':
    print("🤖 MongoDB URL Reader bot starting...")
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️ BOT_TOKEN is not configured! Please configure it in config.py or your environment variables.")
    else:
        bot.infinity_polling()
