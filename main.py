import disnake
from disnake.ext import commands, tasks
import aiosqlite
import random, os
import time
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')

if TOKEN is None:
    print("Ошибка: Токен DISCORD_TOKEN не найден в переменных окружения.")
    exit(1)

bot = commands.Bot(command_prefix="!", intents=disnake.Intents.all())

# ============================================================
# ----------------------  НАСТРОЙКИ  -------------------------
# ============================================================

MAP_TEMPLATE = """
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛
⬛⬜⬜⬜⬜⬜⬜⬛⬜⬜⬛⬜⬜⬛
⬛⬜⬜⬜⬜⬜⬜⬛⬜⬜⬛⬜⬜⬛
⬛⬛⬛⬛⬛⬛⬛⬛⬜⬜⬛⬜⬜⬛
⬛⬜⬜⬜⬜⬜⬜⬛⬜⬜⬛⬜⬜⬛
⬛⬜🟪🟪🟪🟪⬜⬛⬜⬜⬛⬜⬜⬛
⬛⬜⬜⬜⬜⬜⬜⬛⬜⬜⬛⬜⬜⬛
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛
"""

# Здания: цена / производство / требуемые ресурсы / эмодзи
BUILDINGS = {
    "Жилая многоэтажка": {
        "cost": {"дерево": 20, "камень": 15},
        "prod": {"жители": 5},
        "need": {"еда": 1},
        "emoji": "🏢"
    },
    "Ферма еды": {
        "cost": {"дерево": 10},
        "prod": {"еда": 5},
        "need": {},
        "emoji": "🌾"
    },
    "Цементный завод": {
        "cost": {"камень": 20},
        "prod": {"цемент": 3},
        "need": {"жители": 3},
        "emoji": "🏭"
    },
    "Лесопилка": {
        "cost": {"камень": 5},
        "prod": {"дерево": 5},
        "need": {"жители": 2},
        "emoji": "🪓"
    },
    "Песчаный карьер": {
        "cost": {"дерево": 10},
        "prod": {"песок": 4},
        "need": {"жители": 2},
        "emoji": "⛏️"
    }
}

# ============================================================
# ----------------------  БАЗА ДАННЫХ  -----------------------
# ============================================================

async def init_db():
    async with aiosqlite.connect("city.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            дерево INTEGER,
            камень INTEGER,
            еда INTEGER,
            жители INTEGER,
            цемент INTEGER,
            песок INTEGER,
            довольство INTEGER
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS buildings(
            user_id INTEGER,
            name TEXT
        )
        """)
        await db.commit()

async def ensure_user(user_id):
    async with aiosqlite.connect("city.db") as db:
        cur = await db.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        data = await cur.fetchone()
        if data is None:
            await db.execute("""
            INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, 100, 100, 20, 5, 0, 0, 100))
            await db.commit()

# ============================================================
# ----------------------  КАРТА  -----------------------------
# ============================================================

def map_to_matrix(template):
    return [list(row) for row in template.strip().split("\n")]

def matrix_to_map(matrix):
    return "\n".join("".join(row) for row in matrix)

def get_embed_map(user_id, res, buildings):
    matrix = map_to_matrix(MAP_TEMPLATE)

    # Свободные позиции (⬜)
    free_positions = [(y, x) for y, row in enumerate(matrix) 
                               for x, cell in enumerate(row) if cell == "⬜"]

    for building in buildings:
        if free_positions:
            y, x = random.choice(free_positions)
            matrix[y][x] = BUILDINGS[building]["emoji"]
            free_positions.remove((y, x))

    new_map = matrix_to_map(matrix)

    embed = disnake.Embed(
        title=f"🏙 Карта вашей страны — {user_id}",
        color=disnake.Color.gold(),
        description=new_map
    )

    res_text = "\n".join([f"**{k}:** {v}" for k, v in res.items()])
    embed.add_field(name="📦 Ресурсы", value=res_text, inline=False)
    embed.add_field(name="👥 Жители", value=str(res.get("жители", 0)), inline=True)
    embed.add_field(name="😃 Довольство", value=f"{res.get('довольство',100)}%", inline=True)

    if buildings:
        embed.add_field(
            name="🏗 Постройки",
            value="\n".join([f"• {b}" for b in buildings]),
            inline=False
        )
    else:
        embed.add_field(name="🏗 Постройки", value="Пока нет построек", inline=False)

    return embed

# ============================================================
# ----------------------  СБОР РЕСУРСОВ  ---------------------
# ============================================================

last_collect_time = {}

@bot.command()
async def сбор(ctx):
    user_id = ctx.author.id
    await ensure_user(user_id)

    now = time.time()
    last = last_collect_time.get(user_id, 0)

    if now - last < 60:
        await ctx.send(f"⏳ Подождите {int(60 - (now - last))} секунд до следующего сбора.")
        return

    last_collect_time[user_id] = now

    async with aiosqlite.connect("city.db") as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        res = {
            "дерево": row[1],
            "камень": row[2],
            "еда": row[3],
            "жители": row[4],
            "цемент": row[5],
            "песок": row[6],
            "довольство": row[7]
        }

        cur2 = await db.execute("SELECT name FROM buildings WHERE user_id=?", (user_id,))
        buildings = [b[0] for b in await cur2.fetchall()]

        events_text = ""

        for b in buildings:
            bd = BUILDINGS[b]

            # Проверяем доступность производства
            can_work = True
            for need_r, need_c in bd["need"].items():
                if res[need_r] < need_c:
                    can_work = False
            if not can_work:
                continue

            # списываем необходимые ресурсы
            for need_r, need_c in bd["need"].items():
                res[need_r] -= need_c

            # случайные события
            event_chance = random.randint(1,100)
            multiplier = 1
            if event_chance <= 10:
                multiplier = 0
                events_text += f"⚠️ {b} пострадало от несчастного случая, производство не получилось!\n"
            elif event_chance <= 20:
                multiplier = 2
                events_text += f"🎉 {b} произвело вдвое больше ресурсов!\n"

            # добавляем продукцию
            for prod_r, prod_c in bd["prod"].items():
                res[prod_r] += int(prod_c * multiplier)

        # Довольство зависит от еды и жителей
        if res["еда"] < res["жители"]:
            res["довольство"] -= 10
            events_text += "😡 Жителей больше, чем еды! Довольство упало на 10%.\n"
        else:
            res["довольство"] = min(100, res["довольство"] + 5)  # небольшое восстановление

        await db.execute("""
        UPDATE users SET дерево=?, камень=?, еда=?, жители=?, цемент=?, песок=?, довольство=? WHERE user_id=?
        """, (res["дерево"], res["камень"], res["еда"], res["жители"], res["цемент"], res["песок"], res["довольство"], user_id))
        await db.commit()

    message = f"✅ Вы собрали ресурсы!\n"
    message += "\n".join([f"**{k}:** {v}" for k, v in res.items() if k not in ["жители","довольство"]])
    message += f"\n👥 Жители: {res['жители']}\n😃 Довольство: {res['довольство']}%"
    if events_text:
        message += f"\n\nСобытия:\n{events_text}"

    await ctx.send(message)

# ============================================================
# ----------------------  КОМАНДЫ КАРТЫ ----------------------
# ============================================================

@bot.command()
async def карта(ctx):
    user_id = ctx.author.id
    await ensure_user(user_id)

    async with aiosqlite.connect("city.db") as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()

        res = {
            "дерево": row[1],
            "камень": row[2],
            "еда": row[3],
            "жители": row[4],
            "цемент": row[5],
            "песок": row[6],
            "довольство": row[7]
        }

        cur2 = await db.execute("SELECT name FROM buildings WHERE user_id=?", (user_id,))
        buildings = [b[0] for b in await cur2.fetchall()]

    embed = get_embed_map(user_id, res, buildings)
    view = MapButtons(user_id)
    await ctx.send(embed=embed, view=view)

class MapButtons(disnake.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @disnake.ui.button(label="🏗 Построить", style=disnake.ButtonStyle.green)
    async def build(self, button, inter):
        if inter.author.id != self.user_id:
            return await inter.response.send_message("Не твоя карта.", ephemeral=True)

        view = BuildMenu(self.user_id)
        embed = disnake.Embed(
            title="Выберите что строить",
            description="\n".join([f"**{name}**" for name in BUILDINGS.keys()])
        )
        await inter.response.edit_message(embed=embed, view=view)

    @disnake.ui.button(label="ℹ Инфо о зданиях", style=disnake.ButtonStyle.blurple)
    async def info(self, button, inter):
        text = ""
        for name, d in BUILDINGS.items():
            cost = ", ".join([f"{k}:{v}" for k, v in d["cost"].items()])
            prod = ", ".join([f"{k}:{v}" for k, v in d["prod"].items()])
            need = ", ".join([f"{k}:{v}" for k, v in d["need"].items()]) or "нет"
            text += f"**{name}**\nЦена: {cost}\nПроизводит: {prod}\nТребует: {need}\nЭмодзи: {d['emoji']}\n\n"

        embed = disnake.Embed(title="ℹ Информация о зданиях", description=text)
        await inter.response.send_message(embed=embed, ephemeral=True)

class BuildMenu(disnake.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        for name in BUILDINGS.keys():
            self.add_item(BuildButton(name, user_id))

class BuildButton(disnake.ui.Button):
    def __init__(self, building_name, user_id):
        super().__init__(label=building_name, style=disnake.ButtonStyle.green)
        self.building_name = building_name
        self.user_id = user_id

    async def callback(self, inter):
        if inter.author.id != self.user_id:
            return await inter.response.send_message("Не твоя страна.", ephemeral=True)

        async with aiosqlite.connect("city.db") as db:
            cur = await db.execute("SELECT * FROM users WHERE user_id=?", (self.user_id,))
            row = await cur.fetchone()

            res = {
                "дерево": row[1],
                "камень": row[2],
                "еда": row[3],
                "жители": row[4],
                "цемент": row[5],
                "песок": row[6],
                "довольство": row[7]
            }

            cost = BUILDINGS[self.building_name]["cost"]

            for r, c in cost.items():
                if res[r] < c:
                    return await inter.response.send_message(f"Не хватает ресурса **{r}**!", ephemeral=True)

            for r, c in cost.items():
                res[r] -= c

            await db.execute("INSERT INTO buildings VALUES (?, ?)", (self.user_id, self.building_name))
            await db.execute("""
            UPDATE users SET дерево=?, камень=?, еда=?, жители=?, цемент=?, песок=? WHERE user_id=?
            """, (res["дерево"], res["камень"], res["еда"], res["жители"], res["цемент"], res["песок"], self.user_id))
            await db.commit()

        await show_map(inter, self.user_id)

async def show_map(inter, user_id):
    async with aiosqlite.connect("city.db") as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        res = {
            "дерево": row[1],
            "камень": row[2],
            "еда": row[3],
            "жители": row[4],
            "цемент": row[5],
            "песок": row[6],
            "довольство": row[7]
        }
        cur2 = await db.execute("SELECT name FROM buildings WHERE user_id=?", (user_id,))
        buildings = [b[0] for b in await cur2.fetchall()]

    embed = get_embed_map(user_id, res, buildings)
    await inter.response.edit_message(embed=embed, view=MapButtons(user_id))

# ============================================================

@bot.event
async def on_ready():
    await init_db()
    print(f"Бот запущен как {bot.user}")
    bot.run(TOKEN)

