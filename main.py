import os
import sys
import re
import json
import logging
import requests
import gdown
import numpy as np
from flask import Flask, request
from PIL import Image, ImageOps
import telebot
from tensorflow.keras.models import load_model
import tensorflow as tf
from telebot import util

logging.basicConfig(level=logging.INFO)
API_TOKEN = os.getenv('API_TOKEN')
if not API_TOKEN:
    sys.exit("Ошибка: API-токен не задан в переменных окружениях")

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

MAX_LEN = 4096


def convert_markdown_to_html(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'__(.*?)__', r'<u>\1</u>', text)
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)
    text = re.sub(r'`([^`]*)`', r'<code>\1</code>', text)
    text = re.sub(r'\[(.*?)\\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    return text


def send_long_message(chat_id, text, parse_mode='HTML'):
    try:
        safe_text = convert_markdown_to_html(text or "")
        for part in util.smart_split(safe_text, MAX_LEN):
            bot.send_message(chat_id, part, parse_mode=parse_mode)
    except Exception as e:
        logging.error(f"Ошибка: {e}")


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        temp_path = "temp.jpg"
        with open(temp_path, "wb") as new_file:
            new_file.write(downloaded_file)
        result = cat_dog(temp_path)
        bot.send_message(message.chat.id, result)
        os.remove(temp_path)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка обработки фото: {e}")


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

def load_photo(message,name):
    photo = message.photo[-1]
    file_info = bot.get_file(photo.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    save_path = name
    with open(save_path, 'wb') as new_file:
        new_file.write(downloaded_file)


history_file = "history.json"
history = {}

if os.path.exists(history_file):
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
    except Exception:
        history = {}


def save_history(history):
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error("Ошибка сохранения истории: %s", e)


AI_KEY = os.getenv('AI_KEY')
if not AI_KEY:
    logging.warning("API_KEY не задан: чат-модель будет недоступна")


def chat(user_id, text):
    try:
        if str(user_id) not in history:
            history[str(user_id)] = [
                {"role": "system", "content": "Ты — дружелюбный помощник."}
            ]

        history[str(user_id)].append({"role": "user", "content": text})

        if len(history[str(user_id)]) > 16:
            history[str(user_id)] = [history[str(user_id)][0]] + history[str(user_id)][-15:]

        url = "https://api.intelligence.io.solutions/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_KEY}" if AI_KEY else ""
        }
        data = {
            "model": "deepseek-ai/DeepSeek-R1-0528",
            "messages": history[str(user_id)]
        }

        response = requests.post(url, headers=headers, json=data, timeout=300)
        data = response.json()

        if isinstance(data, dict) and data.get('choices'):
            content = data['choices'][0]['message']['content']
            history[str(user_id)].append({"role": "assistant", "content": content})

            if len(history[str(user_id)]) > 16:
                history[str(user_id)] = [history[str(user_id)][0]] + history[str(user_id)][-15:]

            save_history(history)

            if '</think>' in content:
                return content.split('</think>', 1)[1]
            return content
        else:
            logging.error(f"Ошибка AI: {json.dumps(data, ensure_ascii=False)}")

    except Exception as e:
        logging.error(f"Ошибка при запросе: {e}")
        send_long_message(user_id, f"Ошибка при запросе: {e}, повторите попытку позже")


TFLITE_PATH = "cat_dog_model.h5"
TFLITE_URL = "CAT_DOG_MODEL_URL"
_interpreter = None
_input_details = None
_output_details = None

def ensure_catdog_tflite():
    global _interpreter, _input_details, _output_details
    if _interpreter is None:
        if not os.path.exists(TFLITE_PATH):
            if not TFLITE_URL:
                raise RuntimeError("CAT_DOGS_TFLITE_URL не задан, а локальной модели нет")
            gdown.download(TFLITE_URL, TFLITE_PATH, quiet=False)

        _interpreter = tf.lite.Interpreter(model_path=TFLITE_PATH)
        _interpreter.allocate_tensors()
        _input_details = _interpreter.get_input_details()
        _output_details = _interpreter.get_output_details()
    return _interpreter, _input_details, _output_details


MNIST_PATH = "mnist_model.h5"
_mnist_model = None

def ensure_mnist():
    global _mnist_model
    if _mnist_model is None:
        if not os.path.exists(MNIST_PATH):
            raise RuntimeError("MNIST модель не найдена: mnist_model.h5")
        _mnist_model = load_model(MNIST_PATH, compile=False)
    return _mnist_model

def number_identification(photo):
    try:
        model = ensure_mnist()
        image = Image.open(photo).convert("L")
        image = ImageOps.invert(image)
        image = ImageOps.fit(image, (28, 28), method=Image.Resampling.LANCZOS)
        x = (np.asarray(image).astype(np.float32) / 255.0).reshape(1, 28, 28, 1)
        pred = model.predict(x, verbose=0)
        return str(int(np.argmax(pred)))
    except Exception as e:
        return f"Ошибка распознавания цифры: {e}"


def cat_dog(photo):
    try:
        interpreter, input_details, output_details = ensure_catdog_tflite()

        image = Image.open(photo).convert("RGB")
        image = ImageOps.fit(image, (150, 150), method=Image.Resampling.LANCZOS)
        x = (np.asarray(image).astype(np.float32) / 255.0)[None, ...]

        interpreter.set_tensor(input_details[0]['index'], x)
        interpreter.invoke()
        pred = interpreter.get_tensor(output_details[0]['index'])

        if pred.ndim == 2 and pred.shape[1] == 1:
            confidence = float(pred[0][0])
        elif pred.ndim == 1:
            confidence = float(pred[0])
        else:
            confidence = float(np.ravel(pred)[0])

        return (f"На изображении собака (точность: {confidence:.2f})"
                if confidence >= 0.5 else
                f"На изображении кот (точность: {1 - confidence:.2f})")
    except Exception as e:
        return f"Ошибка при распознавании: {e}"

def ident_number(message):
    load_photo(message, "Number.jpg")
    answer_number = number_identification("Number.jpg")
    bot.send_message(message.chat.id, f"Цифра на фото: {answer_number}")

def ident_cat_dog(message):
    load_photo(message, "Cat_Dog.jpg")
    answer_cat_dog = cat_dog("Cat_Dog.jpg")
    bot.send_message(message.chat.id, answer_cat_dog)

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
    button6 = telebot.types.KeyboardButton(text="Распознование цифр")
    button7 = telebot.types.KeyboardButton(text="Распознование животных")
    keyboardReply.add(button6, button7)


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
    try:
        user_id = str(message.from_user.id)
        text = message.text
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
        elif text == "Распознание цифр":
            send1 = bot.send_message(message.chat.id, "Загрузите изображение цифры")
            bot.register_next_step_handler(send1, ident_number)
        elif text == "Распознавание животных":
            send2 = bot.send_message(message.chat.id, "Загрузите изображение кошки или собаки")
            bot.register_next_step_handler(send2, ident_cat_dog)
        else:
            msg = bot.send_message(message.chat.id, message.text)
            try:
                answer = chat(message.chat.id, text)
                send_long_message(message.chat.id, answer)
            finally:
                try:
                    bot.delete_message(message.chat.id, msg.message_id)
                except Exception:
                    pass
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")


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
