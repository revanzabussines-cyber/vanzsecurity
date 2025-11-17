import os
import re
import json
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# ================== CONFIG ==================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")

DATA_FILE = Path("blocked_words.json")

# Kata kasar default (global, kepake di semua grup)
DEFAULT_BLOCKED_WORDS = {
    # Indo
    "anjing", "anjg", "anj", "njing",
    "bangsat", "bgsat", "bgs",
    "kontol", "kontl",
    "memek", "mmk", "meki",
    "pepek", "ppk",
    "peler", "pler",
    "pantek", "panteq",
    "puki", "pukimak",
    "tai", "tae", "taik",
    "goblok", "gblk", "goblog",
    "tolol", "idiot", "bego",
    "kampret", "kampang",
    # Inggris
    "fuck", "fck", "fucking",
    "shit", "bullshit",
    "bitch", "btch",
    "bastard",
    "asshole", "assh0le",
    "dick", "d1ck",
    "pussy", "slut", "whore",
}

# { str(chat_id): [word1, word2, ...] }
CHAT_CUSTOM_WORDS: dict[str, list[str]] = {}


# ================== STORAGE ==================

def load_data():
    global CHAT_CUSTOM_WORDS
    if DATA_FILE.exists():
        try:
            with DATA_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            CHAT_CUSTOM_WORDS = data.get("chats", {})
        except Exception:
            CHAT_CUSTOM_WORDS = {}
    else:
        CHAT_CUSTOM_WORDS = {}


def save_data():
    data = {"chats": CHAT_CUSTOM_WORDS}
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_chat_custom_words(chat_id: int) -> set[str]:
    key = str(chat_id)
    words = CHAT_CUSTOM_WORDS.get(key, [])
    return set(words)


def set_chat_custom_words(chat_id: int, words: set[str]):
    key = str(chat_id)
    CHAT_CUSTOM_WORDS[key] = sorted(list(words))
    save_data()


# ================== TEXT NORMALIZATION ==================

def normalize_text(text: str) -> str:
    """
    Normalisasi teks:
    - lowercase
    - hapus karakter non-alfanumerik
    - rapikan huruf yang berulang berlebihan (koooontooool -> koontool)
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)

    def _shrink(match: re.Match) -> str:
        char = match.group(1)
        return char * 2

    text = re.sub(r"(.)\1{2,}", _shrink, text)
    return text


def contains_blocked_word(text: str, chat_id: int) -> bool:
    """Cek text mengandung kata kasar default + custom per chat."""
    if not text:
        return False

    norm = normalize_text(text)
    tokens = norm.split()

    # gabung global + custom chat
    all_blocked = set(DEFAULT_BLOCKED_WORDS)
    all_blocked.update(get_chat_custom_words(chat_id))

    # cek per kata
    for t in tokens:
        for bad in all_blocked:
            if bad in t:
                return True

    # cek full text juga (jaga2)
    for bad in all_blocked:
        if bad in norm:
            return True

    return False


# ================== UTILS ==================

async def is_admin_or_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Cek apakah user admin grup / owner, atau chat private."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return False

    # Private chat: user bebas atur sendiri
    if chat.type == chat.PRIVATE:
        return True

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator", "owner")
    except Exception:
        return False


# ================== HANDLER: TEXT ==================

async def text_filter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat

    if not message or not message.text or not chat:
        return

    text = message.text

    if contains_blocked_word(text, chat.id):
        user = update.effective_user

        # Coba hapus pesan
        try:
            await message.delete()
            deleted = True
        except Exception:
            deleted = False

        # ⚠️ DISINI UDAH CLEAN: ga ada "kata terlarang terdeteksi" & ga ada "Made by"
        if deleted:
            warn_text = "🧹 Pesan melanggar aturan dan sudah dihapus."
        else:
            warn_text = "❗ Pesan melanggar aturan, tapi bot tidak punya izin untuk menghapus."

        if user:
            warn_text += f"\n\n👤 User: `{user.id}` (@{user.username or 'no-username'})"

        await context.bot.send_message(
            chat_id=chat.id,
            text=warn_text,
            parse_mode="Markdown",
        )


# ================== HANDLER: COMMAND ==================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start sekarang simple & clean:
    - tanpa list command admin
    """
    chat = update.effective_chat

    if chat and chat.type != chat.PRIVATE:
        # Kalau dipanggil di grup
        text = (
            "👋 Bot aktif di grup ini.\n"
            "Aku akan membantu menjaga percakapan tetap rapi dengan menghapus pesan yang mengandung kata yang sudah diblokir."
        )
    else:
        # Kalau di private chat
        text = (
            "👋 Halo!\n"
            "Aku bot filter kata yang bisa kamu tambahkan ke grup untuk bantu bersihin chat."
        )

    await update.effective_message.reply_text(text)


async def addword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message

    if not chat:
        return

    if not await is_admin_or_private(update, context):
        await msg.reply_text("❌ Fitur ini cuma bisa dipakai admin grup / owner.")
        return

    if not context.args:
        await msg.reply_text("Usage: `/addword kata_kasar`", parse_mode="Markdown")
        return

    raw_word = " ".join(context.args).strip().lower()
    norm_word = re.sub(r"[^a-z0-9]", "", raw_word)

    if not norm_word:
        await msg.reply_text("❌ Kata tidak valid.")
        return

    custom_words = get_chat_custom_words(chat.id)
    if norm_word in custom_words:
        await msg.reply_text(f"ℹ️ Kata `{norm_word}` sudah ada di list.", parse_mode="Markdown")
        return

    custom_words.add(norm_word)
    set_chat_custom_words(chat.id, custom_words)

    await msg.reply_text(
        f"✅ Kata `{norm_word}` ditambahkan ke list terlarang untuk grup ini.",
        parse_mode="Markdown",
    )


async def delword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message

    if not chat:
        return

    if not await is_admin_or_private(update, context):
        await msg.reply_text("❌ Fitur ini cuma bisa dipakai admin grup / owner.")
        return

    if not context.args:
        await msg.reply_text("Usage: `/delword kata_kasar`", parse_mode="Markdown")
        return

    raw_word = " ".join(context.args).strip().lower()
    norm_word = re.sub(r"[^a-z0-9]", "", raw_word)

    custom_words = get_chat_custom_words(chat.id)
    if norm_word not in custom_words:
        await msg.reply_text(
            f"❌ Kata `{norm_word}` tidak ada di list custom.",
            parse_mode="Markdown",
        )
        return

    custom_words.remove(norm_word)
    set_chat_custom_words(chat.id, custom_words)

    await msg.reply_text(
        f"🗑 Kata `{norm_word}` dihapus dari list custom.",
        parse_mode="Markdown",
    )


async def listword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message

    if not chat:
        return

    custom_words = sorted(list(get_chat_custom_words(chat.id)))

    if not custom_words:
        await msg.reply_text("📭 Belum ada kata custom untuk grup ini.")
        return

    joined = ", ".join(custom_words)
    text = (
        "📃 *Daftar kata terlarang custom untuk grup ini:*\n"
        f"`{joined}`"
    )
    await msg.reply_text(text, parse_mode="Markdown")


# ================== MAIN ==================

def main():
    load_data()
    print("Bot started...")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("addword", addword_cmd))
    app.add_handler(CommandHandler("delword", delword_cmd))
    app.add_handler(CommandHandler("listword", listword_cmd))

    # Text filter
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_filter_handler))

    print("Running polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
