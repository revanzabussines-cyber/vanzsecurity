import os
import json
import re
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    ContextTypes, filters
)

# ================== CONFIG ==================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise RuntimeError("ENV TELEGRAM_TOKEN belum di-set!")

DATA_FILE = Path("blocked_words.json")
PREMIUM_FILE = Path("premium.json")

CREDIT = "Premium powered by @VanzzSkyyID"

# Default kata kasar global
DEFAULT_BLOCKED_WORDS = {
    "anjing", "anjg", "anj", "njing",
    "bangsat", "bgsat", "bgs",
    "kontol", "kontl",
    "memek", "mmk", "meki",
    "peler", "pler",
    "pantek", "panteq",
    "puki", "pukimak",
    "tai", "tae", "taik",
    "goblok", "gblk", "goblog",
    "tolol", "idiot", "bego",
    "kampret", "kampang",
    "fuck", "fck", "fucking",
    "shit", "bullshit",
    "bitch", "btch",
    "asshole", "assh0le",
    "whore", "slut",
}

CHAT_CUSTOM_WORDS = {}
PREMIUM_GROUPS = {}

# ================== STORAGE ==================

def load_all():
    """Load both JSON files on startup"""
    global CHAT_CUSTOM_WORDS, PREMIUM_GROUPS

    # blocked words
    if DATA_FILE.exists():
        try:
            CHAT_CUSTOM_WORDS = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("chats", {})
        except Exception:
            CHAT_CUSTOM_WORDS = {}
    else:
        CHAT_CUSTOM_WORDS = {}

    # premium groups
    if PREMIUM_FILE.exists():
        try:
            PREMIUM_GROUPS = json.loads(PREMIUM_FILE.read_text(encoding="utf-8")).get("premium_groups", {})
        except Exception:
            PREMIUM_GROUPS = {}
    else:
        PREMIUM_GROUPS = {}

def save_words():
    DATA_FILE.write_text(
        json.dumps({"chats": CHAT_CUSTOM_WORDS}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def save_premium():
    PREMIUM_FILE.write_text(
        json.dumps({"premium_groups": PREMIUM_GROUPS}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def is_premium(chat_id: int) -> bool:
    cid = str(chat_id)
    return cid in PREMIUM_GROUPS and PREMIUM_GROUPS[cid].get("active", False)

# ================== TEXT FILTER ==================

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"(.)\1{2,}", r"\1\1", text)

def get_all_blocked(chat_id: int):
    blocked = set(DEFAULT_BLOCKED_WORDS)
    custom = CHAT_CUSTOM_WORDS.get(str(chat_id), [])
    blocked.update(custom)

    # Premium gets extra aggressive words
    if is_premium(chat_id):
        blocked.update({"asu", "bangke", "kampang", "pukimak"})

    return blocked

def contains_blocked_word(text: str, chat_id: int):
    if not text:
        return False

    norm = normalize_text(text)
    tokens = norm.split()
    blocked = get_all_blocked(chat_id)

    for t in tokens:
        for bad in blocked:
            if bad in t:
                return True

    for bad in blocked:
        if bad in norm:
            return True

    return False

# ================== COMMAND HANDLERS ==================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    # Grup → simple info
    if chat.type != chat.PRIVATE:
        return await update.message.reply_text(
            "👋 Bot filter kata kasar aktif di grup ini.\n"
            "Pesan mengandung kata kasar otomatis dihapus."
        )

    # Private → halaman jualan premium
    text = (
        "👋 Halo!\n\n"
        "Aku bot *filter kata kasar* khusus buat grup Telegram.\n\n"
        "🧹 **Cara pakai (GRATIS):**\n"
        "• Tinggal *add aku ke grup kamu* lalu jadikan admin (izin hapus pesan).\n"
        "• Semua fitur dasar bisa dipakai gratis tanpa batas.\n"
        "• Admin grup bisa tambah kata custom: /addword, /delword, /listword.\n\n"
        "✨ **Mode Premium (Rp 5.000 / bulan / grup):**\n"
        "• Filter lebih bersih & agresif\n"
        "• Pengaturan lebih fleksibel\n"
        "• Mode clean tanpa bloatware\n\n"
        "💸 Mau upgrade ke premium?\n"
        "👉 Chat aja: @VanzzSkyyID"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def addword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message

    if chat.type == "private":
        return await msg.reply_text("Command ini hanya untuk grup.")

    user = update.effective_user
    member = await context.bot.get_chat_member(chat.id, user.id)

    if member.status not in ("administrator", "creator"):
        return await msg.reply_text("❌ Hanya admin yang bisa menambah kata.")

    if not context.args:
        return await msg.reply_text("Usage: `/addword kata_kasar`", parse_mode="Markdown")

    word = re.sub(r"[^a-z0-9]", "", " ".join(context.args).lower())
    if not word:
        return await msg.reply_text("❌ Kata tidak valid.")

    cid = str(chat.id)
    custom = CHAT_CUSTOM_WORDS.get(cid, [])
    if word not in custom:
        custom.append(word)
        CHAT_CUSTOM_WORDS[cid] = custom
        save_words()

    reply = f"✅ Kata `{word}` ditambahkan."
    if is_premium(chat.id):
        reply += f"\n✨ {CREDIT}"

    await msg.reply_text(reply, parse_mode="Markdown")

async def delword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message

    cid = str(chat.id)
    if cid not in CHAT_CUSTOM_WORDS:
        return await msg.reply_text("📭 Belum ada kata custom.")

    if not context.args:
        return await msg.reply_text("Usage: `/delword kata_kasar`", parse_mode="Markdown")

    word = re.sub(r"[^a-z0-9]", "", " ".join(context.args).lower())
    if word in CHAT_CUSTOM_WORDS[cid]:
        CHAT_CUSTOM_WORDS[cid].remove(word)
        save_words()
        return await msg.reply_text(f"🗑 Kata `{word}` dihapus.", parse_mode="Markdown")

    await msg.reply_text("❌ Kata tidak ada di list custom.")

async def listword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    words = CHAT_CUSTOM_WORDS.get(cid, [])

    if not words:
        return await update.message.reply_text("📭 Belum ada kata custom.")

    text = "📃 *Daftar kata custom:*\n`" + ", ".join(words) + "`"
    await update.message.reply_text(text, parse_mode="Markdown")

# ================== PREMIUM COMMANDS ==================

BOT_OWNER_ID = 6593622247  # <===== GANTI dengan User ID Telegram lu

async def premium_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message

    if user.id != BOT_OWNER_ID:
        return await msg.reply_text("❌ Lu bukan owner bot.")

    if not context.args:
        return await msg.reply_text("Usage: `/premium_add <group_id>`")

    gid = context.args[0]
    PREMIUM_GROUPS[gid] = {"active": True}
    save_premium()

    await msg.reply_text(
        f"✨ Grup `{gid}` sekarang PREMIUM!\n{CREDIT}",
        parse_mode="Markdown"
    )

async def premium_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message

    if user.id != BOT_OWNER_ID:
        return await msg.reply_text("❌ Lu bukan owner bot.")

    if not context.args:
        return await msg.reply_text("Usage: `/premium_remove <group_id>`")

    gid = context.args[0]
    PREMIUM_GROUPS.pop(gid, None)
    save_premium()

    await msg.reply_text(f"⛔ Premium dicabut dari grup `{gid}`.")

async def premium_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id

    if is_premium(cid):
        await update.message.reply_text(
            f"✨ Grup ini *PREMIUM*\n{CREDIT}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Grup ini belum premium.")

# ================== TEXT FILTER HANDLER ==================

async def text_filter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = update.effective_chat

    if not msg or not msg.text:
        return

    if not contains_blocked_word(msg.text, chat.id):
        return

    # Try delete
    try:
        await msg.delete()
        deleted = True
    except:
        deleted = False

    # ALWAYS show info
    if deleted:
        if is_premium(chat.id):
            info = "🧹 Pesan *kata kasar* telah dihapus (mode premium)."
        else:
            info = "🧹 Pesan *kata kasar* telah dihapus."
    else:
        info = "❗ Pesan kata kasar terdeteksi, tapi bot tidak punya izin hapus."

    await context.bot.send_message(
        chat_id=chat.id,
        text=info,
        parse_mode="Markdown"
    )

# ================== MAIN ==================

def main():
    load_all()
    print("BOT READY")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Public cmds
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("addword", addword_cmd))
    app.add_handler(CommandHandler("delword", delword_cmd))
    app.add_handler(CommandHandler("listword", listword_cmd))

    # Premium cmds
    app.add_handler(CommandHandler("premium_add", premium_add))
    app.add_handler(CommandHandler("premium_remove", premium_remove))
    app.add_handler(CommandHandler("premium_status", premium_status))

    # Text filter
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_filter_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
