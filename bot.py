import os
import json
import time
import logging
from pathlib import Path
from functools import wraps
from typing import Tuple, Optional

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
)

# ===================== CONFIG =====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("ENV TELEGRAM_TOKEN belum di-set!")

# GANTI dengan user id lu (bisa lebih dari satu)
OWNER_IDS = {123456789}

GROUP_LINK = "https://t.me/VANZSHOPGROUP"
CHANNEL_LINK = "https://t.me/VanzDisscusion"

BOT_NAME = "VanzSecurity Bot"
BOT_VERSION = "1.0"

PREMIUM_FILE = Path("premium.json")

# ==================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# cache admin per grup (di-RAM)
chat_admins_cache: dict[int, set[int]] = {}


# =============== PREMIUM STORAGE ===============

def load_premium() -> dict:
    if not PREMIUM_FILE.exists():
        return {}
    try:
        with PREMIUM_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_premium(data: dict):
    try:
        with PREMIUM_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("Gagal menyimpan premium.json: %s", e)


def is_chat_premium(chat_id: int) -> Tuple[bool, Optional[int]]:
    """Return (is_premium, expires_at)."""
    data = load_premium()
    info = data.get(str(chat_id))
    if not info:
        return False, None

    expires_at = int(info.get("expires_at", 0))
    if expires_at != 0 and expires_at < int(time.time()):
        # sudah expired → hapus
        data.pop(str(chat_id), None)
        save_premium(data)
        return False, expires_at

    return True, expires_at


# =============== HELPER DECORATORS ===============

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


def premium_required(func):
    """Fitur hanya bisa dipakai di grup premium."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        message = update.effective_message

        if chat.type not in ("group", "supergroup"):
            await message.reply_text("Fitur ini khusus untuk grup premium.")
            return

        ok, expires_at = is_chat_premium(chat.id)
        if not ok:
            await message.reply_text(
                "❌ Grup ini belum premium / sudah expired.\n"
                "Hubungi owner bot untuk aktivasi premium."
            )
            return

        return await func(update, context)

    return wrapper


# =============== KEYBOARD BUILDERS ===============

def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("⚔️ Security", callback_data="menu_security"),
            InlineKeyboardButton("🛠 Moderation", callback_data="menu_moderation"),
        ],
        [
            InlineKeyboardButton("⚙️ Utility", callback_data="menu_utility"),
            InlineKeyboardButton("😎 Fun", callback_data="menu_fun"),
        ],
        [
            InlineKeyboardButton("⭐ Premium", callback_data="menu_premium"),
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
        "Gunakan tombol di bawah untuk mengakses menu.\n\n"
        f"🔗 *Grup:* {GROUP_LINK}\n"
        f"📢 *Channel:* {CHANNEL_LINK}\n\n"
        "Ketik /help untuk lihat perintah dasar."
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
        "👑 /reload - memperbarui daftar Admin dan hak istimewanya\n"
        "👮 /settings - mengelola semua pengaturan Bot di grup\n\n"
        "👮 /ban - blokir pengguna dari grup\n"
        "👮 /mute - mode hanya-membaca (bisa lihat, tidak bisa chat)\n"
        "👮 /kick - tendang pengguna dari grup\n"
        "👮 /unban - hapus blokir pengguna dari grup\n\n"
        "👮 /info - info tentang pengguna (balas pesan target)\n"
        "👮 /infopvt - kirim info pengguna via obrolan pribadi\n\n"
        "👮 /staff - daftar lengkap staf grup\n\n"
        "⭐ Premium:\n"
        "👑 /addpremium <hari> - jadikan grup ini premium / perpanjang\n"
        "👮 /premstatus - cek status premium grup\n"
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
async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⚙️ *Panel Pengaturan Grup*\n\n"
        "Di sini nanti kamu bisa mengatur:\n"
        "- Anti-toxic\n"
        "- Anti-link\n"
        "- Hukuman otomatis\n"
        "- Dll.\n"
    )

    keyboard = [
        [InlineKeyboardButton("⚔️ Security Settings", callback_data="settings_security")],
        [InlineKeyboardButton("🛠 Moderation Settings", callback_data="settings_moderation")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="menu_main")],
    ]

    await update.effective_message.reply_markdown(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


@admin_required
async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat

    target = None
    reason = " ".join(context.args) if context.args else ""

    if message.reply_to_message:
        target = message.reply_to_message.from_user

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
            f"🤐 {target.mention_html()} sekarang hanya bisa membaca.",
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


# --------- PREMIUM COMMANDS ---------

async def addpremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message

    if user.id not in OWNER_IDS:
        await message.reply_text("Perintah ini cuma buat Owner bot bro.")
        return

    if chat.type not in ("group", "supergroup"):
        await message.reply_text(
            "Jalankan /addpremium di dalam grup yang mau dijadikan premium."
        )
        return

    if not context.args:
        await message.reply_text("Pakai: /addpremium <jumlah_hari>\nContoh: /addpremium 30")
        return

    try:
        days = int(context.args[0])
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.reply_text("Jumlah hari tidak valid.")
        return

    now = int(time.time())
    data = load_premium()

    current_premium, current_exp = is_chat_premium(chat.id)
    if current_premium and current_exp:
        base = current_exp
    else:
        base = now

    new_exp = base + days * 24 * 60 * 60

    data[str(chat.id)] = {
        "expires_at": new_exp,
        "added_by": user.id,
    }
    save_premium(data)

    sisa_hari = int((new_exp - now) / 86400)

    await message.reply_text(
        f"✅ Grup *{chat.title}* sekarang PREMIUM.\n"
        f"⏰ Berlaku sampai: <code>{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(new_exp))}</code>\n"
        f"📅 Sisa ~{sisa_hari} hari.",
        parse_mode="HTML",
    )


async def premstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    message = update.effective_message

    if chat.type not in ("group", "supergroup"):
        await message.reply_text("Perintah ini khusus di dalam grup.")
        return

    ok, expires_at = is_chat_premium(chat.id)
    if not ok:
        await message.reply_text(
            f"❌ Grup *{chat.title}* saat ini *Bukan Premium*.",
            parse_mode="Markdown",
        )
        return

    sisa = expires_at - int(time.time())
    sisa_hari = max(0, int(sisa / 86400))

    await message.reply_text(
        f"⭐ Grup *{chat.title}* adalah *GRUP PREMIUM*.\n"
        f"⏰ Expired: <code>{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}</code>\n"
        f"📅 Sisa ~{sisa_hari} hari.",
        parse_mode="HTML",
    )


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

    if data == "menu_security":
        text = (
            "⚔️ *Menu Security*\n\n"
            "Fitur terkait keamanan grup:\n"
            "- Anti toxic\n"
            "- Anti spam\n"
            "- Anti link\n"
            "- Hukuman otomatis\n\n"
            "_(Masih kerangka, fitur detail akan ditambahkan kemudian.)_"
        )
        await query.edit_message_text(
            text=text,
            reply_markup=build_back_menu("main"),
            parse_mode="Markdown",
        )
        return

    if data == "menu_moderation":
        text = (
            "🛠 *Menu Moderation*\n\n"
            "Gunakan command:\n"
            "- /ban, /mute, /kick, /unban\n"
            "- /info, /infopvt, /staff\n\n"
            "Panel lanjutan akan ditambah kemudian."
        )
        await query.edit_message_text(
            text=text,
            reply_markup=build_back_menu("main"),
            parse_mode="Markdown",
        )
        return

    if data == "menu_utility":
        text = (
            "⚙️ *Menu Utility*\n\n"
            "Nanti berisi fitur:\n"
            "- Tools convert file\n"
            "- Scraping, cek info, dll."
        )
        await query.edit_message_text(
            text=text,
            reply_markup=build_back_menu("main"),
            parse_mode="Markdown",
        )
        return

    if data == "menu_fun":
        text = (
            "😎 *Menu Fun*\n\n"
            "Nanti berisi fitur:\n"
            "- Games kecil\n"
            "- Meme\n"
            "- Dll."
        )
        await query.edit_message_text(
            text=text,
            reply_markup=build_back_menu("main"),
            parse_mode="Markdown",
        )
        return

    if data == "menu_premium":
        text = (
            "⭐ *Menu Premium*\n\n"
            "Di sini nantinya user bisa beli & cek status premium.\n"
            "Saat ini:\n"
            "- /premstatus → cek status grup\n"
            "- Owner bot bisa pakai /addpremium <hari>."
        )
        await query.edit_message_text(
            text=text,
            reply_markup=build_back_menu("main"),
            parse_mode="Markdown",
        )
        return

    if data == "menu_owner":
        text = (
            "👑 *Owner Panel*\n\n"
            "Panel khusus Owner / Admin utama untuk mengatur:\n"
            "- Limit grup\n"
            "- Paket premium\n"
            "- Broadcast, dll.\n\n"
            "Masih kerangka, nanti kita expand."
        )
        await query.edit_message_text(
            text=text,
            reply_markup=build_back_menu("main"),
            parse_mode="Markdown",
        )
        return

    if data.startswith("settings_"):
        await query.edit_message_text(
            text="⚙️ Menu pengaturan detail belum diisi.\n"
                 "Nanti akan dihubungkan ke config anti-toxic, anti-link, dll.",
            reply_markup=build_back_menu("main"),
        )


# =============== MAIN ===============

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # command dasar
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    app.add_handler(CommandHandler("reload", reload_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("kick", kick_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("info", info_cmd))
    app.add_handler(CommandHandler("infopvt", infopvt_cmd))
    app.add_handler(CommandHandler("staff", staff_cmd))

    # premium
    app.add_handler(CommandHandler("addpremium", addpremium_cmd))
    app.add_handler(CommandHandler("premstatus", premstatus_cmd))

    # callback menu
    app.add_handler(CallbackQueryHandler(menu_callback))

    logger.info("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
