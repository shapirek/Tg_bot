from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext
import requests
import random
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO

TOKEN = "7214391494:AAHEagSkALsaia3rVgWPtlnPZS9N68DRtZc"
OPENWEATHER_API_KEY = "6e0ea17093bc39b95edab1633fb20462"
users = {}

def get_current_temperature(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&APPID={OPENWEATHER_API_KEY}&units=metric"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data['main']['temp']
    return None

def check_goal_progress(update: Update, context: CallbackContext, user_id: str):
    user = users[user_id]
    messages = []

    # Проверка воды
    current_water = user["logged_water"]
    water_goal = user["water_goal"]
    water_percent = current_water / water_goal

    if current_water < water_goal:
        user["water_goal_reached"] = False

    if water_percent >= 1 and not user.get("water_goal_reached"):
        messages.append("Поздравляем, вы достигли нормы по воде!")
        user["water_goal_reached"] = True

    # Проверка калорий (учитываем чистые калории: потреблено минус сожжено)
    current_calories = user["logged_calories"] - user["burned_calories"]
    calorie_goal = user["calorie_goal"]
    calorie_percent = current_calories / calorie_goal

    if current_calories < calorie_goal:
        user["calorie_goal_reached"] = False

    if calorie_percent >= 1 and not user.get("calorie_goal_reached"):
        messages.append("Поздравляем, вы достигли нормы по калориям!")
        user["calorie_goal_reached"] = True

    if current_calories > 2 * calorie_goal:
        messages.append("Пора потренироваться! Вы превысили норму калорий в 2 раза!")

    if messages:
        update.effective_message.reply_text("\n".join(messages))

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Запустите настройку профиля с помощью команды /set_profile или выберите действие через /menu.")

def set_profile(update: Update, context: CallbackContext):
    user_id = str(update.effective_chat.id)
    users[user_id] = {"state": "weight"}
    update.effective_message.reply_text("Введите ваш вес (в кг):")

def handle_message(update: Update, context: CallbackContext):
    user_id = str(update.effective_chat.id)
    if user_id not in users or users[user_id].get("state") is None:
        update.effective_message.reply_text("Сначала используйте команду /set_profile.")
        return

    state = users[user_id]["state"]
    text = update.message.text

    try:
        if state == "weight":
            users[user_id]["weight"] = float(text)
            users[user_id]["state"] = "height"
            update.effective_message.reply_text("Введите ваш рост (в см):")

        elif state == "height":
            users[user_id]["height"] = float(text)
            users[user_id]["state"] = "age"
            update.effective_message.reply_text("Введите ваш возраст:")

        elif state == "age":
            users[user_id]["age"] = int(text)
            users[user_id]["state"] = "activity"
            update.effective_message.reply_text("Сколько минут активности у вас в день?")

        elif state == "activity":
            users[user_id]["activity"] = int(text)
            users[user_id]["state"] = "city"
            update.effective_message.reply_text("В каком городе вы находитесь?")

        elif state == "city":
            users[user_id]["city"] = text
            temp = get_current_temperature(text)
            extra_msg = ""
            if temp is not None:
                users[user_id]["city_temperature"] = temp
                if temp > 25:
                    extra_msg = "У вас жарко! Норма потребления воды увеличена.\n"
            # Расчёт нормы воды на основе веса, активности и температуры:
            weight = users[user_id]["weight"]
            activity = users[user_id]["activity"]
            water_goal = weight * 30 + (activity // 30) * 500
            if temp is not None and temp > 25:
                water_goal += 500
            update.effective_message.reply_text(
                f"{extra_msg}Норма воды на сегодня: {water_goal} мл/день\n"
                f"Рекомендуемая цель по калориям: 2000 ккал/день"
            )
            users[user_id]["state"] = "calorie_goal"
            update.effective_message.reply_text("Введите цель по калориям (по желанию):")

        elif state == "calorie_goal":
            users[user_id]["calorie_goal"] = float(text) if text else 2000
            finalize_profile(update, user_id)

    except ValueError:
        update.effective_message.reply_text("Пожалуйста, введите корректное значение.")

def finalize_profile(update: Update, user_id):
    user = users[user_id]
    weight = user["weight"]
    activity = user["activity"]

    water_goal = weight * 30 + (activity // 30) * 500
    if user.get("city_temperature", 0) > 25:
        water_goal += 500

    users[user_id].update({
        "water_goal": water_goal,
        "logged_water": 0,
        "logged_calories": 0,
        "burned_calories": 0,
        "state": None,
        "water_log": [],
        "calorie_log": [],
        "water_goal_reached": False,
        "calorie_goal_reached": False
    })

    update.effective_message.reply_text(
        f"Профиль настроен!\n"
        f"Норма воды: {water_goal} мл/день\n"
        f"Цель по калориям: {user['calorie_goal']} ккал/день\n"
        "Чтобы вернуться к меню, введите команду /menu"
    )

def log_workout(update: Update, context: CallbackContext):
    user_id = str(update.effective_chat.id)
    if user_id not in users:
        update.effective_message.reply_text("Сначала настройте профиль с помощью команды /set_profile.")
        return

    if not context.args or len(context.args) < 2:
        update.effective_message.reply_text("Используйте команду в формате: /log_workout <тип тренировки> <время (мин)>.")
        return

    workout_type = context.args[0].lower()
    try:
        workout_duration = int(context.args[1])
        workout_calories = {"бег": 10, "плавание": 8, "велосипед": 7}

        if workout_type not in workout_calories:
            update.effective_message.reply_text("Неизвестный тип тренировки. Доступные варианты: бег, плавание, велосипед")
            return

        calories_burned = workout_calories[workout_type] * workout_duration
        users[user_id]["burned_calories"] += calories_burned
        # Добавляем сожжённые калории как отрицательное значение для построения графика
        users[user_id]["calorie_log"].append(-calories_burned)

        # Расчёт потери воды во время тренировки (например, 200 мл за каждые 30 минут)
        water_loss = (workout_duration // 30) * 200
        users[user_id]["logged_water"] -= water_loss
        users[user_id]["water_log"].append(-water_loss)

        check_goal_progress(update, context, user_id)

        update.effective_message.reply_text(
            f"{workout_type.capitalize()} {workout_duration} мин\n"
            f"Сожжено калорий: {calories_burned} ккал\n"
            f"Потеряно воды: {water_loss} мл"
        )

        # После тренировки отправляем графики по воде и калориям
        water_buf = generate_water_plot(users[user_id])
        calorie_buf = generate_calorie_plot(users[user_id])
        if water_buf:
            update.effective_message.reply_photo(photo=water_buf)
        if calorie_buf:
            update.effective_message.reply_photo(photo=calorie_buf)

    except ValueError:
        update.effective_message.reply_text("Пожалуйста, введите корректные значения.")

def generate_water_plot(user):
    water_log = user.get("water_log", [])
    if not water_log:
        return None
    cumulative = np.cumsum(water_log)
    plt.figure(figsize=(6, 4))
    plt.plot(range(1, len(cumulative) + 1), cumulative, marker='o', label='Выпитая вода (с учётом потерь)')
    plt.axhline(y=user["water_goal"], color='r', linestyle='--', label='Цель')
    plt.title('Динамика потребляемой воды')
    plt.xlabel('Количество записей')
    plt.ylabel('Вода (мл)')
    plt.legend()
    buf = BytesIO()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)
    return buf

def generate_calorie_plot(user):
    calorie_log = user.get("calorie_log", [])
    if not calorie_log:
        return None
    cumulative = np.cumsum(calorie_log)
    plt.figure(figsize=(6, 4))
    plt.plot(range(1, len(cumulative) + 1), cumulative, marker='o', label='Потребленные калории')
    plt.axhline(y=user["calorie_goal"], color='r', linestyle='--', label='Цель')
    plt.title('Динамика потребляемых калорий')
    plt.xlabel('Количество записей')
    plt.ylabel('Калории')
    plt.legend()
    buf = BytesIO()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)
    return buf

def log_water(update: Update, context: CallbackContext):
    user_id = str(update.effective_chat.id)
    if user_id not in users:
        update.effective_message.reply_text("Сначала настройте профиль с помощью команды /set_profile.")
        return

    if not context.args:
        update.effective_message.reply_text("Используйте команду в формате: /log_water <количество>.")
        return

    try:
        amount = int(context.args[0])
        users[user_id]["logged_water"] += amount
        check_goal_progress(update, context, user_id)
        users[user_id]["water_log"].append(amount)
        update.effective_message.reply_text(f"Вы выпили {amount} мл воды. Всего: {users[user_id]['logged_water']} мл.")

        buf = generate_water_plot(users[user_id])
        if buf:
            update.effective_message.reply_photo(photo=buf)
    except ValueError:
        update.effective_message.reply_text("Пожалуйста, введите число мл выпитой воды.")

def log_food(update: Update, context: CallbackContext):
    user_id = str(update.effective_chat.id)
    if user_id not in users:
        update.effective_message.reply_text("Сначала настройте профиль с помощью команды /set_profile.")
        return

    if not context.args:
        update.effective_message.reply_text("Используйте команду в формате: /log_food <название продукта>.")
        return

    try:
        product_name = " ".join(context.args)
        food_info = get_food_info(product_name)
        if food_info is None:
            update.effective_message.reply_text("Не удалось найти информацию о продукте.")
            return

        calories = food_info["calories"]
        users[user_id]["logged_calories"] += calories
        users[user_id]["calorie_log"].append(calories)

        # Проверка, если после потребления текущего продукта (с калорийностью > 100)
        # суммарное количество потреблённых калорий (за вычетом сожжённых) >= 1.5 * нормы,
        # тогда выводим сообщение с рекомендацией.
        current_total = users[user_id]["logged_calories"] - users[user_id]["burned_calories"]
        if calories > 100 and current_total >= 1.5 * users[user_id]["calorie_goal"]:
            suggestion = get_random_low_calorie_product()
            if suggestion:
                update.effective_message.reply_text(
                    f"Количество потребленных калорий существенно больше нормы. Рекомендуем заняться спортом или употреблять низкокалорийные продукты, например {suggestion['name']} ({suggestion['calories']:.2f} ккал)"
                )

        check_goal_progress(update, context, user_id)

        update.effective_message.reply_text(
            f"{food_info['name']} содержит {calories:.2f} ккал. Всего потреблено: {users[user_id]['logged_calories']} ккал."
        )

        buf = generate_calorie_plot(users[user_id])
        if buf:
            update.effective_message.reply_photo(photo=buf)
    except Exception as e:
        print(f"Ошибка в log_food: {e}")
        update.effective_message.reply_text("Произошла ошибка. Попробуйте снова.")

def get_food_info(product_name):
    url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={product_name}&json=true"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        products = data.get("products", [])
        if products:
            first_product = products[0]
            return {
                "name": first_product.get("product_name", "Неизвестно"),
                "calories": float(first_product.get("nutriments", {}).get("energy-kcal_100g", 0))
            }
    return None

def get_random_low_calorie_product():
    url = "https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms=&page_size=100&json=true"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        products = data.get("products", [])
        low_cal_products = []
        for product in products:
            nutriments = product.get("nutriments", {})
            try:
                calories = float(nutriments.get("energy-kcal_100g", 0))
                if 0 < calories < 100:
                    product_name = product.get("product_name", "Неизвестно")
                    low_cal_products.append({"name": product_name, "calories": calories})
            except (ValueError, TypeError):
                continue
        if low_cal_products:
            return random.choice(low_cal_products)
    return None

def check_progress(update: Update, context: CallbackContext):
    user_id = str(update.effective_chat.id)
    if user_id not in users:
        update.effective_message.reply_text("Сначала настройте профиль с помощью команды /set_profile.")
        return

    user = users[user_id]
    water_remaining = max(0, user["water_goal"] - user["logged_water"])
    calorie_balance = user["logged_calories"] - user["burned_calories"]

    update.effective_message.reply_text(
        f"Прогресс:\n"
        f"Вода:\n"
        f"- Выпито: {user['logged_water']} мл из {user['water_goal']} мл\n"
        f"- Осталось: {water_remaining} мл\n\n"
        f"Калории:\n"
        f"- Потреблено: {user['logged_calories']} ккал\n"
        f"- Сожжено: {user['burned_calories']} ккал\n"
        f"- Итого: {calorie_balance} ккал"
    )

def menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Настроить профиль", callback_data="set_profile")],
        [InlineKeyboardButton("Записать воду", callback_data="log_water"),
         InlineKeyboardButton("Записать еду", callback_data="log_food")],
        [InlineKeyboardButton("Записать тренировку", callback_data="log_workout")],
        [InlineKeyboardButton("Проверить прогресс", callback_data="check_progress")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Главное меню:", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    if query.data == "log_workout":
        query.message.reply_text("Введите данные через команду: /log_workout <тип> <время>")
    elif query.data == "set_profile":
        set_profile(update, context)
    elif query.data == "log_water":
        query.message.reply_text("Введите количество воды: /log_water <мл>")
    elif query.data == "log_food":
        query.message.reply_text("Введите продукт: /log_food <название>")
    elif query.data == "check_progress":
        check_progress(update, context)

def main():
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    handlers = [
        CommandHandler("start", start),
        CommandHandler("set_profile", set_profile),
        CommandHandler("menu", menu),
        CommandHandler("log_water", log_water),
        CommandHandler("log_food", log_food),
        CommandHandler("log_workout", log_workout),
        CommandHandler("check_progress", check_progress),
        MessageHandler(Filters.text & ~Filters.command, handle_message),
        CallbackQueryHandler(button_handler)
    ]

    for handler in handlers:
        dispatcher.add_handler(handler)

    print("Бот запущен...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
