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

    if data == "menu_premium":
        text = (
            "⭐ *Menu Premium*\n\n"
            "Saat ini fitur premium:\n"
            "- /premstatus → cek status premium grup\n"
            "- Owner bot bisa pakai /addpremium <hari>\n\n"
            "Ke depan bisa ditambah integrasi payment & fitur PRO lainnya."
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
            "- Aktivasi premium (/addpremium)\n"
            "- Manajemen grup & fitur PRO (coming soon)."
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

    # premium
    app.add_handler(CommandHandler("addpremium", addpremium_cmd))
    app.add_handler(CommandHandler("premstatus", premstatus_cmd))

    # menu callback
    app.add_handler(CallbackQueryHandler(menu_callback))

    # watchdog: anti toxic + anti spam
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_watchdog))

    logger.info("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
