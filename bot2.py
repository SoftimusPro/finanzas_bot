import os
import json
import io
from pathlib import Path
from datetime import datetime, time
import logging

import matplotlib.pyplot as plt
import seaborn as sns

from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ConversationHandler, CallbackQueryHandler, ContextTypes, PicklePersistence
)

# --------------------
# Configuración básica
# --------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
DB_FILE = Path(__file__).parent / "finanzas.json"
STATE_FILE = Path(__file__).parent / "conversation_states.pkl"

# --------------------
# Estados
# --------------------
SELECT_INGRESO_CAT, INGRESO_OTRO, INGRESO_MONTO = range(3)
SELECT_GASTO_CAT, SELECT_PRODUCTO_GASTO, GASTO_MANUAL = range(3, 6)
PRODUCTO_OPCION, PRODUCTO_NUEVO, PRODUCTO_ELIMINAR, PRODUCTO_ACTUALIZAR, PRODUCTO_ACTUALIZAR_PRECIO = range(6, 11)
RESUMEN_OPCION = 11
SET_BUDGET_CAT, SET_BUDGET_AMOUNT = range(12, 14)

# --------------------
# Teclados
# --------------------
main_keyboard = ReplyKeyboardMarkup(
    [["➕ Ingreso", "➖ Gasto"], ["📦 Productos", "📊 Resumen", "⚙️ Configuración"]],
    resize_keyboard=True
)

CATEGORIAS_INGRESO = ["💼 Salario", "💰 Extra", "🎯 Otro"]
categorias_ingreso_keyboard = ReplyKeyboardMarkup(
    [[c] for c in CATEGORIAS_INGRESO] + [["🔙 Menú principal"]],
    resize_keyboard=True
)

CATEGORIAS_GASTO = ["🍔 Comida", "🎁 Regalos", "🚕 Transporte", "⚠️ Emergencia",
                    "🏠 Hogar", "🎮 Ocio", "📚 Educación", "💊 Salud", "📦 Otros"]
categorias_gasto_keyboard = ReplyKeyboardMarkup(
    [[c] for c in CATEGORIAS_GASTO] + [["🔙 Menú principal"]],
    resize_keyboard=True
)

productos_keyboard = ReplyKeyboardMarkup(
    [["Agregar Producto", "Eliminar Producto", "Actualizar Producto"], ["Ver Productos"], ["🔙 Menú principal"]],
    resize_keyboard=True
)

resumen_keyboard = ReplyKeyboardMarkup(
    [["Resumen de gastos", "Resumen de ingresos"], ["Resumen general", "Gráfico", "Análisis de hábitos"], ["Exportar datos", "🔙 Menú principal"]],
    resize_keyboard=True
)

config_keyboard = ReplyKeyboardMarkup(
    [["💸 Establecer presupuesto", "⏰ Recordatorios"], ["🔙 Menú principal"]],
    resize_keyboard=True
)

# --------------------
# DB
# --------------------
def _db_load():
    if DB_FILE.exists():
        try:
            with DB_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error("Error al cargar DB, creando nueva")
            return {"users": {}}
    return {"users": {}}

def _db_save(db):
    with DB_FILE.open("w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def _get_user(db, user_id):
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {}
    user = db["users"][uid]
    user.setdefault("ingresos", [])
    user.setdefault("gastos", [])
    user.setdefault("productos", {})
    user.setdefault("presupuestos", {})
    user.setdefault("recordatorio", {"activo": False, "hora": "20:00"})
    return user

def saldo_actual(user):
    return sum(i['monto'] for i in user.get('ingresos', [])) - sum(g['monto'] for g in user.get('gastos', []))

def fmt_cup(value: float) -> str:
    s = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s} CUP"

# --------------------
# START
# --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Qué bolá, mi hermano. Usa los botones para navegar:", reply_markup=main_keyboard)

# --------------------
# RECORDATORIOS
# --------------------
async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    db = _db_load()
    for user_id, user_data in db["users"].items():
        try:
            if user_data.get('recordatorio', {}).get('activo', False):
                balance = saldo_actual(user_data)
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"⏰ Recordatorio diario!\n\nTu saldo actual: {fmt_cup(balance)}\n¡Revisa tus gastos con /resumen!"
                )
        except Exception as e:
            logger.error(f"Error enviando recordatorio a {user_id}: {e}")

# --------------------
# MAIN
# --------------------
def main():
    persistence = PicklePersistence(filepath=str(STATE_FILE))
    app = ApplicationBuilder().token(TOKEN).persistence(persistence).build()

    # Comando start
    app.add_handler(CommandHandler("start", start))

    # Configurar job diario
    app.job_queue.run_daily(
        daily_reminder,
        time=time(20, 0, 0),
        name="daily_reminder"
    )

    # Aquí agregas todos los ConversationHandler que ya tienes (ingresos, gastos, productos, resumen, config)
    # ... copiar todo como lo tienes, usando 'async def' handlers y 'await' ...

    logger.info("Bot corriendo…")
    app.run_polling()

if __name__ == "__main__":
    main()
