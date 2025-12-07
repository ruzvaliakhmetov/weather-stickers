import os
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot, InputSticker
from telegram.error import BadRequest


IMAGES_DIR = Path(__file__).parent / "images"
ICONS_DIR = IMAGES_DIR / "icons"  # сюда складываем иконки openweather: 01d.png, 01n.png и т.п.


# ==========================
#   НАСТРОЙКИ МАКЕТА
# ==========================

@dataclass
class BlockLayout:
    # Если x или y = None, используется «умное» значение по умолчанию (например, центрирование).
    x: int | None
    y: int | None
    font_size: int


@dataclass
class DetailsLayout:
    x: int
    y: int
    font_size: int
    line_spacing: int = 6


# Позиции блоков (можешь править как угодно):

# Город
CITY_LAYOUT = BlockLayout(
    x=50,   # None = центр по горизонтали
    y=100,   # None = автоматически чуть выше низа
    font_size=60,
)

# Температура (число)
TEMP_LAYOUT = BlockLayout(
    x=200,   # None = центр по горизонтали
    y=70,
    font_size=140,
)

# Блок "°C"
DEGREE_LAYOUT = BlockLayout(
    x=None,   # None = автоматически справа от числа
    y=None,   # None = автоматически выравнивание по нижней части числа
    font_size=70,
)

# День (например "07")
DAY_LAYOUT = BlockLayout(
    x=400,
    y=400,
    font_size=80,
)

# Месяц (например "Dec")
MONTH_LAYOUT = BlockLayout(
    x=40,
    y=DAY_LAYOUT.y + 50,
    font_size=40,
)

# Время (например "20:55")
TIME_LAYOUT = BlockLayout(
    x=40,
    y=MONTH_LAYOUT.y + 50,
    font_size=40,
)

# Блок деталей (humidity, wind, conditions) — три строки
DETAILS_LAYOUT = DetailsLayout(
    x=40,
    y=350,       # стартовая Y для первой строки
    font_size=28,
    line_spacing=6,
)

# Позиция иконки погоды (из локальных PNG 225x225)
ICON_X = 0
ICON_Y = 0
ICON_SIZE = (225, 225)


# ==========================
#   КОНФИГ ГОРОДОВ
# ==========================

@dataclass
class CityConfig:
    name: str      # как написать город на стикере
    query: str     # как отдать город в API
    emoji: str     # эмодзи для стикера
    output: str    # куда сохранить png
    background: str  # фон города (PNG), путь относительно IMAGES_DIR


CITIES = [
#    CityConfig(
#        name="Tula",
#        query="Tula,RU",
#        emoji="🏙️",
#        output="sticker_tula.png",
#        background="bg_tula.png",
#    ),
#    CityConfig(
#        name="Malmö",
#        query="Malmo,SE",  # в API без умлаута
#        emoji="🏙️",
#        output="sticker_malmo.png",
#        background="bg_malmo.png",
#    ),
#    CityConfig(
#        name="Belgrade",
#        query="Belgrade,RS",
#        emoji="🏙️",
#        output="sticker_belgrade.png",
#        background="bg_belgrade.png",
#    ),
    CityConfig(
        name="Moscow",
        query="Moscow,RU",
        emoji="🏙️",
        output="sticker_moscow.png",
        background="bg_moscow.png",
    ),
 #   CityConfig(
 #       name="Petersburg",
 #       query="Saint Petersburg,RU",
 #       emoji="🏙️",
 #       output="sticker_saintpetersburg.png",
 #       background="bg_petersburg.png",
 #   ),
 #   CityConfig(
 #       name="Haifa",
 #       query="Haifa,IL",
 #       emoji="🏙️",
 #       output="sticker_haifa.png",
 #       background="bg_haifa.png",
 #   ),
 #   CityConfig(
 #       name="Karmiel",
 #       query="Karmiel,IL",
 #       emoji="🏙️",
 #       output="sticker_karmiel.png",
 #       background="bg_karmiel.png",
 #   ),
 #   CityConfig(
 #       name="Ufa",
 #       query="Ufa,RU",
 #       emoji="🏙️",
 #       output="sticker_ufa.png",
 #       background="bg_ufa.png",
 #   ),
 #   CityConfig(
 #       name="Hamburg",
 #       query="Hamburg,DE",
 #       emoji="🏙️",
 #       output="sticker_hamburg.png",
 #       background="bg_hamburg.png",
 #   ),
]


# ==========================
#   ШРИФТ
# ==========================

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


# ==========================
#   ПОГОДА
# ==========================

@dataclass
class WeatherInfo:
    temp: float
    humidity: int
    wind_speed: float
    description: str
    condition_main: str  # Clear, Clouds, Rain и т.п.
    icon_code: str       # код иконки, например "01d"


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
        icon_code=weather0.get("icon", ""),  # например: "01d"
    )


# ==========================
#   ГЕНЕРАЦИЯ КАРТИНКИ
# ==========================

def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    text: str,
    layout: BlockLayout,
    *,
    default_x: int | None = None,
    default_y: int | None = None,
    fill=(255, 255, 255, 255),
) -> tuple[int, int, int, int]:
    """
    Рисует текст по правилам:
    - если layout.x указан, используем его;
    - иначе, если default_x указан — используем его;
    - иначе центрируем по горизонтали.
    Аналогично для y.
    Возвращает bbox (x, y, w, h).
    """
    font = get_font(layout.font_size)
    tb = draw.textbbox((0, 0), text, font=font)
    text_w = tb[2] - tb[0]
    text_h = tb[3] - tb[1]

    # X
    if layout.x is not None:
        x = layout.x
    elif default_x is not None:
        x = default_x
    else:
        x = (img.width - text_w) // 2

    # Y
    if layout.y is not None:
        y = layout.y
    elif default_y is not None:
        y = default_y
    else:
        # по умолчанию для тех блоков, где y не задан — внизу
        y = img.height - text_h - 40

    draw.text((x, y), text, font=font, fill=fill)
    return x, y, text_w, text_h


def _draw_details_block(draw: ImageDraw.ImageDraw, img: Image.Image, weather: WeatherInfo) -> None:
    font = get_font(DETAILS_LAYOUT.font_size)
    lines = [
        f"Humidity: {weather.humidity}%",
        f"Wind: {weather.wind_speed:.1f} m/s",
        weather.description,
    ]

    x = DETAILS_LAYOUT.x
    y = DETAILS_LAYOUT.y

    for line in lines:
        lb = draw.textbbox((0, 0), line, font=font)
        h = lb[3] - lb[1]
        draw.text((x, y), line, font=font, fill=(220, 220, 220, 255))
        y += h + DETAILS_LAYOUT.line_spacing


def _paste_icon(img: Image.Image, icon_code: str) -> None:
    if not icon_code:
        return

    icon_path = ICONS_DIR / f"{icon_code}.png"
    if not icon_path.exists():
        print(f"[warn] icon not found: {icon_path}")
        return

    icon = Image.open(icon_path).convert("RGBA")
    if icon.size != ICON_SIZE:
        icon = icon.resize(ICON_SIZE, Image.LANCZOS)

    # Вклеиваем иконку в левый верхний угол
    img.alpha_composite(icon, (ICON_X, ICON_Y))


def generate_weather_image(
    city: CityConfig,
    weather: WeatherInfo,
    output_path: str,
    day_text: str,
    month_text: str,
    time_text: str,
) -> None:
    # --- фон города ---
    bg_path = IMAGES_DIR / city.background
    if not bg_path.exists():
        raise FileNotFoundError(
            f"Background image not found: {bg_path}. "
            f"Put city backgrounds (e.g. {city.background}) into {IMAGES_DIR}"
        )

    img = Image.open(bg_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # --- иконка погоды ---
    _paste_icon(img, weather.icon_code)

    # --- большая температура (число) ---
    temp_value = f"{round(weather.temp):d}"  # только число, без °C
    temp_x, temp_y, temp_w, temp_h = _draw_text_block(
        draw,
        img,
        temp_value,
        TEMP_LAYOUT,
        default_y=70,
    )

    # --- блок °C ---
    degree_text = "°C"
    degree_font = get_font(DEGREE_LAYOUT.font_size)
    db = draw.textbbox((0, 0), degree_text, font=degree_font)
    deg_w = db[2] - db[0]
    deg_h = db[3] - db[1]

    if DEGREE_LAYOUT.x is not None:
        deg_x = DEGREE_LAYOUT.x
    else:
        deg_x = temp_x + temp_w + 10  # по умолчанию — справа от числа

    if DEGREE_LAYOUT.y is not None:
        deg_y = DEGREE_LAYOUT.y
    else:
        deg_y = temp_y + temp_h - deg_h  # выравнивание по нижней части числа

    draw.text((deg_x, deg_y), degree_text, font=degree_font, fill=(255, 255, 255, 255))

    # --- город ---
    _ = _draw_text_block(
        draw,
        img,
        city.name,
        CITY_LAYOUT,
        # default_y не задаём — по умолчанию город внизу
    )

    # --- дата/время обновления ---
    _draw_text_block(draw, img, day_text, DAY_LAYOUT)
    _draw_text_block(draw, img, month_text, MONTH_LAYOUT)
    _draw_text_block(draw, img, time_text, TIME_LAYOUT)

    # --- детали (3 строки) ---
    _draw_details_block(draw, img, weather)

    img.save(output_path, format="PNG")


# ==========================
#   ОБНОВЛЕНИЕ СТИКЕРОВ
# ==========================

async def update_stickers() -> None:
    token = os.environ["BOT_TOKEN"]
    set_name = os.environ["STICKER_SET_NAME"]
    set_title = os.environ["STICKER_SET_TITLE"]
    owner_user_id = int(os.environ["TELEGRAM_USER_ID"])

    bot = Bot(token)

    # timestamp для всех стикеров одинаковый
    now = datetime.now()
    day_text = now.strftime("%d")   # "07"
    month_text = now.strftime("%b") # "Dec"
    time_text = now.strftime("%H:%M")  # "20:55"

    new_stickers: list[InputSticker] = []

    for city in CITIES:
        weather = fetch_weather(city)
        generate_weather_image(city, weather, city.output, day_text, month_text, time_text)

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
            # набора нет — создаём новый сразу со всеми городами
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

    # 3) Набор существует — делаем replace там, где можем
    old_stickers = sticker_set.stickers
    old_count = len(old_stickers)
    new_count = len(new_stickers)
    common = min(old_count, new_count)

    # 3a) replace для общих позиций
    for i in range(common):
        old_id = old_stickers[i].file_id
        new_st = new_stickers[i]
        try:
            await bot.replace_sticker_in_set(
                user_id=owner_user_id,
                name=set_name,
                old_sticker=old_id,
                sticker=new_st,
            )
            print(f"Replaced sticker {old_id} with new one at position {i}")
        except BadRequest as e:
            print("replace_sticker_in_set error:", getattr(e, "message", str(e)))

    # 3б) если новых больше — добавляем хвост
    if new_count > old_count:
        for i in range(common, new_count):
            st = new_stickers[i]
            try:
                await bot.add_sticker_to_set(
                    user_id=owner_user_id,
                    name=set_name,
                    sticker=st,
                )
            except BadRequest as e:
                print("add_sticker_to_set error:", getattr(e, "message", str(e)))

    # 3в) если старых больше — удаляем лишние в конце
    elif old_count > new_count:
        for i in range(common, old_count):
            old_id = old_stickers[i].file_id
            try:
                await bot.delete_sticker_from_set(old_id)
            except BadRequest as e:
                print("delete_sticker_from_set error:", getattr(e, "message", str(e)))

    print(f"Updated sticker set {set_name} with weather for {new_count} cities")


if __name__ == "__main__":
    import asyncio

    asyncio.run(update_stickers())
