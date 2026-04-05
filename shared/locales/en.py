"""
## English localization for LeadHunter
"""

STRINGS = {
    ## ===== Language selection =====
    "lang": {
        "select": "Please select your language:",
        "btn_ru": "🇷🇺 Русский",
        "btn_en": "🇬🇧 English",
        "changed": "✅ Language changed to English.",
    },

    ## ===== Main menu =====
    "start": {
        "welcome": (
            "👋 <b>Welcome to LeadHunter!</b>\n\n"
            "I will help you find and process leads from Telegram chats.\n\n"
            "🎯 <b>What I can do:</b>\n"
            "• Monitor selected chats for orders\n"
            "• Analyze leads using AI\n"
            "• Suggest reply options and pricing\n"
            "• Send messages from your accounts\n\n"
            "📚 Use /help for detailed instructions.\n"
            "🎛 Choose a section from the menu below:"
        ),
    },

    ## ===== Menu buttons =====
    "menu": {
        "leads": "📬 Leads",
        "stats": "📊 Statistics",
        "chats": "💬 Chats",
        "accounts": "👤 Accounts",
        "profile": "🧑‍💻 Profile",
        "search": "🔍 Search",
        "language": "🌐 Language",
        "back": "🔙 Back",
        "back_to_menu": "🔙 Menu",
        "back_to_list": "🔙 List",
    },

    ## ===== Statistics =====
    "stats": {
        "title": "📊 <b>LeadHunter Statistics</b>\n",
        "total": "📬 <b>Total leads:</b> {count}",
        "new": "🆕 <b>New:</b> {count}",
        "viewed": "👁 <b>Viewed:</b> {count}",
        "replied": "✅ <b>Replied:</b> {count}",
        "ignored": "🚫 <b>Ignored:</b> {count}",
        "footer": "Use the menu for more details.",
    },

    ## ===== Help =====
    "help": {
        "text": (
            "📖 <b>LeadHunter Help</b>\n\n"

            "🎯 <b>Main sections:</b>\n\n"

            "<b>📊 Statistics</b>\n"
            "Overview of leads, chats, and accounts.\n\n"

            "<b>📬 Leads</b>\n"
            "Browse discovered leads:\n"
            "• 🆕 New — not yet reviewed\n"
            "• 👁 Viewed — already opened\n"
            "• ✅ Replied — response sent\n"
            "• 🚫 Ignored — dismissed\n\n"

            "<b>💬 Chats</b>\n"
            "Manage monitored chats:\n"
            "• Add new chats\n"
            "• Enable/disable monitoring\n"
            "• Whitelist and blacklist\n\n"

            "<b>👤 Accounts</b>\n"
            "Manage Telegram accounts:\n"
            "• Add new accounts\n"
            "• Configure communication styles\n"
            "• Activate/deactivate\n\n"

            "<b>⚙️ Settings</b>\n"
            "System configuration:\n"
            "• Search keywords\n"
            "• Sending limits\n"
            "• AI parameters\n\n"

            "💡 <b>Communication styles:</b>\n"
            "🎩 <b>Polite/Business</b> — formal tone\n"
            "😊 <b>Friendly</b> — casual communication\n"
            "💪 <b>Aggressive</b> — assertive style\n\n"

            "🤖 <b>Working with leads:</b>\n"
            "1. Receive a notification about a new lead\n"
            "2. Review the AI analysis card\n"
            "3. Choose an account and reply style\n"
            "4. Edit the text if needed\n"
            "5. Send the message with one button\n\n"

            "❓ <b>Commands:</b>\n"
            "/start — main menu\n"
            "/help — this help page\n"
            "/menu — open menu\n"
            "/stats — quick statistics\n\n"

            "🔐 Only you have access to this bot.\n"
            "📝 All actions are logged for security."
        ),
    },

    ## ===== Unknown command =====
    "unknown_cmd": "❓ Unknown command.\n\nUse /help for instructions or /menu to open the menu.",

    ## ===== Leads =====
    "leads": {
        "empty": "📭 <b>No leads found</b>",
        "not_found": "❌ Lead not found",
        "nav_error": "❌ Navigation error",
        "no_leads": "🔍 No leads found.",
        "title": "📬 Leads ({page}/{total})",
        ## Lead card
        "card": {
            "new_lead": "New lead",
            "message_label": "📝 <b>Message:</b>",
            "open_in_chat": "Open in chat",
            "draft_label": "📨 <b>Draft:</b>",
        },
        ## Lead buttons
        "btn": {
            "send": "✅ Send",
            "regenerate": "🔄 Regenerate",
            "edit": "✏️ Edit",
            "generate": "🤖 Generate reply",
            "skip": "❌ Skip",
            "list": "🔙 List",
            "sent_manually": "✅ Sent manually",
        },
        ## Sending
        "sending": "⏳ Sending...",
        "sent_ok": "✅ <b>Message sent!</b>\n\n👤 Account: {account}\n📝 Text sent via DM.",
        "no_draft": "❌ No draft to send",
        "no_accounts": "❌ No available accounts",
        "no_dm_access": "⚠️ <b>Could not send DM</b>",
        "no_dm_details": "The author has no username / account cannot reach them.\n",
        "draft_copy_label": "📋 <b>Draft for copying:</b>",
        "send_error": "❌ <b>Sending error</b>\n\nPlease try again later.",
        "marked_replied": "✅ Lead #{lead_id} marked as replied.",
        ## Draft editing
        "edit_draft_title": "✏️ <b>Edit draft</b>\n\n",
        "edit_current": "📝 Current text:\n{draft}\n\n",
        "edit_prompt": "Send the new text or /cancel to abort.",
        "edit_no_lead": "❌ Error: no lead selected",
        "edit_saved": "✅ Draft updated\n\n{card}",
        ## Regeneration
        "regen_waiting": "⏳ Generating draft...",
        "regen_feedback_prompt": (
            "✏️ Write what you didn't like about the draft and I'll take it into account.\n\n"
            "Or send <b>-</b> to regenerate without comment.\n"
            "Send /cancel to abort."
        ),
        "regen_cancel": "❌ Regeneration cancelled.",
        "regen_not_found": "❌ Lead not found. Please try again.",
        "regen_in_progress": "⏳ Regenerating draft...",
        "regen_error": "❌ Generation error: {error}",
        ## Author blacklist
        "author_blacklisted": (
            "🚫 <b>Author blacklisted</b>\n\n"
            "👤 {author}\n"
            "Lead #{lead_id} marked as ignored.\n\n"
            "⚠️ Full author filtering will be available in the next version."
        ),
        ## AI request
        "ai_requesting": "⏳ Requesting AI analysis...",
        "ai_done": "✅ Analysis received",
        "ai_error": "❌ AI request error: {error}",
        ## Reply variants
        "variants_title": "💬 <b>AI reply variants:</b>\n",
        "variant_n": "Variant {n}",
        "no_variants": "❌ No reply variants. Request AI analysis.",
        "no_variants_short": "❌ No reply variants",
        ## Account selection
        "account_selected": "✅ <b>Account selected:</b> {label}\n\n💬 Choose a reply variant or type your own:",
        "account_selected_custom": "✅ <b>Account selected:</b> {label}\n\n✏️ Type the message text:\n\nSend /cancel to abort.",
        "data_error": "❌ Failed to load data",
    },

    ## ===== Chats =====
    "chats": {
        "menu_title": (
            "💬 <b>Chat Management</b>\n\n"
            "📊 Total: <b>{total}</b> | Active: <b>{enabled}</b>\n\n"
            "📋 <b>My chats</b> — list and settings\n"
            "➕ <b>Add</b> — by link, @username, or ID\n"
            "🚫 <b>Blacklist</b> — ignored chats\n"
            "🔎 <b>Auto-search</b> — AI-powered channel discovery\n"
            "📡 <b>Subscribe monitor</b> — join all chats (monitor account only)"
        ),
        "btn_my_chats": "📋 My chats",
        "btn_add": "➕ Add",
        "btn_blacklist": "🚫 Blacklist",
        "btn_discovery": "🔎 Auto-search",
        "btn_join_all": "📡 Subscribe monitor",
        "empty": "📭 <b>Chat list is empty</b>\n\nAdd chats for monitoring.",
        "empty_cmd": "📭 <b>Chat list is empty</b>\n\nAdd chats with /add_chat",
        "list_title": "💬 <b>Chat list</b>\n",
        "list_page": "📄 Page {page}/{total} | Total: {count}",
        "btn_add_chat": "➕ Add chat",
        "btn_back_chats": "🔙 Chat menu",
        ## Adding chat
        "add_title": "➕ <b>Add chat to monitoring</b>\n\n",
        "add_methods_btn": (
            "Choose how to add a chat:\n\n"
            "🔗 <b>Method 1: By ID or username</b>\n"
            "Send Chat ID (e.g.: <code>-1001234567890</code>)\n"
            "or username (e.g.: <code>@pythonru</code>)\n\n"
            "📤 <b>Method 2: Forward a message</b>\n"
            "Forward any message from a public channel\n"
            "(⚠️ for private groups use method 1 only)\n\n"
            "💡 <b>How to find Chat ID:</b>\n"
            "1. Add @getmyid_bot to the group\n"
            "2. Type /id\n"
            "3. Copy the Chat ID\n\n"
            "Send /cancel to abort."
        ),
        "add_methods_cmd": (
            "Choose how to add a chat:\n\n"
            "🔗 <b>Method 1: By link</b>\n"
            "Paste a channel link:\n"
            "• <code>https://t.me/pythonru</code>\n"
            "• <code>t.me/pythonru</code>\n\n"
            "📝 <b>Method 2: By username</b>\n"
            "Send channel/group username:\n"
            "• With @: <code>@pythonru</code>\n"
            "• Without @: <code>pythonru</code>\n\n"
            "🆔 <b>Method 3: By Chat ID</b>\n"
            "Send Chat ID (e.g.: <code>-1001234567890</code>)\n\n"
            "📤 <b>Method 4: Forward a message</b>\n"
            "Forward any message from a public channel\n"
            "(⚠️ for private groups use method 2 or 3)\n\n"
            "💡 <b>How to find Chat ID:</b>\n"
            "1. Add @getmyid_bot to the group\n"
            "2. Type /id\n"
            "3. Copy the Chat ID\n\n"
            "Send /cancel to abort."
        ),
        "forward_user_error": (
            "❌ <b>Wrong message type</b>\n\n"
            "You forwarded a message from a user, not from a group or channel.\n\n"
            "💡 <b>How to do it correctly:</b>\n"
            "• Open the group or channel you want to add\n"
            "• Forward any message from that chat\n"
            "• Don't forward personal messages from users\n\n"
            "Try again or send /cancel to abort."
        ),
        "forward_error": "❌ Could not detect the chat from the forwarded message.\nTry again or send /cancel.",
        "already_added": "⚠️ Chat {title} is already in the system.\nID: #{id}\n\nUse /list_chats to view.",
        "added_ok": (
            "✅ <b>Chat added successfully!</b>\n\n"
            "📝 <b>Title:</b> {title}\n"
            "🆔 <b>Chat ID:</b> {tg_chat_id}\n"
            "📂 <b>Type:</b> {type}\n"
            "🔢 <b>Priority:</b> {priority}\n"
            "✅ <b>Monitoring:</b> Enabled\n\n"
            "The chat will be monitored for leads."
        ),
        "getting_info": "⏳ <b>Fetching chat info...</b>\n\nThis may take a few seconds.",
        "interpret_username": "💡 Interpreted as username: {username}",
        "bad_chat_id": (
            "❌ <b>Invalid Chat ID format</b>\n\n"
            "Chat ID must start with a minus sign (e.g.: <code>-1001234567890</code>)\n\n"
            "Or send a channel/group username:\n"
            "• With @: <code>@pythonru</code>\n"
            "• Without @: <code>pythonru</code>\n\n"
            "Try again or send /cancel."
        ),
        "already_added_info": (
            "⚠️ <b>Chat already added</b>\n\n"
            "📝 <b>Title:</b> {title}\n"
            "🆔 <b>ID:</b> #{id}\n\n"
            "Use /list_chats to view."
        ),
        ## Chat card
        "card_title": "💬 <b>{title}</b>\n\n",
        "card_tg_id": "🆔 <b>Telegram ID:</b> {tg_id}\n",
        "card_db_id": "🆔 <b>DB ID:</b> #{id}\n",
        "card_type": "📂 <b>Type:</b> {type}\n",
        "card_username": "🔗 <b>Username:</b> @{username}\n",
        "card_priority": "🔢 <b>Priority:</b> {priority}\n",
        "card_monitoring_on": "✅ <b>Monitoring:</b> Enabled 🟢\n",
        "card_monitoring_off": "✅ <b>Monitoring:</b> Disabled 🔴\n",
        "card_whitelist": "⚪ <b>Whitelist:</b> {status}\n",
        "card_blacklist": "⚫ <b>Blacklist:</b> {status}\n",
        "yes": "Yes",
        "no": "No",
        ## Action buttons
        "btn_disable": "🔴 Disable",
        "btn_enable": "🟢 Enable",
        "btn_whitelist": "⚪ Whitelist",
        "btn_to_blacklist": "⚫ Blacklist",
        "btn_delete": "🗑 Delete",
        ## Actions
        "not_found": "❌ Chat not found",
        "monitoring_on": "✅ Monitoring enabled",
        "monitoring_on_text": "💬 <b>{title}</b>\n\n✅ Chat monitoring enabled.",
        "monitoring_off": "🔴 Monitoring disabled",
        "monitoring_off_text": "💬 <b>{title}</b>\n\n🔴 Chat monitoring disabled.",
        "enable_error": "❌ Error enabling",
        "disable_error": "❌ Error disabling",
        "whitelist_added": "⚪ Chat added to whitelist",
        "whitelist_removed": "⚪ Chat removed from whitelist",
        "whitelist_changed": "💬 <b>{title}</b>\n\n⚪ Whitelist status changed.",
        "whitelist_error": "❌ Error changing status",
        "blacklist_added": "⚫ Chat added to blacklist",
        "blacklist_removed": "⚫ Chat removed from blacklist",
        "blacklist_changed": "💬 <b>{title}</b>\n\n⚫ Blacklist status changed.",
        "blacklist_error": "❌ Error changing status",
        "blacklist_title": "⚫ <b>Chat blacklist</b>\n\n",
        "blacklist_empty": "The list is empty.\n\nAdd chats to ignore.",
        "blacklist_count": "Found: {count}\n\n",
        "blacklist_more": "\n<i>...{count} more</i>",
        ## Deletion
        "delete_confirm": (
            "⚠️ <b>Confirm deletion</b>\n\n"
            "Are you sure you want to delete chat {title}?\n\n"
            "❗ All related leads will also be deleted."
        ),
        "deleted": "✅ <b>Chat deleted</b>\n\nChat {title} has been removed from monitoring.",
        "delete_ok_toast": "🗑 Chat deleted",
        "delete_error": "❌ Error deleting",
        "action_cancelled": "Action cancelled",
        "action_cancelled_text": "💬 <b>{title}</b>\n\nAction cancelled.",
        ## Auto-subscription
        "join_starting": "🔄 Starting monitor subscription...",
        "join_in_progress": (
            "⏳ <b>Monitor account subscription</b>\n\n"
            "Subscribing monitor account to active channels...\n"
            "This may take a while."
        ),
        "join_done": "✅ <b>Auto-subscription complete!</b>\n\n",
        "join_stats": "📊 <b>Statistics:</b>\n",
        "join_success": "✅ Successfully subscribed: {count}\n",
        "join_already": "⏭️ Already subscribed: {count}\n",
        "join_private": "🔒 Private channels: {count}\n",
        "join_flood": "⏳ FloodWait: {count}\n",
        "join_pending": "⏳ Pending approval: {count}\n",
        "join_errors": "❌ Errors: {count}\n",
        "join_private_label": "\n🔒 <b>Private channels:</b> {count}\n",
        "join_pending_label": "⏳ <b>Requests submitted:</b> {count}\n",
        "join_errors_label": "❌ <b>Other errors:</b> {count}\n",
        "join_report_title": "📋 <b>Detailed Report</b>\n",
        "join_flood_label": "\n⏳ <b>FloodWait:</b> {count}\n",
        "join_more": "...+{count} more",
        "join_details_btn": "📋 Error details",
        "join_api_error": "❌ <b>Auto-subscription error</b>\n\nStatus: {status}\nError: {error}",
        "join_timeout": (
            "❌ <b>Timeout</b>\n\n"
            "The subscription process took too long.\n"
            "Some channels may already be added.\n"
            "Try again in a few minutes."
        ),
        "join_unexpected": "❌ <b>Unexpected error</b>\n\n{error}",
    },

    ## ===== Accounts =====
    "accounts": {
        "menu_title": (
            "👤 <b>Account Management</b>\n\n"
            "Here you can add Telegram accounts "
            "that will be used for sending replies to leads."
        ),
        "btn_list": "📋 Account list",
        "btn_add": "➕ Add account",
        "empty": "📭 <b>Account list is empty</b>\n\nAdd accounts to send messages.",
        "empty_cmd": "📭 <b>Account list is empty</b>\n\nAdd accounts with /add_account",
        "list_title": "👤 <b>Account list ({count})</b>\n",
        ## Adding
        "add_title": (
            "➕ <b>Add Telegram Account</b>\n\n"
            "Accounts are used for sending replies to leads.\n\n"
        ),
        "add_label_prompt": (
            "📝 Enter a name (label) for this account.\n"
            "(For example: Work 1, Main)\n\n"
            "Send /cancel to abort."
        ),
        "add_label_prompt_cmd": (
            "📝 Enter a name (label) for this account.\n"
            'For example: "Main", "Backup", "Account1"\n\n'
            "💡 The name must be unique.\n\n"
            "Send /cancel to abort."
        ),
        "label_short": "❌ Name is too short.\nEnter at least 2 characters.",
        "label_long": "❌ Name is too long (max 100 characters).\nEnter a shorter name.",
        "label_exists": "❌ An account named {label} already exists.\nChoose a different name.",
        "phone_prompt": (
            "✅ Name: {label}\n\n"
            "📱 Now enter the account's phone number.\n"
            "Format: +7XXXXXXXXXX or +380XXXXXXXXX\n\n"
            "Send /cancel to abort."
        ),
        "phone_no_plus": "❌ Number must start with +\nExample: +79991234567",
        "phone_short": "❌ Phone number is too short.\nEnter a valid number.",
        "role_prompt": "🎭 <b>Select account role:</b>\n\n👁 <b>Monitoring</b> — subscribed to chats, listens to messages\n✉️ <b>Replies + search</b> — sends replies to leads, Premium search",
        "role_monitor": "👁 Chat monitoring",
        "role_reply": "✉️ Replies + search",
        "role_changed": "✅ Role changed to: {role}",
        "role_error": "❌ Error changing role",
        "data_lost": "❌ Data lost",
        "added_ok": (
            "✅ <b>Account added!</b>\n\n"
            "📝 <b>Name:</b> {label}\n"
            "📱 <b>Phone:</b> {phone}\n"
            "🎭 <b>Role:</b> {role}\n"
            "🆔 <b>ID:</b> #{id}\n\n"
            "⚠️ Authorize the account via CLI on the server:\n"
            "{cli_cmd}"
        ),
        "added_toast": "✅ Account added",
        "add_error": "❌ Error: {error}",
        "add_cancelled": "❌ Account creation cancelled.",
        ## Card
        "card_title": "👤 <b>{label}</b>\n\n",
        "card_db_id": "🆔 <b>DB ID:</b> #{id}\n",
        "card_tg_id": "🆔 <b>Telegram ID:</b> {tg_id}\n",
        "card_phone": "📱 <b>Phone:</b> {phone}\n",
        "card_username": "🔗 <b>Username:</b> @{username}\n",
        "card_role": "🎭 <b>Role:</b> {role}\n",
        "card_status_on": "✅ <b>Status:</b> Active 🟢\n",
        "card_status_off": "✅ <b>Status:</b> Inactive 🔴\n",
        "role_names": {
            "monitor": "👁 Monitoring",
            "reply": "✉️ Replies + search",
            "both": "🔄 Monitoring + replies",
        },
        "not_found": "❌ Account not found",
        ## Buttons
        "btn_auth": "🔐 Authorize",
        "btn_disable": "🔴 Deactivate",
        "btn_enable": "🟢 Activate",
        "btn_role": "🎭 Change role",
        "btn_delete": "🗑 Delete",
        ## Actions
        "enabled": "✅ Account activated",
        "enabled_text": "👤 <b>{label}</b>\n\n✅ Account activated and ready.",
        "enable_error": "❌ Error activating",
        "disabled": "🔴 Account deactivated",
        "disabled_text": "👤 <b>{label}</b>\n\n🔴 Account deactivated.",
        "disable_error": "❌ Error deactivating",
        ## Styles
        "style_prompt": (
            "🎨 <b>Choose a new communication style:</b>\n\n"
            "🎩 <b>Polite/Business</b> — formal tone\n"
            "😊 <b>Friendly</b> — casual communication\n"
            "💪 <b>Aggressive</b> — assertive style"
        ),
        "style_polite": "🎩 Polite/Business",
        "style_friendly": "😊 Friendly",
        "style_aggressive": "💪 Aggressive/Assertive",
        "style_names": {
            "polite": "Polite/Business",
            "friendly": "Friendly",
            "aggressive": "Aggressive",
        },
        "style_changed": "✅ Style changed to {style}",
        "style_changed_text": "👤 <b>{label}</b>\n\n🎨 Style changed successfully.",
        "style_error": "❌ Error changing style",
        ## Deletion
        "delete_confirm": (
            "⚠️ <b>Confirm deletion</b>\n\n"
            "Are you sure you want to delete account {label}?\n\n"
            "❗ All related sent messages will remain in history."
        ),
        "deleted": "✅ <b>Account deleted</b>\n\nAccount {label} has been deleted.",
        "deleted_toast": "🗑 Account deleted",
        "delete_error": "❌ Error deleting",
        "action_cancelled": "Action cancelled",
        "action_cancelled_text": "👤 <b>{label}</b>\n\nAction cancelled.",
        ## Authorization
        "auth_title": "🔐 <b>Authorize account {label}</b>\n\n",
        "auth_phone": "📱 <b>Phone:</b> {phone}\n\n",
        "auth_code_sent": "✅ Authorization code sent to Telegram!\n\n📝 Enter the 5-digit code:\n\nSend /cancel to abort.",
        "auth_no_phone": "❌ Account has no phone number",
        "auth_already": "✅ Account is already authorized",
        "auth_code_invalid": "❌ Code must be 5 digits.\nEnter the code again or send /cancel.",
        "auth_data_lost": "❌ Error: data lost. Please start over.",
        "auth_success": (
            "✅ <b>Account authorized!</b>\n\n"
            "🆔 <b>Telegram ID:</b> {tg_id}\n"
            "🔗 <b>Username:</b> @{username}\n\n"
            "The account is now ready to use!"
        ),
        "auth_2fa_prompt": "🔒 <b>Two-factor authentication required</b>\n\nEnter 2FA password:\n\nSend /cancel to abort.",
        "auth_error": "❌ <b>Authorization error</b>\n\n{error}\n\nTry again or send /cancel.",
        "auth_error_2fa": "❌ <b>Authorization error</b>\n\n{error}\n\nTry again.",
        "auth_password_empty": "❌ Password cannot be empty.\nEnter password again or send /cancel.",
        "auth_cancelled": "❌ Account authorization cancelled.",
    },

    ## ===== Profile =====
    "profile": {
        "title": "🧑‍💻 <b>Freelancer Profile</b>",
        "empty": "Profile is not filled in. Click a button to edit.",
        "stack_label": "🔧 <b>Stack:</b>",
        "spec_label": "🎯 <b>Specialization:</b>",
        "about_label": "📝 <b>About:</b>",
        "budget_label": "💰 <b>Min. budget:</b> {amount:,} ₽",
        "portfolio_label": "🔗 <b>Portfolio:</b>",
        "not_set": "not set",
        "not_set_f": "not set",
        "footer": "Profile is used for generating personalized auto-replies.",
        "btn_stack": "🔧 Stack",
        "btn_spec": "🎯 Specialization",
        "btn_about": "📝 About",
        "btn_budget": "💰 Min. budget",
        "btn_portfolio": "🔗 Portfolio",
        "btn_back": "🔙 Menu",
        "prompt_stack": "🔧 Enter your technology stack (comma-separated):\n\nExample: Python, aiogram, Telethon, Next.js, PostgreSQL, Docker",
        "prompt_spec": "🎯 Enter your specialization:\n\nExample: Telegram bots, web apps, automation, AI integrations",
        "prompt_about": "📝 Tell about yourself (1-3 sentences):\n\nThis text will be used for generating auto-replies.",
        "prompt_budget": "💰 Enter minimum project budget (number in rubles):\n\nExample: 15000",
        "prompt_portfolio": "🔗 Enter portfolio link:\n\nExample: https://github.com/username",
        "cancel_prompt": "\n\nSend /cancel to abort.",
        "saved": "✅ Saved!",
        "budget_negative": "❌ Budget cannot be negative. Try again.",
        "budget_invalid": "❌ Enter a number. Example: 15000",
        "edit_cancelled": "❌ Editing cancelled.",
        "unknown_field": "❌ Unknown field",
    },

    ## ===== Search =====
    "search": {
        "menu_title": "🔍 <b>Global Search (Premium)</b>\n\n",
        "phrases_count": "📋 Phrases: {count}",
        "today_count": "📊 Searches today: {count}/10",
        "footer": "Search uses Telegram search_global (Premium).",
        "btn_phrases": "📋 My phrases",
        "btn_add": "➕ Add phrase",
        "btn_run": "🚀 Run search",
        "btn_back": "🔙 Menu",
        "phrases_title": "📋 <b>Search phrases</b>",
        "phrases_empty": "No phrases yet. Add the first one!",
        "phrase_used": "never",
        "add_title": "➕ <b>Add search phrase</b>\n\n",
        "add_prompt": "Enter a search phrase:\n\nExamples:\n",
        "add_cancel_prompt": "\n\nSend /cancel to abort.",
        "add_short": "❌ Phrase is too short. Minimum 3 characters.",
        "add_ok": "✅ Phrase added: {text}\nID: #{id}",
        "toggle_on": "✅ Phrase enabled",
        "toggle_off": "⛔ Phrase disabled",
        "not_found": "❌ Phrase not found",
        "deleted": "🗑 Phrase deleted",
        "run_starting": "⏳ Starting search...",
        "run_done": "✅ <b>Search complete</b>\n\n",
        "run_queries": "🔍 Queries: {count}",
        "run_found": "📊 Found: {count}",
        "run_leads": "🎯 Leads: {count}",
        "run_errors": "⚠️ Errors: {errors}",
        "run_error": "❌ <b>Search error</b>\n\n{error}",
        "run_timeout": "⏳ <b>Search started</b>\n\nResults will appear in leads.",
        "run_unexpected": "❌ <b>Error</b>\n\n{error}",
        "add_cancelled": "❌ Addition cancelled.",
    },

    ## ===== Channel Discovery =====
    "discovery": {
        "menu_title": (
            "🔍 <b>Auto-search channels</b>\n\n"
            "The system automatically finds relevant Telegram channels "
            "for lead monitoring and evaluates them using AI.\n\n"
        ),
        "stats_title": "📊 <b>Candidate statistics:</b>\n",
        "stats_total": "• Total found: {count}\n",
        "stats_pending": "• Pending review: {count}\n",
        "stats_added": "• Added to monitoring: {count}\n",
        "stats_rejected": "• Rejected: {count}\n",
        "action_prompt": "\nChoose an action:",
        "btn_start": "🚀 Start search",
        "btn_view": "⭐ View recommendations",
        "btn_add_top": "➕ Add best",
        "search_started": "🚀 <b>Starting channel search...</b>\n\n",
        "search_keywords": "Searching channels by keywords:\n",
        "search_more": "and {count} more...",
        "search_wait": "\n\n⏳ This may take a few minutes...\nI'll find channels, collect posts, and run AI evaluation.",
        "search_done": "✅ <b>Search complete!</b>\n\n🎯 New channels found: {count}\n\n",
        "search_overall": "📊 <b>Overall statistics:</b>\n",
        "search_view_prompt": "\nUse the button below to view recommendations.",
        "search_timeout": "⏱ <b>Timeout</b>\n\nChannel search took too long.\nTry again or reduce the number of keywords.",
        "search_error": "❌ <b>Channel search error</b>\n\nError: {error}\n\nTry again later or contact the administrator.",
        "no_recommendations": "🤷 <b>No recommended channels</b>\n\nRun auto-search to find new channels.",
        "candidate_card": "📺 <b>Channel {index} of {total}</b>\n\n",
        "no_username": "(no username)",
        "metrics_title": "📊 <b>Metrics:</b>\n",
        "members": "• Subscribers: {count}\n",
        "source": "• Source: {source}\n",
        "ai_score": "🤖 <b>AI score:</b> {emoji} {score}/10\n",
        "ai_content_type": "📁 <b>Content type:</b> {type}\n\n",
        "ai_comment": "💬 <b>AI comment:</b>\n{comment}\n\n",
        "open_link": "🔗 Open channel",
        "btn_add_monitoring": "✅ Add to monitoring",
        "btn_ignore": "🚫 Ignore",
        "btn_prev": "◀️ Previous",
        "btn_next": "▶️ Next",
        "btn_menu": "🔙 Menu",
        "candidates_empty": "❌ Candidate list is empty",
        "candidate_not_found": "❌ Candidate not found",
        "already_in_list": "ℹ️ This channel is already in the list",
        "added_to_monitoring": "✅ Channel '{title}' added to monitoring!",
        "all_reviewed": "🎉 <b>All recommended channels reviewed!</b>\n\nRun a new search or go back to the menu.",
        "all_reviewed_short": "🎉 <b>All recommended channels reviewed!</b>",
        "ignored_toast": "🚫 Channel rejected",
        "mass_add_progress": "⏳ Adding best channels to monitoring...",
        "mass_add_done": (
            "✅ <b>Mass addition complete!</b>\n\n"
            "• Channels added: {added}\n"
            "• Skipped (already exist): {skipped}\n\n"
            "These channels will now be monitored automatically."
        ),
        "back_title": "💬 <b>Chat Management</b>\n\nChoose an action:",
    },

    ## ===== Settings =====
    "settings": {
        "title": "⚙️ <b>LeadHunter Settings</b>\n\n<b>Current settings:</b>\n\n",
        "ai_primary": "🤖 <b>AI model (primary):</b> {model}\n",
        "ai_secondary": "🤖 <b>AI model (secondary):</b> {model}\n",
        "ai_timeout": "⏱ <b>AI timeout:</b> {timeout}s\n\n",
        "max_replies": "📊 <b>Max replies/hour:</b> {count}\n",
        "send_delay": "⏳ <b>Send delay:</b> {min}-{max}s\n\n",
        "edit_hint": "💡 <i>To change settings, edit .env and restart containers</i>",
    },

    ## ===== Common =====
    "common": {
        "confirm_yes": "✅ Yes, confirm",
        "confirm_no": "❌ No, cancel",
        "cancel": "❌ Cancelled",
        "error": "❌ Error",
        "page_indicator": "📄 {current}/{total}",
        "prev": "◀️ Back",
        "next": "▶️ Next",
        "forward": "Next ▶️",
        "channel_n": "📺 Channel {n}",
    },

    ## ===== BotCommands =====
    "commands": {
        "start": "Main menu",
        "leads": "Lead list",
        "help": "Help",
    },

    ## ===== AI prompts =====
    "ai": {
        "summary_system": "You are an experienced IT services sales manager.",
        "analysis_lang": "en",
    },
}
