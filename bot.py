import os
import json
import time
import logging
from pathlib import Path
from functools import wraps
from typing import Tuple, Dict, List

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPermissions,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ===================== CONFIG =====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("ENV TELEGRAM_TOKEN belum di-set!")

# GANTI dengan user id lu (bisa lebih dari satu)
OWNER_IDS = {7321522905}

GROUP_LINK = "https://t.me/VANZSHOPGROUP"
CHANNEL_LINK = "https://t.me/VanzDisscusion"

BOT_NAME = "Security Sense Guard"
BOT_VERSION = "1.0"

WARN_FILE = Path("warns.json")
BLOCKED_WORDS_FILE = Path("blocked_words.json")

# Anti spam config
SPAM_WINDOW_SECONDS = 5          # window detik cek spam
SPAM_MAX_MESSAGES = 6           # >6 pesan dlm 5 detik = spam
SPAM_MUTE_SECONDS = 600         # 10 menit

# ==================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# cache admin per grup (di-RAM)
chat_admins_cache: Dict[int, set[int]] = {}

# cache simple buat spam: {(chat_id, user_id): [timestamps]}
spam_tracker: Dict[Tuple[int, int], List[float]] = {}


# =============== WARN STORAGE ===============

def load_warns() -> dict:
    if not WARN_FILE.exists():
        return {}
    try:
        with WARN_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_warns(data: dict):
    try:
        with WARN_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("Gagal menyimpan warns.json: %s", e)


def add_warn(chat_id: int, user_id: int) -> int:
    """Tambah warn untuk user di chat tertentu, return jumlah warn terbaru."""
    data = load_warns()
    chat_key = str(chat_id)
    user_key = str(user_id)

    if chat_key not in data:
        data[chat_key] = {}

    chat_warns = data[chat_key]
    chat_warns[user_key] = chat_warns.get(user_key, 0) + 1

    save_warns(data)
    return chat_warns[user_key]


# =============== HELPER DECORATOR ===============

def admin_required(func):
    """Command hanya boleh dipakai admin grup / owner bot."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user = update.effective_user
        message = update.effective_message

        if chat.type not in ("group", "supergroup"):
            await message.reply_text("Perintah ini hanya bisa di dalam grup.")
            return

        # ambil admin dari cache kalau ada
        admin_ids = chat_admins_cache.get(chat.id)

        if not admin_ids:
            admins = await context.bot.get_chat_administrators(chat.id)
            admin_ids = {a.user.id for a in admins}
            chat_admins_cache[chat.id] = admin_ids

        if user.id not in admin_ids and user.id not in OWNER_IDS:
            await message.reply_text("Perintah ini hanya untuk Admin / Owner grup.")
            return

        return await func(update, context)

    return wrapper


# =============== KEYBOARD BUILDERS ===============

def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("👑 Owner Panel", callback_data="menu_owner"),
        ],
        [
            InlineKeyboardButton("🆘 Bantuan Bot", callback_data="menu_help"),
            InlineKeyboardButton("📖 Perintah Bot", callback_data="menu_commands"),
        ],
        [
            InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK),
            InlineKeyboardButton("💬 Grup", url=GROUP_LINK),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_back_menu(parent: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Kembali", callback_data=f"menu_{parent}")]]
    )


# =============== COMMAND HANDLERS ===============

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"👋 Selamat datang di *{BOT_NAME}* (v{BOT_VERSION})\n\n"
        "Bot ini membantu mengamankan dan mengelola grup Telegram.\n"
        "Anti spam + Anti kata kasar aktif otomatis di grup.\n\n"
        "Ketik /help untuk lihat perintah dasar.\n\n"
        f"🔗 *Grup:* {GROUP_LINK}\n"
        f"📢 *Channel:* {CHANNEL_LINK}"
    )
    await update.effective_message.reply_markdown(
        text,
        reply_markup=build_main_menu(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*Perintah Dasar*\n\n"
        "👮 = Admin & Moderator\n"
        "👑 = Admin / Owner\n\n"
        "👑 /reload - memperbarui daftar Admin dan hak istimewanya\n\n"
        "👮 /ban - blokir pengguna dari grup (balas pesan target)\n"
        "👮 /mute - mode hanya-membaca (balas pesan target)\n"
        "👮 /kick - tendang pengguna dari grup (balas pesan target)\n"
        "👮 /unban <user_id> - hapus blokir pengguna\n\n"
        "👮 /info - info tentang pengguna (balas pesan target / diri sendiri)\n"
        "👮 /infopvt - kirim info pengguna via obrolan pribadi\n\n"
        "👮 /staff - daftar lengkap staf grup\n\n"
        "🔐 Proteksi otomatis:\n"
        "- Anti kata kasar → hapus pesan + warn\n"
        "- Banyak kata kasar / terlalu sering → mute / ban\n"
        "- Spam pesan banyak dalam waktu singkat → mute 10 menit\n"
    )
    await update.effective_message.reply_markdown(
        text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="menu_main")]]
        ),
    )


# --------- BASIC MODERATION ---------

@admin_required
async def reload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    admins = await context.bot.get_chat_administrators(chat.id)
    admin_ids = {a.user.id for a in admins}
    chat_admins_cache[chat.id] = admin_ids

    await update.effective_message.reply_text(
        f"✅ Daftar admin & moderator di grup ini sudah diperbarui.\n"
        f"Total admin: {len(admin_ids)}"
    )


@admin_required
async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat

    target = message.reply_to_message.from_user if message.reply_to_message else None
    reason = " ".join(context.args) if context.args else ""

    if not target:
        await message.reply_text("Balas pesan orang yang mau di /ban ya bro.")
        return

    try:
        await context.bot.ban_chat_member(chat.id, target.id)
        await message.reply_text(
            f"🚫 Pengguna {target.mention_html()} telah diblokir dari grup.\n"
            f"Alasan: {reason or '-'}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Gagal ban: %s", e)
        await message.reply_text("Gagal ban. Pastikan bot punya hak ban member.")


@admin_required
async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat

    if not message.reply_to_message:
        await message.reply_text("Balas pesan orang yang mau di /mute ya bro.")
        return

    target = message.reply_to_message.from_user

    perms = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )

    try:
        await context.bot.restrict_chat_member(chat.id, target.id, permissions=perms)
        await message.reply_text(
            f"🔇 {target.mention_html()} sekarang hanya bisa membaca.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Gagal mute: %s", e)
        await message.reply_text("Gagal mute. Pastikan bot punya hak restrict.")


@admin_required
async def kick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat

    if not message.reply_to_message:
        await message.reply_text("Balas pesan orang yang mau di /kick ya bro.")
        return

    target = message.reply_to_message.from_user

    try:
        await context.bot.ban_chat_member(chat.id, target.id)
        await context.bot.unban_chat_member(chat.id, target.id)
        await message.reply_text(
            f"👢 {target.mention_html()} sudah ditendang dari grup.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Gagal kick: %s", e)
        await message.reply_text("Gagal kick. Pastikan bot punya hak ban member.")


@admin_required
async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat

    if not context.args:
        await message.reply_text("Pakai: /unban <user_id>")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await message.reply_text("user_id tidak valid.")
        return

    try:
        await context.bot.unban_chat_member(chat.id, user_id)
        await message.reply_text(f"✅ User dengan ID {user_id} sudah di-unban.")
    except Exception as e:
        logger.exception("Gagal unban: %s", e)
        await message.reply_text("Gagal unban. Pastikan bot punya hak ban/unban member.")


@admin_required
async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message

    target = message.reply_to_message.from_user if message.reply_to_message else update.effective_user

    text = (
        f"🧾 *Info Pengguna*\n\n"
        f"ID: `{target.id}`\n"
        f"Nama: {target.full_name}\n"
        f"Username: @{target.username if target.username else '-'}\n"
        f"Bot: {'Ya' if target.is_bot else 'Tidak'}\n"
    )

    await message.reply_markdown(text)


@admin_required
async def infopvt_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    sender = update.effective_user

    if not message.reply_to_message:
        await message.reply_text(
            "Balas pesan target lalu pakai /infopvt untuk kirim info via DM."
        )
        return

    target = message.reply_to_message.from_user

    text = (
        f"🧾 *Info Pengguna dari grup {message.chat.title}*\n\n"
        f"ID: `{target.id}`\n"
        f"Nama: {target.full_name}\n"
        f"Username: @{target.username if target.username else '-'}\n"
        f"Bot: {'Ya' if target.is_bot else 'Tidak'}\n"
    )

    try:
        await context.bot.send_message(
            chat_id=sender.id,
            text=text,
            parse_mode="Markdown",
        )
        await message.reply_text("✅ Info sudah dikirim ke DM kamu.")
    except Exception:
        await message.reply_text("Gagal kirim DM. Pastikan kamu pernah chat bot di private.")


@admin_required
async def staff_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    admins = await context.bot.get_chat_administrators(chat.id)

    lines = ["*Daftar Staf Grup:*", ""]
    for a in admins:
        role = "Owner" if a.status == "creator" else "Admin"
        lines.append(f"- {a.user.mention_markdown()} (`{a.user.id}`) – *{role}*")

    text = "\n".join(lines)
    await update.effective_message.reply_markdown(text)


# =============== MESSAGE WATCHDOG ===============

def load_blocked_words() -> List[str]:
    if not BLOCKED_WORDS_FILE.exists():
        return []
    try:
        with BLOCKED_WORDS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [str(w).lower() for w in data]
            return []
    except Exception as e:
        logger.exception("Gagal baca blocked_words.json: %s", e)
        return []


async def message_watchdog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cek kata kasar + spam."""
    chat = update.effective_chat
    msg = update.effective_message
    user = update.effective_user

    if chat.type not in ("group", "supergroup"):
        return

    if not msg or not user or user.is_bot:
        return

    text = msg.text or ""
    if not text:
        return

    text_lower = text.lower()

    # --------- ANTI KATA KASAR ---------
    bad_words = load_blocked_words()
    matches = [w for w in bad_words if w in text_lower] if bad_words else []

    if matches:
        # hapus pesan
        try:
            await msg.delete()
        except Exception:
            pass

        # kalau banyak kata kasar dalam satu pesan → ban langsung
        if len(matches) >= 3:
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                await chat.send_message(
                    f"🚨 {user.mention_html()} diban karena menggunakan banyak kata kasar.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.exception("Gagal ban auto-toxic: %s", e)
            return

        # kalau cuma 1–2 kata kasar → warn system
        warn_count = add_warn(chat.id, user.id)

        if warn_count == 1:
            await chat.send_message(
                f"⚠️ {user.mention_html()} jangan kasar ya (1/5).",
                parse_mode="HTML",
            )
        elif warn_count == 2:
            await chat.send_message(
                f"⚠️ {user.mention_html()} sudah diperingati (2/5).",
                parse_mode="HTML",
            )
        elif warn_count in (3, 4):
            # mute
            perms = ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            )
            try:
                await context.bot.restrict_chat_member(chat.id, user.id, permissions=perms)
                await chat.send_message(
                    f"🔇 {user.mention_html()} di-mute karena terlalu sering berkata kasar ({warn_count}/5).",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.exception("Gagal mute auto-toxic: %s", e)
        elif warn_count >= 5:
            # ban
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                await chat.send_message(
                    f"🚫 {user.mention_html()} diban karena mencapai 5 peringatan kata kasar.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.exception("Gagal ban auto-toxic warn>=5: %s", e)

        # setelah proses kata kasar, gak usah cek spam
        return

    # --------- ANTI SPAM ---------
    now = time.time()
    key = (chat.id, user.id)
    history = spam_tracker.get(key, [])
    # buang yang kadaluwarsa
    history = [t for t in history if now - t <= SPAM_WINDOW_SECONDS]
    history.append(now)
    spam_tracker[key] = history

    if len(history) > SPAM_MAX_MESSAGES:
        # spam terdeteksi
        try:
            await msg.delete()
        except Exception:
            pass

        until = int(now + SPAM_MUTE_SECONDS)
        perms = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
        )
        try:
            await context.bot.restrict_chat_member(
                chat.id, user.id, permissions=perms, until_date=until
            )
            await chat.send_message(
                f"🚨 {user.mention_html()} di-mute {SPAM_MUTE_SECONDS//60} menit karena spam.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("Gagal mute auto-spam: %s", e)


# =============== CALLBACK MENU ===============

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_main":
        await query.edit_message_text(
            text=f"🏠 *Menu Utama {BOT_NAME}*",
            reply_markup=build_main_menu(),
            parse_mode="Markdown",
        )
        return

    if data == "menu_help":
        await query.edit_message_text(
            text="🆘 *Bantuan Bot*\n\n"
                 "Gunakan tombol di bawah untuk melihat daftar perintah dasar.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📖 Perintah Dasar", callback_data="menu_commands")],
                    [InlineKeyboardButton("⬅️ Kembali", callback_data="menu_main")],
                ]
            ),
            parse_mode="Markdown",
        )
        return

    if data == "menu_commands":
        await help_cmd(update, context)
        return

    if data == "menu_owner":
        text = (
            "👑 *Owner Panel*\n\n"
            "Panel khusus Owner / Admin utama.\n"
            "Saat ini:\n"
            "- Gunakan command manual (/ban, /mute, /kick, dll).\n"
            "Ke depan bisa ditambah pengaturan lanjutan di sini."
        )
        await query.edit_message_text(
            text=text,
            reply_markup=build_back_menu("main"),
            parse_mode="Markdown",
        )
        return


# =============== MAIN ===============

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # command dasar
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    app.add_handler(CommandHandler("reload", reload_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("kick", kick_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("info", info_cmd))
    app.add_handler(CommandHandler("infopvt", infopvt_cmd))
    app.add_handler(CommandHandler("staff", staff_cmd))

    # menu callback
    app.add_handler(CallbackQueryHandler(menu_callback))

    # watchdog: anti toxic + anti spam
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_watchdog))

    logger.info("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
