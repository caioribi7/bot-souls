import aiosqlite
from datetime import datetime

DB_PATH = "community_bot.db"


class Database:
    def __init__(self):
        self.path = DB_PATH

    async def initialize(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id    INTEGER,
                    guild_id   INTEGER,
                    xp         INTEGER DEFAULT 0,
                    level      INTEGER DEFAULT 0,
                    messages   INTEGER DEFAULT 0,
                    balance    INTEGER DEFAULT 0,
                    last_xp_ts REAL    DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                );

                CREATE TABLE IF NOT EXISTS profiles (
                    user_id          INTEGER PRIMARY KEY,
                    bio              TEXT    DEFAULT '',
                    banner_url       TEXT    DEFAULT '',
                    icon_url         TEXT    DEFAULT '',
                    color            TEXT    DEFAULT '#5865F2',
                    background_color TEXT    DEFAULT '#2C2F33',
                    theme            TEXT    DEFAULT 'escuro'
                );

                CREATE TABLE IF NOT EXISTS shop_items (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id      INTEGER,
                    role_id       INTEGER,
                    name          TEXT,
                    price         INTEGER,
                    description   TEXT    DEFAULT '',
                    emoji         TEXT    DEFAULT '🎭',
                    is_custom     INTEGER DEFAULT 0,
                    xp_multiplier REAL    DEFAULT 1.0
                );

                CREATE TABLE IF NOT EXISTS user_purchases (
                    user_id      INTEGER,
                    guild_id     INTEGER,
                    item_id      INTEGER,
                    purchased_at TEXT,
                    PRIMARY KEY (user_id, guild_id, item_id)
                );

                CREATE TABLE IF NOT EXISTS giveaways (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id   INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    prize      TEXT,
                    winners    INTEGER DEFAULT 1,
                    host_id    INTEGER,
                    ends_at    TEXT,
                    ended      INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    giveaway_id INTEGER,
                    user_id     INTEGER,
                    PRIMARY KEY (giveaway_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS anonymous_config (
                    guild_id          INTEGER PRIMARY KEY,
                    channel_id        INTEGER,
                    menu_channel_id   INTEGER DEFAULT 0,
                    log_channel_id    INTEGER DEFAULT 0,
                    enabled           INTEGER DEFAULT 1,
                    button_message_id INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS level_roles (
                    guild_id INTEGER,
                    level    INTEGER,
                    role_id  INTEGER,
                    PRIMARY KEY (guild_id, level)
                );

                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id           INTEGER PRIMARY KEY,
                    level_channel_id   INTEGER DEFAULT 0,
                    xp_min             INTEGER DEFAULT 15,
                    xp_max             INTEGER DEFAULT 25,
                    xp_cooldown        INTEGER DEFAULT 60,
                    coins_per_msg      INTEGER DEFAULT 5,
                    level_up_msg       TEXT    DEFAULT '🎉 {user} subiu para o nível **{level}**!',
                    welcome_channel_id INTEGER DEFAULT 0,
                    welcome_message    TEXT    DEFAULT 'Bem-vindo(a) {user} ao servidor!',
                    welcome_image_url  TEXT    DEFAULT '',
                    shop_channel_id    INTEGER DEFAULT 0,
                    shop_message_id    INTEGER DEFAULT 0,
                    level_coins_base   INTEGER DEFAULT 100,
                    pix_key            TEXT    DEFAULT '',
                    pix_price_100      INTEGER DEFAULT 500,
                    pix_price_500      INTEGER DEFAULT 2000,
                    pix_price_1000     INTEGER DEFAULT 3500
                );

                CREATE TABLE IF NOT EXISTS warns (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id     INTEGER,
                    user_id      INTEGER,
                    moderator_id INTEGER,
                    reason       TEXT,
                    created_at   TEXT
                );

                CREATE TABLE IF NOT EXISTS daily_claims (
                    user_id    INTEGER PRIMARY KEY,
                    last_claim TEXT
                );

                CREATE TABLE IF NOT EXISTS marriages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id        INTEGER,
                    user1_id        INTEGER,
                    user2_id        INTEGER,
                    godparent1_id   INTEGER DEFAULT 0,
                    godparent2_id   INTEGER DEFAULT 0,
                    married_at      TEXT,
                    shared_balance  INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS clans (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id         INTEGER,
                    name             TEXT,
                    owner_id         INTEGER,
                    role_id          INTEGER DEFAULT 0,
                    text_channel_id  INTEGER DEFAULT 0,
                    voice_channel_id INTEGER DEFAULT 0,
                    color_hex        TEXT    DEFAULT '#5865F2',
                    description      TEXT    DEFAULT '',
                    created_at       TEXT
                );

                CREATE TABLE IF NOT EXISTS clan_members (
                    clan_id     INTEGER,
                    user_id     INTEGER,
                    joined_at   TEXT,
                    member_role TEXT    DEFAULT 'member',
                    PRIMARY KEY (clan_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS clan_invites (
                    clan_id    INTEGER,
                    user_id    INTEGER,
                    invited_at TEXT,
                    PRIMARY KEY (clan_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS open_tickets (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id   INTEGER,
                    user_id    INTEGER,
                    channel_id INTEGER,
                    status     TEXT    DEFAULT 'open',
                    created_at TEXT,
                    closed_at  TEXT    DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS tickets_config (
                    guild_id         INTEGER PRIMARY KEY,
                    category_id      INTEGER DEFAULT 0,
                    channel_id       INTEGER DEFAULT 0,
                    log_channel_id   INTEGER DEFAULT 0,
                    panel_message_id INTEGER DEFAULT 0,
                    enabled          INTEGER DEFAULT 1,
                    panel_title      TEXT    DEFAULT '📬 Suporte',
                    panel_description TEXT   DEFAULT 'Clique no botão abaixo para abrir um ticket privado com a equipe.',
                    ticket_title     TEXT    DEFAULT '🎫 Ticket de {user}',
                    ticket_description TEXT  DEFAULT 'Olá, {user}! Descreva sua dúvida e a equipe irá ajudar.',
                    close_message    TEXT    DEFAULT '🔒 Ticket fechado por {closer}. Este canal será deletado em 5 segundos.'
                );

                CREATE TABLE IF NOT EXISTS role_listings (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id  INTEGER,
                    seller_id INTEGER,
                    role_id   INTEGER,
                    price     INTEGER,
                    listed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS xp_boost_roles (
                    guild_id   INTEGER,
                    role_id    INTEGER,
                    multiplier REAL    DEFAULT 1.5,
                    PRIMARY KEY (guild_id, role_id)
                );

                CREATE TABLE IF NOT EXISTS shop_config (
                    guild_id          INTEGER PRIMARY KEY,
                    custom_role_price INTEGER DEFAULT 5000,
                    channel_id        INTEGER DEFAULT 0,
                    message_id        INTEGER DEFAULT 0,
                    market_message_id INTEGER DEFAULT 0
                );
            """)
            await db.commit()

            migrations = [
                "ALTER TABLE profiles ADD COLUMN theme TEXT DEFAULT 'escuro'",
                "ALTER TABLE shop_items ADD COLUMN is_custom INTEGER DEFAULT 0",
                "ALTER TABLE shop_items ADD COLUMN xp_multiplier REAL DEFAULT 1.0",
                "ALTER TABLE anonymous_config ADD COLUMN button_message_id INTEGER DEFAULT 0",
                "ALTER TABLE anonymous_config ADD COLUMN menu_channel_id INTEGER DEFAULT 0",
                "ALTER TABLE guild_config ADD COLUMN welcome_channel_id INTEGER DEFAULT 0",
                "ALTER TABLE guild_config ADD COLUMN welcome_message TEXT DEFAULT 'Bem-vindo(a) {user} ao servidor!'",
                "ALTER TABLE guild_config ADD COLUMN welcome_image_url TEXT DEFAULT ''",
                "ALTER TABLE guild_config ADD COLUMN shop_channel_id INTEGER DEFAULT 0",
                "ALTER TABLE guild_config ADD COLUMN shop_message_id INTEGER DEFAULT 0",
                "ALTER TABLE guild_config ADD COLUMN level_coins_base INTEGER DEFAULT 100",
                "ALTER TABLE guild_config ADD COLUMN pix_key TEXT DEFAULT ''",
                "ALTER TABLE guild_config ADD COLUMN pix_price_100 INTEGER DEFAULT 500",
                "ALTER TABLE guild_config ADD COLUMN pix_price_500 INTEGER DEFAULT 2000",
                "ALTER TABLE guild_config ADD COLUMN pix_price_1000 INTEGER DEFAULT 3500",
                "ALTER TABLE shop_config ADD COLUMN market_message_id INTEGER DEFAULT 0",
                "ALTER TABLE tickets_config ADD COLUMN panel_title TEXT DEFAULT '📬 Suporte'",
                "ALTER TABLE tickets_config ADD COLUMN panel_description TEXT DEFAULT 'Clique no botão abaixo para abrir um ticket privado com a equipe.'",
                "ALTER TABLE tickets_config ADD COLUMN ticket_title TEXT DEFAULT '🎫 Ticket de {user}'",
                "ALTER TABLE tickets_config ADD COLUMN ticket_description TEXT DEFAULT 'Olá, {user}! Descreva sua dúvida e a equipe irá ajudar.'",
                "ALTER TABLE tickets_config ADD COLUMN close_message TEXT DEFAULT '🔒 Ticket fechado por {closer}. Este canal será deletado em 5 segundos.'",
            ]
            for stmt in migrations:
                try:
                    await db.execute(stmt)
                    await db.commit()
                except Exception:
                    pass

    # ── Users ────────────────────────────────────────────────────────────────

    async def get_user(self, user_id: int, guild_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id=? AND guild_id=?",
                (user_id, guild_id),
            ) as cur:
                row = await cur.fetchone()
            if row:
                return dict(row)
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?,?)",
                (user_id, guild_id),
            )
            await db.commit()
            return {
                "user_id": user_id, "guild_id": guild_id,
                "xp": 0, "level": 0, "messages": 0,
                "balance": 0, "last_xp_ts": 0.0,
            }

    async def add_xp(self, user_id: int, guild_id: int, xp_gain: int, coins_gain: int, ts: float):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO users (user_id, guild_id, xp, messages, balance, last_xp_ts)
                VALUES (?,?,?,1,?,?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    xp         = xp + ?,
                    messages   = messages + 1,
                    balance    = balance + ?,
                    last_xp_ts = ?
                """,
                (user_id, guild_id, xp_gain, coins_gain, ts, xp_gain, coins_gain, ts),
            )
            await db.commit()

    async def set_user_xp(self, user_id: int, guild_id: int, xp: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET xp=? WHERE user_id=? AND guild_id=?",
                (xp, user_id, guild_id),
            )
            await db.commit()

    async def add_coins(self, user_id: int, guild_id: int, amount: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO users (user_id, guild_id, balance) VALUES (?,?,?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET balance = balance + ?
                """,
                (user_id, guild_id, amount, amount),
            )
            await db.commit()

    async def deduct_coins(self, user_id: int, guild_id: int, amount: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET balance=balance-? WHERE user_id=? AND guild_id=? AND balance>=?",
                (amount, user_id, guild_id, amount),
            )
            await db.commit()
            return db.total_changes > 0

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE guild_id=? ORDER BY xp DESC LIMIT ?",
                (guild_id, limit),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_rank(self, user_id: int, guild_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """
                SELECT COUNT(*)+1 FROM users
                WHERE guild_id=? AND xp>(SELECT xp FROM users WHERE user_id=? AND guild_id=?)
                """,
                (guild_id, user_id, guild_id),
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else 1

    # ── Profiles ─────────────────────────────────────────────────────────────

    async def get_profile(self, user_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM profiles WHERE user_id=?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
            if row:
                return dict(row)
            return {
                "user_id": user_id, "bio": "", "banner_url": "",
                "icon_url": "", "color": "#5865F2",
                "background_color": "#2C2F33", "theme": "escuro",
            }

    async def update_profile(self, user_id: int, **fields):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO profiles (user_id) VALUES (?)", (user_id,)
            )
            for key, val in fields.items():
                await db.execute(
                    f"UPDATE profiles SET {key}=? WHERE user_id=?", (val, user_id)
                )
            await db.commit()

    # ── Shop ─────────────────────────────────────────────────────────────────

    async def get_shop(self, guild_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM shop_items WHERE guild_id=? ORDER BY price", (guild_id,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_shop_item(self, item_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM shop_items WHERE id=?", (item_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def add_shop_item(
        self,
        guild_id: int,
        role_id: int,
        name: str,
        price: int,
        description: str = "",
        emoji: str = "🎭",
        is_custom: bool = False,
        xp_multiplier: float = 1.0,
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO shop_items (guild_id,role_id,name,price,description,emoji,is_custom,xp_multiplier)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (guild_id, role_id, name, price, description, emoji, int(is_custom), xp_multiplier),
            )
            await db.commit()
            return cur.lastrowid

    async def remove_shop_item(self, item_id: int, guild_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM shop_items WHERE id=? AND guild_id=?", (item_id, guild_id)
            )
            await db.commit()

    async def has_purchased(self, user_id: int, guild_id: int, item_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT 1 FROM user_purchases WHERE user_id=? AND guild_id=? AND item_id=?",
                (user_id, guild_id, item_id),
            ) as cur:
                return await cur.fetchone() is not None

    async def buy_item(self, user_id: int, guild_id: int, item_id: int, price: int) -> bool:
        """Debita saldo e registra compra atomicamente. Falha se saldo baixo ou já comprou."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT balance FROM users WHERE user_id=? AND guild_id=?",
                (user_id, guild_id),
            ) as cur:
                row = await cur.fetchone()

            if row is None or row[0] < price:
                await db.rollback()
                return False

            async with db.execute(
                "SELECT 1 FROM user_purchases WHERE user_id=? AND guild_id=? AND item_id=?",
                (user_id, guild_id, item_id),
            ) as cur:
                if await cur.fetchone():
                    await db.rollback()
                    return False

            await db.execute(
                "UPDATE users SET balance=balance-? WHERE user_id=? AND guild_id=? AND balance>=?",
                (price, user_id, guild_id, price),
            )
            if db.total_changes == 0:
                await db.rollback()
                return False

            await db.execute(
                "INSERT INTO user_purchases (user_id,guild_id,item_id,purchased_at)"
                " VALUES (?,?,?,?)",
                (user_id, guild_id, item_id, datetime.utcnow().isoformat()),
            )
            await db.commit()
            return True

    async def remove_shop_purchase(self, user_id: int, guild_id: int, item_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM user_purchases WHERE user_id=? AND guild_id=? AND item_id=?",
                (user_id, guild_id, item_id),
            )
            await db.commit()

    async def get_purchases(self, user_id: int, guild_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT s.* FROM user_purchases p
                JOIN shop_items s ON s.id=p.item_id
                WHERE p.user_id=? AND p.guild_id=?
                """,
                (user_id, guild_id),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_shop_config(self, guild_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "INSERT OR IGNORE INTO shop_config (guild_id) VALUES (?)", (guild_id,)
            )
            await db.commit()
            async with db.execute(
                "SELECT * FROM shop_config WHERE guild_id=?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row)

    async def set_shop_config(self, guild_id: int, **fields):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO shop_config (guild_id) VALUES (?)", (guild_id,)
            )
            for key, val in fields.items():
                await db.execute(
                    f"UPDATE shop_config SET {key}=? WHERE guild_id=?", (val, guild_id)
                )
            await db.commit()

    # ── Guild Config ─────────────────────────────────────────────────────────

    async def get_guild_config(self, guild_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM guild_config WHERE guild_id=?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
            if row:
                return dict(row)
            return {
                "guild_id": guild_id,
                "level_channel_id": 0,
                "xp_min": 15,
                "xp_max": 25,
                "xp_cooldown": 60,
                "coins_per_msg": 5,
                "level_up_msg": "🎉 {user} subiu para o nível **{level}**!",
                "welcome_channel_id": 0,
                "welcome_message": "Bem-vindo(a) {user} ao servidor!",
                "welcome_image_url": "",
                "shop_channel_id": 0,
                "shop_message_id": 0,
                "level_coins_base": 100,
                "pix_key": "",
                "pix_price_100": 500,
                "pix_price_500": 2000,
                "pix_price_1000": 3500,
            }

    async def set_guild_config(self, guild_id: int, **fields):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,)
            )
            for key, val in fields.items():
                await db.execute(
                    f"UPDATE guild_config SET {key}=? WHERE guild_id=?", (val, guild_id)
                )
            await db.commit()

    # ── Level Roles ──────────────────────────────────────────────────────────

    async def get_level_roles(self, guild_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM level_roles WHERE guild_id=? ORDER BY level", (guild_id,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def set_level_role(self, guild_id: int, level: int, role_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO level_roles (guild_id, level, role_id) VALUES (?,?,?)
                ON CONFLICT(guild_id, level) DO UPDATE SET role_id=?
                """,
                (guild_id, level, role_id, role_id),
            )
            await db.commit()

    async def remove_level_role(self, guild_id: int, level: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM level_roles WHERE guild_id=? AND level=?", (guild_id, level)
            )
            await db.commit()

    # ── Warns ────────────────────────────────────────────────────────────────

    async def add_warn(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO warns (guild_id,user_id,moderator_id,reason,created_at) VALUES (?,?,?,?,?)",
                (guild_id, user_id, moderator_id, reason, datetime.utcnow().isoformat()),
            )
            await db.commit()
            return cur.lastrowid

    async def get_warns(self, guild_id: int, user_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM warns WHERE guild_id=? AND user_id=? ORDER BY created_at DESC",
                (guild_id, user_id),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def remove_warn(self, warn_id: int, guild_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM warns WHERE id=? AND guild_id=?", (warn_id, guild_id)
            )
            await db.commit()
            return db.total_changes > 0

    async def clear_warns(self, guild_id: int, user_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM warns WHERE guild_id=? AND user_id=?", (guild_id, user_id)
            )
            await db.commit()
            return db.total_changes

    # ── Daily Claims ─────────────────────────────────────────────────────────

    async def get_daily_claim(self, user_id: int) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT last_claim FROM daily_claims WHERE user_id=?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def set_daily_claim(self, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO daily_claims (user_id, last_claim) VALUES (?,?)",
                (user_id, datetime.utcnow().strftime("%Y-%m-%d")),
            )
            await db.commit()

    # ── Marriages ────────────────────────────────────────────────────────────

    async def create_marriage(self, guild_id: int, user1_id: int, user2_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO marriages (guild_id,user1_id,user2_id,married_at) VALUES (?,?,?,?)",
                (guild_id, user1_id, user2_id, datetime.utcnow().isoformat()),
            )
            await db.commit()
            return cur.lastrowid

    async def get_marriage(self, user_id: int, guild_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM marriages WHERE (user1_id=? OR user2_id=?) AND guild_id=?",
                (user_id, user_id, guild_id),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_marriage_by_id(self, marriage_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM marriages WHERE id=?", (marriage_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def dissolve_marriage(self, marriage_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM marriages WHERE id=?", (marriage_id,))
            await db.commit()

    async def set_godparent(self, marriage_id: int, slot: int, user_id: int):
        col = "godparent1_id" if slot == 1 else "godparent2_id"
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                f"UPDATE marriages SET {col}=? WHERE id=?", (user_id, marriage_id)
            )
            await db.commit()

    async def remove_godparent(self, marriage_id: int, slot: int):
        col = "godparent1_id" if slot == 1 else "godparent2_id"
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                f"UPDATE marriages SET {col}=0 WHERE id=?", (marriage_id,)
            )
            await db.commit()

    async def get_godparent_marriages(self, user_id: int, guild_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM marriages WHERE (godparent1_id=? OR godparent2_id=?) AND guild_id=?",
                (user_id, user_id, guild_id),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def marriage_deposit(self, marriage_id: int, user_id: int, guild_id: int, amount: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET balance=balance-? WHERE user_id=? AND guild_id=? AND balance>=?",
                (amount, user_id, guild_id, amount),
            )
            if db.total_changes == 0:
                return False
            await db.execute(
                "UPDATE marriages SET shared_balance=shared_balance+? WHERE id=?",
                (amount, marriage_id),
            )
            await db.commit()
            return True

    async def marriage_withdraw(self, marriage_id: int, user_id: int, guild_id: int, amount: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE marriages SET shared_balance=shared_balance-? WHERE id=? AND shared_balance>=?",
                (amount, marriage_id, amount),
            )
            if db.total_changes == 0:
                return False
            await db.execute(
                "UPDATE users SET balance=balance+? WHERE user_id=? AND guild_id=?",
                (amount, user_id, guild_id),
            )
            await db.commit()
            return True

    # ── Clans ────────────────────────────────────────────────────────────────

    async def create_clan(
        self,
        guild_id: int,
        name: str,
        owner_id: int,
        role_id: int,
        text_channel_id: int,
        voice_channel_id: int,
        color_hex: str,
        description: str,
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO clans (guild_id,name,owner_id,role_id,text_channel_id,voice_channel_id,color_hex,description,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (guild_id, name, owner_id, role_id, text_channel_id, voice_channel_id,
                 color_hex, description, datetime.utcnow().isoformat()),
            )
            await db.commit()
            return cur.lastrowid

    async def get_clan(self, clan_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM clans WHERE id=?", (clan_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_clan_by_name(self, guild_id: int, name: str) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM clans WHERE guild_id=? AND LOWER(name)=LOWER(?)",
                (guild_id, name),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_user_clan(self, user_id: int, guild_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT c.* FROM clan_members cm
                JOIN clans c ON cm.clan_id=c.id
                WHERE cm.user_id=? AND c.guild_id=?
                """,
                (user_id, guild_id),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_clan_members(self, clan_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM clan_members WHERE clan_id=? ORDER BY joined_at",
                (clan_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_all_clans(self, guild_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM clans WHERE guild_id=? ORDER BY name", (guild_id,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def update_clan(self, clan_id: int, **fields):
        async with aiosqlite.connect(self.path) as db:
            for key, val in fields.items():
                await db.execute(
                    f"UPDATE clans SET {key}=? WHERE id=?", (val, clan_id)
                )
            await db.commit()

    async def delete_clan(self, clan_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM clan_invites WHERE clan_id=?", (clan_id,))
            await db.execute("DELETE FROM clan_members WHERE clan_id=?", (clan_id,))
            await db.execute("DELETE FROM clans WHERE id=?", (clan_id,))
            await db.commit()

    async def add_clan_member(self, clan_id: int, user_id: int, member_role: str = "member"):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO clan_members (clan_id,user_id,joined_at,member_role) VALUES (?,?,?,?)",
                (clan_id, user_id, datetime.utcnow().isoformat(), member_role),
            )
            await db.commit()

    async def remove_clan_member(self, clan_id: int, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM clan_members WHERE clan_id=? AND user_id=?", (clan_id, user_id)
            )
            await db.commit()

    async def create_clan_invite(self, clan_id: int, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO clan_invites (clan_id,user_id,invited_at) VALUES (?,?,?)",
                (clan_id, user_id, datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def get_clan_invite(self, clan_id: int, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT 1 FROM clan_invites WHERE clan_id=? AND user_id=?", (clan_id, user_id)
            ) as cur:
                return await cur.fetchone() is not None

    async def remove_clan_invite(self, clan_id: int, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM clan_invites WHERE clan_id=? AND user_id=?", (clan_id, user_id)
            )
            await db.commit()

    # ── Tickets ──────────────────────────────────────────────────────────────

    async def get_tickets_config(self, guild_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tickets_config WHERE guild_id=?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                data = dict(row)
                data.setdefault("panel_title", "📬 Suporte")
                data.setdefault("panel_description", "Clique no botão abaixo para abrir um ticket privado com a equipe.")
                data.setdefault("ticket_title", "🎫 Ticket de {user}")
                data.setdefault("ticket_description", "Olá, {user}! Descreva sua dúvida e a equipe irá ajudar.")
                data.setdefault("close_message", "🔒 Ticket fechado por {closer}. Este canal será deletado em 5 segundos.")
                return data

    async def set_tickets_config(self, guild_id: int, **fields):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO tickets_config (guild_id) VALUES (?)", (guild_id,)
            )
            for key, val in fields.items():
                await db.execute(
                    f"UPDATE tickets_config SET {key}=? WHERE guild_id=?", (val, guild_id)
                )
            await db.commit()

    async def create_ticket(self, guild_id: int, user_id: int, channel_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO open_tickets (guild_id,user_id,channel_id,status,created_at) VALUES (?,?,?,?,?)",
                (guild_id, user_id, channel_id, "open", datetime.utcnow().isoformat()),
            )
            await db.commit()
            return cur.lastrowid

    async def close_ticket(self, ticket_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE open_tickets SET status='closed', closed_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), ticket_id),
            )
            await db.commit()

    async def get_open_ticket(self, user_id: int, guild_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM open_tickets WHERE user_id=? AND guild_id=? AND status='open'",
                (user_id, guild_id),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_ticket_by_channel(self, channel_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM open_tickets WHERE channel_id=?", (channel_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    # ── Role Market ──────────────────────────────────────────────────────────

    async def add_role_listing(self, guild_id: int, seller_id: int, role_id: int, price: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO role_listings (guild_id,seller_id,role_id,price,listed_at) VALUES (?,?,?,?,?)",
                (guild_id, seller_id, role_id, price, datetime.utcnow().isoformat()),
            )
            await db.commit()
            return cur.lastrowid

    async def get_role_listings(self, guild_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM role_listings WHERE guild_id=? ORDER BY listed_at DESC",
                (guild_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_role_listing(self, listing_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM role_listings WHERE id=?", (listing_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def remove_role_listing(self, listing_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM role_listings WHERE id=?", (listing_id,))
            await db.commit()

    async def get_user_listings(self, guild_id: int, seller_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM role_listings WHERE guild_id=? AND seller_id=?",
                (guild_id, seller_id),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    # ── XP Boost Roles ───────────────────────────────────────────────────────

    async def get_xp_boost_roles(self, guild_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM xp_boost_roles WHERE guild_id=?", (guild_id,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def set_xp_boost_role(self, guild_id: int, role_id: int, multiplier: float):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO xp_boost_roles (guild_id, role_id, multiplier) VALUES (?,?,?)
                ON CONFLICT(guild_id, role_id) DO UPDATE SET multiplier=?
                """,
                (guild_id, role_id, multiplier, multiplier),
            )
            await db.commit()

    async def remove_xp_boost_role(self, guild_id: int, role_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM xp_boost_roles WHERE guild_id=? AND role_id=?", (guild_id, role_id)
            )
            await db.commit()

    async def get_xp_multiplier(self, guild_id: int, role_ids: list) -> float:
        if not role_ids:
            return 1.0
        async with aiosqlite.connect(self.path) as db:
            placeholders = ",".join("?" * len(role_ids))
            async with db.execute(
                f"SELECT MAX(multiplier) FROM xp_boost_roles WHERE guild_id=? AND role_id IN ({placeholders})",
                [guild_id] + list(role_ids),
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row and row[0] is not None else 1.0

    # ── Anonymous ────────────────────────────────────────────────────────────

    async def get_anon_config(self, guild_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM anonymous_config WHERE guild_id=?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                d = dict(row)
                if not int(d.get("menu_channel_id") or 0):
                    d["menu_channel_id"] = int(d["channel_id"])
                return d

    async def set_anon_config(
        self,
        guild_id: int,
        output_channel_id: int,
        menu_channel_id: int | None = None,
        log_channel_id: int = 0,
    ):
        """Define canal de envio (`channel_id`) e canal onde fica o painel com botão (`menu_channel_id`)."""
        mc = menu_channel_id if menu_channel_id is not None else output_channel_id
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO anonymous_config (
                    guild_id, channel_id, menu_channel_id, log_channel_id, enabled, button_message_id
                )
                VALUES (?,?,?,?,1,0)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id=excluded.channel_id,
                    menu_channel_id=excluded.menu_channel_id,
                    log_channel_id=excluded.log_channel_id
                """,
                (guild_id, output_channel_id, mc, log_channel_id),
            )
            await db.commit()

    async def update_anon_button_message(self, guild_id: int, message_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE anonymous_config SET button_message_id=? WHERE guild_id=?",
                (message_id, guild_id),
            )
            await db.commit()

    async def toggle_anon(self, guild_id: int, enabled: bool):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE anonymous_config SET enabled=? WHERE guild_id=?",
                (1 if enabled else 0, guild_id),
            )
            await db.commit()

    # ── Giveaways ────────────────────────────────────────────────────────────

    async def create_giveaway(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        prize: str,
        winners: int,
        host_id: int,
        ends_at: str,
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO giveaways (guild_id,channel_id,message_id,prize,winners,host_id,ends_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (guild_id, channel_id, message_id, prize, winners, host_id, ends_at),
            )
            await db.commit()
            return cur.lastrowid

    async def update_giveaway_message(self, giveaway_id: int, message_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE giveaways SET message_id=? WHERE id=?", (message_id, giveaway_id)
            )
            await db.commit()

    async def get_giveaway(self, giveaway_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM giveaways WHERE id=?", (giveaway_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_active_giveaways(self) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM giveaways WHERE ended=0") as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def end_giveaway(self, giveaway_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE giveaways SET ended=1 WHERE id=?", (giveaway_id,)
            )
            await db.commit()

    async def add_entry(self, giveaway_id: int, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO giveaway_entries (giveaway_id,user_id) VALUES (?,?)",
                (giveaway_id, user_id),
            )
            await db.commit()

    async def remove_entry(self, giveaway_id: int, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM giveaway_entries WHERE giveaway_id=? AND user_id=?",
                (giveaway_id, user_id),
            )
            await db.commit()

    async def get_entries(self, giveaway_id: int) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT user_id FROM giveaway_entries WHERE giveaway_id=?", (giveaway_id,)
            ) as cur:
                return [r[0] for r in await cur.fetchall()]

    async def has_entered(self, giveaway_id: int, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT 1 FROM giveaway_entries WHERE giveaway_id=? AND user_id=?",
                (giveaway_id, user_id),
            ) as cur:
                return await cur.fetchone() is not None
