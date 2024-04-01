import aiohttp
import typing as tp
from aiogram import executor

from PIL import Image
from io import BytesIO

from googlesearch import search
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

import os

from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN: str = os.getenv("BOT_TOKEN_")
X_API_KEY: str = os.getenv("X_API_KEY_")

storage = MemoryStorage()

conn = sqlite3.connect('history.db')

HI_MESSAGE: str = 'Меня зовут cinemabot, и я помогу тебе в поиске фильма!\nЧтобы узнать, что я могу, введи /help'

HELP_MESSAGE: str = 'Чтобы я нашёл фильм для тебя, отправь мне сообщение с названием фильма.\n\
Например: Ход королевы.\nТакже я могу дать тебе краткое описание фильма и вернуть \
ссылку для его просмотра. \nПо команде /history расскажу твою историю запросов \n\
По команде /stats расскажу какие фильмы ты искал и сколько раз.'

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=storage)

X_API_KEY = X_API_KEY
cursor = conn.cursor()

# Создание таблицы для истории поисковых запросов
cursor.execute('''
    CREATE TABLE IF NOT EXISTS searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        query TEXT
    )
''')
conn.commit()

# Создание таблицы для статистики предлагаемых фильмов
cursor.execute('''
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        movie_name TEXT,
        count INTEGER DEFAULT 0
    )
''')
conn.commit()


async def fetch(session: aiohttp.ClientSession, url: str) -> bytes:
    async with session.get(url) as response:
        return await response.read()


@dp.message_handler(commands=['start'])
async def process_start_command(message: types.Message) -> None:
    name: str = message.from_user.first_name
    await message.answer(f"Привет {name}!\n{HI_MESSAGE}")


@dp.message_handler(commands=['help'])
async def process_help_command(message: types.Message) -> None:
    await message.answer(HELP_MESSAGE)


@dp.message_handler(commands=['history'])
async def history_command(message: types.Message) -> None:
    user_id: int = message.from_user.id
    cursor.execute('SELECT query FROM searches WHERE user_id=?', (user_id,))
    search_history: tp.List[tp.Tuple[str]] = cursor.fetchall()
    if search_history:
        await message.reply("История поисковых запросов:")
        out_history: str = ""
        for row in search_history:
            out_history += row[0] + '\n'
        if len(out_history) <= 4096:
            await bot.send_message(message.from_user.id, out_history)
        else:
            output_list: tp.List = []
            while len(out_history) > 0:
                temp: str = out_history[:4096]
                if len(out_history) > 4096:
                    ind: int = temp.rfind('\n')
                    temp = temp[:ind + 1]
                    out_history = out_history[ind + 1:]
                else:
                    out_history = out_history[4096:]
                output_list.append(temp)
            for el in output_list:
                await bot.send_message(message.from_user.id, el)

    else:
        await message.reply("История поисковых запросов пуста.")


@dp.message_handler(commands=['stats'])
async def stats_command(message: types.Message) -> None:
    user_id: int = message.from_user.id
    cursor.execute('SELECT movie_name, count FROM movies WHERE user_id=?', (user_id,))
    movie_stats: tp.List[tp.Tuple[str, int]] = cursor.fetchall()
    if movie_stats:
        await message.reply("Статистика предлагаемых фильмов:")
        out_stats: str = ""
        for row in movie_stats:
            out_stats += f"{row[0]} - {row[1]} раз(а)" + '\n'
        if len(out_stats) <= 4096:
            await bot.send_message(message.from_user.id, out_stats)
        else:
            output_list: tp.List = []
            while len(out_stats) > 0:
                temp: str = out_stats[:4096]
                if len(out_stats) > 4096:
                    ind: int = temp.rfind('\n')
                    temp = temp[:ind + 1]
                    out_stats = out_stats[ind + 1:]
                else:
                    out_stats = out_stats[4096:]
                output_list.append(temp)
            for el in output_list:
                await bot.send_message(message.from_user.id, el)
    else:
        await message.reply("Статистика предлагаемых фильмов пуста.")


async def get_movie_poster(movie_title: str) -> tp.Any:
    async with aiohttp.ClientSession() as session:
        async with session.get(
                f"https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword?keyword={movie_title}",
                headers={"X-API-KEY": X_API_KEY}
        ) as search_response:
            if search_response.status == 200:
                search_data: tp.Any = await search_response.json()
                if search_data['films']:
                    film_id: tp.Any = search_data['films'][0]['filmId']

                    async with session.get(
                            f"https://kinopoiskapiunofficial.tech/api/v2.2/films/{film_id}",
                            headers={"X-API-KEY": X_API_KEY}
                    ) as details_response:
                        if details_response.status == 200:
                            details_data: tp.Any = await details_response.json()
                            if 'posterUrl' in details_data:
                                poster_url: tp.Any = details_data['posterUrl']
                                return poster_url

    return None


def get_movie_links(request: str) -> tp.Any:
    try:
        google_request: str = request + ' смотреть онлайн'
        links: tp.List = list(search(query=google_request, tld='co.in', lang='ru', num=50, stop=50, pause=1))
        return links
    except Exception:
        return None


async def search_movie(movie_title: str) -> str:
    output: str = ""
    try:
        my_link: str = ""
        url: str = f"https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword?keyword={movie_title}"
        headers: tp.Dict = {
            "X-API-KEY": X_API_KEY
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                data = await response.json()
        if data["films"]:
            movie: tp.Any = data["films"][0]
            if movie["rating"] == 'null':
                return "Фильм не найден"
            movie_links: str = get_movie_links(movie["nameRu"] + ' ' + movie["year"])
            if movie_links:
                for link in movie_links:
                    if link.startswith("https://kinobar") or link.startswith("https://www.ivi.ru") or \
                            link.startswith("https://jut.su") or link.startswith("https://hd-rezka") or \
                            link.startswith("https://hdrezka") or link.startswith("https://kinogo"):
                        if str(link).find('&') != -1:
                            my_link += link[:link.find('&')] + '\n'
                        else:
                            my_link += link + '\n'
                        break
                if len(my_link) == 0:
                    return "Фильм не найден"
            else:
                return "Фильм не найден"
            title_ru: str = movie["nameRu"]
            rating: str = movie["rating"]
            year: str = movie["year"]
            description: str = movie["description"]
            return output + (f"Название фильма: {title_ru}\n"
                             f"Рейтинг на кинопоиске: {rating}\n"
                             f"Год: {year}\n"
                             f"Описание: {description}\n"
                             f"Ссылка, где можно посмотреть: {my_link}\n")
        else:
            return "Фильм не найден"
    except aiohttp.ClientError:
        return "Фильм не найден"


@dp.message_handler()
async def search_command(message: types.Message) -> tp.Any:
    user_id: int = message.from_user.id
    movie_title: str = message.text
    cursor.execute('INSERT INTO searches (user_id, query) VALUES (?, ?)', (user_id, movie_title))
    conn.commit()
    movie_info: str = await search_movie(movie_title)
    if movie_info != "Фильм не найден":
        name_of_film: str = movie_info[movie_info.find(':') + 2:movie_info.find("\n")]
        cursor.execute('SELECT count FROM movies WHERE user_id=? AND movie_name=?', (user_id, name_of_film))
        movie_count = cursor.fetchone()
        if movie_count:
            new_count: int = movie_count[0] + 1
            cursor.execute('UPDATE movies SET count=? WHERE user_id=? AND movie_name=?',
                           (new_count, user_id, name_of_film))
        else:
            cursor.execute('INSERT INTO movies (user_id, movie_name, count) VALUES (?, ?, 1)', (user_id, name_of_film))
        conn.commit()

    if movie_info == "Фильм не найден":
        await message.reply(movie_info)
        return None
    async with aiohttp.ClientSession() as session:
        photo_url: str = await get_movie_poster(movie_title)
        response = await fetch(session, photo_url)
    image = Image.open(BytesIO(response))
    temp_file: str = "temp_photo.jpg"
    image.save(temp_file)
    photo = open(temp_file, "rb")
    if photo_url == "https://kinopoiskapiunofficial.tech/images/posters/kp/4675443.jpg":
        return None
    entities: tp.List[str] = []
    ind_link: int = movie_info.rfind("Ссылка, где можно посмотреть")
    if len(movie_info) <= 1024:
        entities.append(movie_info)
    else:
        size_link: int = len(movie_info) - ind_link
        link: str = movie_info[ind_link:len(movie_info)]
        movie_info: str = movie_info[:ind_link]
        chunk: str = movie_info[:1023]
        ind: int = chunk.rfind(".")
        while len(movie_info) > 0:
            if ind and len(movie_info) >= 1024:
                chunk = chunk[:ind + 1]
                movie_info = movie_info[ind + 1:]
            else:
                chunk = chunk[:1024]
                movie_info = movie_info[1024:]
            entities.append(chunk)
        if len(entities[len(entities) - 1]) + size_link < 1024:
            entities[len(entities) - 1] += link
        else:
            entities.append(link)
    for i in range(len(entities)):
        if i == 0:
            await bot.send_photo(message.from_user.id, photo=photo,
                                 caption=entities[0], reply_to_message_id=message.message_id)
        else:
            await bot.send_message(message.from_user.id, entities[i])


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
