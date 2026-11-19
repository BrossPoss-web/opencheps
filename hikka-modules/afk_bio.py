from .. import loader, utils
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.errors import FloodWaitError
import asyncio
import logging
import random
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    BERLIN = ZoneInfo("Europe/Berlin")
except ImportError:
    # На старых версиях Python используем системный часовой пояс устройства.
    BERLIN = None

logger = logging.getLogger(__name__)


@loader.tds
class AFKBioMod(loader.Module):
    """Меняет BIO на разговорные AFK-статусы."""

    strings = {"name": "AFKBio"}

    STATUSES = [
        "sleep", "afk", "ushel", "splu", "zzz", "я сплю",
        "ушел спать", "ушел", "отошел", "не у телефона",
        "меня нет", "позже буду", "сплю", "пошел спать",
        "уже сплю", "не отвечаю", "я пропал", "отдыхаю",
        "в кровати", "пока сплю", "не дома", "засыпаю",
        "вырубился", "телефон отложил", "пока занят",
        "вернусь позже", "ушел гулять", "пошел отдыхать",
        "не у компа", "отошел ненадолго", "я уже лег",
        "пора спать", "свалил", "brb", "sleeping",
        "offline", "gone", "away", "я занят", "позже отвечу",
        "меня пока нет", "пошел по делам", "ушел по делам",
        "отвечу как проснусь", "не сижу в телефоне",
        "сейчас отдыхаю", "глаза закрываются", "пойду посплю",
        "до утра", "до вечера", "не теряйте", "пока без меня",
        "я уже вырубился", "сегодня без меня", "появлюсь позже",
        "пока не до сообщений", "я на паузе", "спать охота",
        "ушел на улицу", "не у экрана", "позже гляну",
        "телефон далеко", "пока занят делами", "я отвалился"
    ]

    TEMPLATES = [
        "{s} с {start}, отвечу к {end}",
        "{s} с {start}, буду примерно к {end}",
        "{s} с {start}, вернусь после {end}",
        "{s} с {start}, раньше {end} не ждите",
        "{s} с {start}, появлюсь ближе к {end}",
        "{s} с {start}, на связи после {end}",
        "{s} с {start}, сообщения гляну к {end}",
        "{s} с {start}, буду уже к {end}",
        "{s} с {start}, пока меня нет до {end}",
        "{s} с {start}, загляну сюда после {end}",
        "{s} с {start}, отвечу когда вернусь к {end}",
        "{s} с {start}, до {end} меня не будет",
        "{s} с {start}, думаю буду к {end}",
        "{s} с {start}, вернусь где-то к {end}",
        "{s} с {start}, всем отвечу после {end}",
        "{s} с {start}, пока отдыхаю до {end}",
        "{s} с {start}, увидимся ближе к {end}",
        "{s} с {start}, буду на месте после {end}",
        "{s} с {start}, телефон отложил до {end}",
        "{s} с {start}, появлюсь уже после {end}",
        "{s} с {start}, если что, буду к {end}",
        "{s} с {start}, проверю сообщения около {end}",
        "{s} с {start}, вернусь где-то после {end}",
        "{s} с {start}, пока не трогайте, до {end} меня нет"
    ]

    def __init__(self):
        super().__init__()
        self.task = None
        self.started = None
        self.reply = None

    def now_berlin(self):
        if BERLIN is not None:
            return datetime.now(BERLIN).replace(second=0, microsecond=0)
        return datetime.now().astimezone().replace(second=0, microsecond=0)

    def format_time(self, value):
        return value.strftime("%H:%M").lstrip("0")

    def get_reply_time(self, now):
        hour = now.hour

        if hour < 6:
            # Ночью: случайное время утром.
            target = now.replace(hour=8, minute=0) + timedelta(
                minutes=random.randint(0, 180)
            )
            if target <= now:
                target += timedelta(days=1)
            return target

        if hour < 10:
            # Ранним утром: через 1–3 часа.
            return now + timedelta(minutes=random.randint(60, 180))

        if hour < 18:
            # Днём: вечером, примерно в 17–19 часов.
            target_hour = random.randint(max(17, hour + 1), 19)
            target_minute = random.randint(0, 59)
            return now.replace(
                hour=target_hour, minute=target_minute
            )

        # Вечером: на следующее утро.
        target = (now + timedelta(days=1)).replace(hour=8, minute=0)
        return target + timedelta(minutes=random.randint(0, 180))

    def make_bio(self):
        start = datetime.fromisoformat(self.started)
        reply = datetime.fromisoformat(self.reply)
        start_text = self.format_time(start)
        end_text = self.format_time(reply)

        # Несколько попыток, чтобы не обрезать фразу посреди слова.
        for _ in range(20):
            status = random.choice(self.STATUSES)
            template = random.choice(self.TEMPLATES)
            bio = template.format(s=status, start=start_text, end=end_text)
            if len(bio) <= 70:
                return bio

        return f"afk с {start_text}, отвечу к {end_text}"[:70]

    async def client_ready(self, client, db):
        self.client = client
        self._db = db

        self.started = db.get("AFKBio", "started", None)
        self.reply = db.get("AFKBio", "reply", None)

        if db.get("AFKBio", "running", False):
            if self.started and self.reply:
                self.task = asyncio.create_task(self.bio_loop())
            else:
                db.set("AFKBio", "running", False)

    async def runafkcmd(self, message):
        """Включить AFK BIO."""
        if self.task and not self.task.done():
            await utils.answer(message, "AFK уже включён")
            return

        now = self.now_berlin()
        reply = self.get_reply_time(now)

        self.started = now.isoformat()
        self.reply = reply.isoformat()

        self._db.set("AFKBio", "started", self.started)
        self._db.set("AFKBio", "reply", self.reply)
        self._db.set("AFKBio", "running", True)

        self.task = asyncio.create_task(self.bio_loop())

        await utils.answer(
            message,
            "AFK включён\n"
            f"Ушёл: {self.format_time(now)}\n"
            f"Примерно отвечу: {self.format_time(reply)}"
        )

    async def stopafkcmd(self, message):
        """Остановить AFK BIO."""
        self._db.set("AFKBio", "running", False)

        if self.task and not self.task.done():
            self.task.cancel()
            self.task = None

        await utils.answer(message, "AFK BIO выключен")

    async def bio_loop(self):
        while self._db.get("AFKBio", "running", False):
            try:
                await self.client(
                    UpdateProfileRequest(about=self.make_bio())
                )
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break

            except FloodWaitError as error:
                await asyncio.sleep(error.seconds)

            except Exception:
                logger.exception("AFKBio: ошибка обновления BIO")
                await asyncio.sleep(60)
