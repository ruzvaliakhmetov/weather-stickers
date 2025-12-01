import os
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot, InputSticker
from telegram.error import BadRequest


IMAGES_DIR = Path(__file__).parent / "images"


@dataclass
class CityConfig:
    name: str      # как написать город на стикере
    query: str     # как отдать город в API
    emoji: str     # эмодзи для стикера
    output: str    # куда сохранить png


CITIES = [
    CityConfig(
        name="Tula",
        query="Tula,RU",
        emoji="🏙️",
        output="sticker_tula.png",
    ),
    CityConfig(
        name="Malmö",
        query="Malmo,SE",  # в API без умлаута
        emoji="🏙️",
        output="sticker_malmo.png",
    ),
    CityConfig(
        name="Belgrade",
        query="Belgrade,RS",
        emoji="🏙️",
        output="sticker_belgrade.png",
    ),
]


def get_font(size: int) -> ImageFont.FreeTypeFont:
    font_paths = [
        "font.ttf",
        "Font.ttf",
        "fonts/font.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


@dataclass
class WeatherInfo:
    temp: float
    humidity: int
    wind_speed: float
    description: str
    condition_main: str  # Clear, Clouds, Rain и т.п.


def fetch_weather(city: CityConfig) -> WeatherInfo:
    api_key = os.environ["WEATHER_API_KEY"]
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city.query,
        "appid": api_key,
        "units": "metric",
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    main = data["main"]
    wind = data.get("wind", {})
    weather0 = data["weather"][0]

    return WeatherInfo(
        temp=main["temp"],
        humidity=main["humidity"],
        wind_speed=wind.get("speed", 0.0),
        description=weather0.get("description", "").capitalize(),
        condition_main=weather0.get("main", "Default"),
    )


BACKGROUND_MAP = {
    "Clear": "weather_clear.png",
    "Clouds": "weather_clouds.png",
    "Rain": "weather_rain.png",
    "Drizzle": "weather_rain.png",
    "Thunderstorm": "weather_rain.png",
    "Snow": "weather_snow.png",
}


def get_background_path(condition_main: str) -> Path:
    filename = BACKGROUND_MAP.get(condition_main, "weather_default.png")
    path = IMAGES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Background image not found: {path}. "
            f"Put weather_*.png files into {IMAGES_DIR}"
        )
    return path


def generate_weather_image(city: CityConfig, weather: WeatherInfo, output_path: str) -> None:
    base_path = get_background_path(weather.condition_main)
    img = Image.open(base_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # ---------- BIG TEMPERATURE ----------
    temp_text = f"{round(weather.temp)} °C"
    temp_font = get_font(140)
    tb = draw.textbbox((0, 0), temp_text, font=temp_font)
    temp_w = tb[2] - tb[0]
    temp_h = tb[3] - tb[1]
    temp_x = (img.width - temp_w) // 2
    temp_y = 70
    draw.text((temp_x, temp_y), temp_text, font=temp_font, fill=(255, 255, 255, 255))

    # ---------- DETAILS (humidity, wind, description) ----------
    small_font = get_font(28)
    lines = [
        f"Humidity: {weather.humidity}%",
        f"Wind: {weather.wind_speed:.1f} m/s",
        weather.description,
    ]
    line_spacing = 6
    start_x = 40
    start_y = img.height // 2

    y = start_y
    for line in lines:
        lb = draw.textbbox((0, 0), line, font=small_font)
        h = lb[3] - lb[1]
        draw.text((start_x, y), line, font=small_font, fill=(220, 220, 220, 255))
        y += h + line_spacing

    # ---------- CITY NAME ----------
    city_font = get_font(80)
    cb = draw.textbbox((0, 0), city.name, font=city_font)
    city_w = cb[2] - cb[0]
    city_h = cb[3] - cb[1]
    city_x = (img.width - city_w) // 2
    city_y = img.height - city_h - 40
    draw.text((city_x, city_y), city.name, font=city_font, fill=(255, 255, 255, 255))

    img.save(output_path, format="PNG")


async def update_stickers() -> None:
    token = os.environ["BOT_TOKEN"]
    set_name = os.environ["STICKER_SET_NAME"]
    set_title = os.environ["STICKER_SET_TITLE"]
    owner_user_id = int(os.environ["TELEGRAM_USER_ID"])

    bot = Bot(token)

    # 1) Готовим картинки и загружаем их как файлы стикеров
    new_stickers: list[InputSticker] = []

    for city in CITIES:
        weather = fetch_weather(city)
        generate_weather_image(city, weather, city.output)

        with open(city.output, "rb") as f:
            uploaded = await bot.upload_sticker_file(
                user_id=owner_user_id,
                sticker=f,
                sticker_format="static",
            )

        new_stickers.append(
            InputSticker(
                sticker=uploaded.file_id,
                emoji_list=[city.emoji],
                format="static",
            )
        )

    # 2) Пробуем получить набор
    try:
        sticker_set = await bot.get_sticker_set(set_name)
    except BadRequest as e:
        msg = getattr(e, "message", str(e)).lower()
        print("get_sticker_set error:", msg)
        if "stickerset_invalid" in msg or "stickerset not found" in msg:
            # набора нет — создаём с двумя стикерами сразу
            await bot.create_new_sticker_set(
                user_id=owner_user_id,
                name=set_name,
                title=set_title,
                stickers=new_stickers,
                sticker_type="regular",
            )
            print(f"Created new sticker set {set_name} with weather stickers")
            return
        else:
            raise

    # 3) Набор существует — удаляем все старые стикеры
    for s in sticker_set.stickers:
        try:
            await bot.delete_sticker_from_set(s.file_id)
            print(f"Deleted old sticker {s.file_id}")
        except BadRequest as e:
            print("delete_sticker_from_set error:", getattr(e, "message", str(e)))

    # 4) Добавляем наши два новых стикера
    for st in new_stickers:
        await bot.add_sticker_to_set(
            user_id=owner_user_id,
            name=set_name,
            sticker=st,
        )
    print(f"Updated sticker set {set_name} with weather for Tula and Malmö")


if __name__ == "__main__":
    import asyncio

    asyncio.run(update_stickers())
