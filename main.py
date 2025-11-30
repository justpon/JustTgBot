import telebot
import json
from flask import Flask, request
import os
import sys
import requests
import logging


logging.basicConfig(level=logging.INFO)
API_TOKEN = os.getenv('API_TOKEN')
if not API_TOKEN:
    sys.exit("Ошибка: API-токен не задан в переменных окружениях")

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

@app.route('/')
def index():
    return "Бот запущен"

@app.route(f'/{API_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data(as_text=True)
        update = telebot.types.Update.de_json(json_str)
        if update:
            bot.process_new_updates([update])
    except Exception as e:
        app.logger.exception(f"Webhook error: {str(e)}")
    return '', 200

def load_db():
    try:
        with open("db.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_db(data):
    with open("db.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
db = load_db()

@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)

    if user_id not in db:
        db[user_id] = {"name": None, "age": None, "money": 777, "state": "awaiting_name"}
        save_db(db)
        bot.send_message(message.chat.id, "Привет! Как тебя зовут?")
        return


    db[user_id]["money"] = 9999999

    keyboardReply = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)

    helpbutton = telebot.types.KeyboardButton("Помощь")
    infobutton = telebot.types.KeyboardButton("Инфо")
    aboutbutton = telebot.types.KeyboardButton("О боте")
    linkbutton = telebot.types.KeyboardButton("Ссылка на чат")
    slotMachineButton = telebot.types.KeyboardButton("Игровой автомат")
    diceButton = telebot.types.KeyboardButton("Игра в кубик")
    quizButton = telebot.types.KeyboardButton("Викторина")
    guessNumberButton = telebot.types.KeyboardButton("Угадай число")

    keyboardReply.add(helpbutton, infobutton, aboutbutton, slotMachineButton, linkbutton, diceButton, quizButton, guessNumberButton)

    bot.send_message(message.chat.id, "Hello World", reply_markup=keyboardReply)

@bot.message_handler(commands=['info'])
def info(message):
    bot.send_message(message.chat.id, "Данный бот пока что нечего не делает")

@bot.message_handler(commands=['help'])
def help(message):
    bot.send_message(message.chat.id, "Тебе ни кто не поможет:)")

@bot.message_handler(content_types=['text'])
def text_event(message):
    user_id = str(message.from_user.id)

    if "awaiting_name" == db.get(user_id, {}).get("state"):
        name = message.text.strip()
        db[user_id]["name"] = name
        db[user_id]["state"] = "awaiting_age"
        save_db(db)
        bot.send_message(message.chat.id, f"Приятно познакомится {name}")
        bot.send_message(message.chat.id, "Сколько тебе лет?")
        return
    elif db.get(user_id, {}).get("state") == "awaiting_age":
        try:
            age = message.text
            db[user_id]["age"] = age
            db[user_id]["state"] = None
            save_db(db)
            start(message)
            return
        except Exception as e:
            print(str(e))
            bot.send_message(message.chat.id, "Ты ввел некорректное значение возраста")
            return

    if message.text == "Помощь":
        bot.send_message(message.chat.id, "Пока что помогать не с чем")
    elif message.text == "Как меня зовут?":
        user_name = db[user_id]["name"]
        bot.send_message(message.chat.id, f"Тебя зовут {user_name}")
    elif message.text == "Инфо":
        bot.send_message(message.chat.id, "Информации к сожелению нету")
    elif message.text == "О боте":
        bot.send_message(message.chat.id, "Бот нечего не делает:)")
    elif message.text == "Игровой автомат":
        if db[user_id]["money"] >= 100:
            value = bot.send_dice(message.chat.id, emoji='🎰').dice.value

            if value in (1, 22, 43):
                bot.send_message(message.chat.id, "Победа")
                db[user_id]["money"] += 50000
            elif value in (16, 32, 48):
                bot.send_message(message.chat.id, "Победа")
                db[user_id]["money"] += 50000
            elif value == 64:
                bot.send_message(message.chat.id, "JACKPOT!!!!!!")
                db[user_id]["money"] += 77777777777777777
            else:
                db[user_id]["money"] -= 100
                bot.send_message(message.chat.id, "Неудача!!!")

    elif message.text == "привет":
        bot.send_message(message.chat.id, "Привет!")
    elif message.text == "":
        bot.send_message(message.chat.id, "?")

    elif message.text == "Угадай число (1-100)":
        import random
        secret_number = random.randint(1, 100)
        db[user_id]["guess_number"] = secret_number
        db[user_id]["state"] = "guessing_number"
        save_db(db)
        bot.send_message(message.chat.id, "Я загадал число от 1 до 100. Попробуй угадать")
        return

    elif db.get(user_id, {}).get("state") == "guessing_number":
        try:
            guess = int(message.text.strip())
            secret_number = db[user_id]["guess_number"]
            if guess == secret_number:
                bot.send_message(message.chat.id, "Поздравляю! Ты угадал число!")
                db[user_id]["state"] = None
                del db[user_id]["guess_number"]
                save_db(db)
            elif guess < secret_number:
                bot.send_message(message.chat.id, "Число больше, Попробуй еще раз.")
            else:
                bot.send_message(message.chat.id, "Число меньше, Попробуй еще раз.")
        except:
            bot.send_message(message.chat.id, "Некорректное число.")
        return


    elif message.text == "Игра в кубик":
        inlineKeyboard = telebot.types.InlineKeyboardMarkup(row_width=3)
        btn1 = telebot.types.InlineKeyboardButton("1", callback_data="1")
        btn2 = telebot.types.InlineKeyboardButton("2", callback_data="2")
        btn3 = telebot.types.InlineKeyboardButton("3", callback_data="3")
        btn4 = telebot.types.InlineKeyboardButton("4", callback_data="4")
        btn5 = telebot.types.InlineKeyboardButton("5", callback_data="5")
        btn6 = telebot.types.InlineKeyboardButton("6", callback_data="6")

        inlineKeyboard.add(btn1, btn2, btn3, btn4, btn5, btn6)

        bot.send_message(message.chat.id, "Угадай число на кубике", reply_markup=inlineKeyboard)



@bot.callback_query_handler(func=lambda call: call.data in ('1', '2', '3', '4', '5', '6'))
def dice_callback(call):
    value = bot.send_dice(call.message.chat.id, emoji='🎲').dice.value
    if str(value) == call.data:
        bot.send_message(call.message.chat.id, "Ты угадал!!!")
    else:
        bot.send_message(call.message.chat.id, "Попробуй ещё раз")

if __name__ == '__main__':
    server_url = os.getenv("RENDER_EXTERNAL_URL")
    if server_url and API_TOKEN:
        webhook_url = f"{server_url.rstrip('/')}/{API_TOKEN}"

        try:
            r = requests.get(f"https://api.telegram.org/bot{API_TOKEN}/setWebhook",
                             params={"url": webhook_url}, timeout=10)
            logging.info(f"Вебхук установлен: {r.text}")
        except Exception:
            logging.exception("Ошибка при установке webhook")

        port = int(os.getenv("PORT", 10000))
        logging.info(f"Запуск на порте {port}")
        app.run(host='0.0.0.0', port=port)
    else:
        logging.info("Запуск бота в режиме Polling")
        bot.remove_webhook()
        bot.infinity_polling(timeout=60 )


