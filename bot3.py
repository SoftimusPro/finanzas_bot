import os
import json
import logging
from pathlib import Path
from datetime import datetime

from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, Bot
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)

# =============================
# CONFIGURACIÓN INICIAL
# =============================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8443))
bot = Bot(token=TOKEN)

DB_FILE = Path(__file__).parent / "finanzas.json"

# =============================
# ESTADOS
# =============================
(
    SELECT_INGRESO_CAT, INGRESO_OTRO, INGRESO_MONTO,
    SELECT_GASTO_CAT, SELECT_PRODUCTO_GASTO, GASTO_MANUAL,
    PRODUCTO_OPCION, PRODUCTO_CATEGORIA, PRODUCTO_NUEVO,
    PRODUCTO_ELIMINAR, PRODUCTO_ACTUALIZAR, PRODUCTO_ACTUALIZAR_PRECIO,
    CONFIG_OPCION
) = range(13)

# =============================
# TECLADOS
# =============================
main_keyboard = ReplyKeyboardMarkup(
    [["➕ Ingreso", "➖ Gasto"], ["📦 Productos", "⚙️ Configuración"]],
    resize_keyboard=True
)

CATEGORIAS_INGRESO = ["💼 Salario", "💰 Extra", "🎯 Otro"]
categorias_ingreso_keyboard = ReplyKeyboardMarkup(
    [[c] for c in CATEGORIAS_INGRESO] + [["🔙 Menú principal"]],
    resize_keyboard=True
)

CATEGORIAS_GASTO_DEFAULT = ["🍔 Comida", "🎁 Regalos", "🚕 Transporte", "⚠️ Emergencia",
                            "🏠 Hogar", "🎮 Ocio", "📚 Educación", "💊 Salud", "📦 Otros"]
categorias_gasto_keyboard = ReplyKeyboardMarkup(
    [[c] for c in CATEGORIAS_GASTO_DEFAULT] + [["🔙 Menú principal"]],
    resize_keyboard=True
)

productos_keyboard = ReplyKeyboardMarkup(
    [["Agregar Producto", "Eliminar Producto", "Actualizar Producto"], ["Ver Productos"], ["🔙 Menú principal"]],
    resize_keyboard=True
)

config_keyboard = ReplyKeyboardMarkup(
    [["💸 Establecer presupuesto", "⏰ Recordatorios", "➕ Agregar categoría"], ["📊 Resumen financiero"], ["🔙 Menú principal"]],
    resize_keyboard=True
)

# =============================
# BASE DE DATOS
# =============================
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

    if "ingresos" not in user:
        user["ingresos"] = []
    if "gastos" not in user:
        user["gastos"] = []
    if "productos" not in user:
        user["productos"] = {}
    if "categorias_gasto" not in user:
        user["categorias_gasto"] = CATEGORIAS_GASTO_DEFAULT.copy()
    if "presupuestos" not in user:
        user["presupuestos"] = {}
    if "recordatorio" not in user:
        user["recordatorio"] = {"activo": False, "hora": "20:00"}

    return user

def saldo_actual(user):
    total_ingresos = sum(i['monto'] for i in user.get('ingresos', []))
    total_gastos = sum(g['monto'] for g in user.get('gastos', []))
    return total_ingresos - total_gastos

def fmt_cup(value: float) -> str:
    s = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s} CUP"

# =============================
# HANDLERS
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Qué bolá, mi hermano. Usa los botones para navegar:",
        reply_markup=main_keyboard
    )

# -----------------------------
# INGRESOS
# -----------------------------
async def ingreso_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Selecciona la categoría del ingreso:", reply_markup=categorias_ingreso_keyboard)
    return SELECT_INGRESO_CAT

async def ingreso_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Menú principal":
        await update.message.reply_text("Volvemos al menú principal.", reply_markup=main_keyboard)
        return ConversationHandler.END
    if text == "🎯 Otro":
        await update.message.reply_text("Escribe el nombre de la categoría:")
        return INGRESO_OTRO
    else:
        context.user_data['categoria_ingreso'] = text
        await update.message.reply_text("Ahora escribe el monto del ingreso:")
        return INGRESO_MONTO

async def ingreso_otro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categoria = update.message.text.strip()
    context.user_data['categoria_ingreso'] = categoria
    await update.message.reply_text(f"Categoría registrada: {categoria}. Ahora escribe el monto del ingreso:")
    return INGRESO_MONTO

async def ingreso_monto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    try:
        monto = float(update.message.text)
        categoria = context.user_data.get('categoria_ingreso', 'Otro')
        user['ingresos'].append({
            "monto": monto,
            "categoria": categoria,
            "fecha": datetime.now().isoformat()
        })
        _db_save(db)
        await update.message.reply_text(f"✅ Ingreso registrado: {fmt_cup(monto)} en '{categoria}'", reply_markup=main_keyboard)
    except ValueError:
        await update.message.reply_text("⚠️ Monto inválido. Debe ser un número (ej: 150 o 75.50).", reply_markup=main_keyboard)
    return ConversationHandler.END

# -----------------------------
# GASTOS
# -----------------------------
async def gasto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    if not user['categorias_gasto']:
        user['categorias_gasto'] = CATEGORIAS_GASTO_DEFAULT.copy()
    keyboard = ReplyKeyboardMarkup([[c] for c in user['categorias_gasto']] + [["🔙 Menú principal"]], resize_keyboard=True)
    await update.message.reply_text("Selecciona la categoría del gasto:", reply_markup=keyboard)
    return SELECT_GASTO_CAT

async def gasto_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Menú principal":
        await update.message.reply_text("Volvemos al menú principal.", reply_markup=main_keyboard)
        return ConversationHandler.END

    context.user_data['gasto_categoria'] = text
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    categoria_productos = user['productos'].get(text, {})

    if categoria_productos:
        keyboard = [[InlineKeyboardButton(p, callback_data=p)] for p in categoria_productos.keys()]
        keyboard.append([InlineKeyboardButton("➕ Agregar producto nuevo", callback_data="nuevo")])
        keyboard.append([InlineKeyboardButton("🔙 Menú principal", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Selecciona el producto:", reply_markup=reply_markup)
        return SELECT_PRODUCTO_GASTO
    else:
        await update.message.reply_text("No hay productos en esta categoría. Puedes escribir el monto manualmente o agregar un producto nuevo:")
        return GASTO_MANUAL

async def gasto_producto_seleccion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db = _db_load()
    user = _get_user(db, query.from_user.id)

    if query.data == "cancel":
        await query.message.reply_text("Has vuelto al menú principal ✅", reply_markup=main_keyboard)
        return ConversationHandler.END
    elif query.data == "nuevo":
        await query.message.reply_text("Escribe el nombre del nuevo producto y su precio separado por coma (Ej: Arroz, 50):")
        return GASTO_MANUAL
    else:
        producto = query.data
        precio = user['productos'][context.user_data['gasto_categoria']][producto]
        saldo = saldo_actual(user)
        if saldo < precio:
            await query.message.reply_text(f"⚠️ Saldo insuficiente: {fmt_cup(saldo)}. No se puede gastar {fmt_cup(precio)}.", reply_markup=main_keyboard)
            return ConversationHandler.END
        user['gastos'].append({"monto": precio, "categoria": context.user_data['gasto_categoria'], "producto": producto, "fecha": datetime.now().isoformat()})
        _db_save(db)
        await query.message.reply_text(f"✅ Gasto registrado: {producto} {fmt_cup(precio)}", reply_markup=main_keyboard)
        return ConversationHandler.END

async def gasto_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    try:
        if "," in text:
            producto, precio = text.split(",")
            producto = producto.strip()
            precio = float(precio.strip())
            cat = context.user_data.get('gasto_categoria', "Otros")
            if cat not in user['productos']:
                user['productos'][cat] = {}
            user['productos'][cat][producto] = precio
            user['gastos'].append({"monto": precio, "categoria": cat, "producto": producto, "fecha": datetime.now().isoformat()})
            _db_save(db)
            await update.message.reply_text(f"✅ Producto '{producto}' agregado y gasto registrado: {fmt_cup(precio)}", reply_markup=main_keyboard)
        else:
            monto = float(text)
            cat = context.user_data.get('gasto_categoria', "Otros")
            user['gastos'].append({"monto": monto, "categoria": cat, "producto": None, "fecha": datetime.now().isoformat()})
            _db_save(db)
            await update.message.reply_text(f"✅ Gasto registrado: {fmt_cup(monto)}", reply_markup=main_keyboard)
    except ValueError:
        await update.message.reply_text("⚠️ Entrada inválida, intenta de nuevo.", reply_markup=main_keyboard)
    return ConversationHandler.END

# -----------------------------
# PRODUCTOS
# -----------------------------
async def productos_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Opciones de productos:", reply_markup=productos_keyboard)
    return PRODUCTO_OPCION

async def productos_opcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Menú principal":
        await update.message.reply_text("Volviendo al menú principal.", reply_markup=main_keyboard)
        return ConversationHandler.END
    elif text == "Agregar Producto":
        await update.message.reply_text("Escribe la categoría del producto a agregar:")
        return PRODUCTO_CATEGORIA
    elif text == "Eliminar Producto":
        await update.message.reply_text("Escribe la categoría del producto a eliminar:")
        return PRODUCTO_ELIMINAR
    elif text == "Actualizar Producto":
        await update.message.reply_text("Escribe la categoría del producto a actualizar:")
        return PRODUCTO_ACTUALIZAR
    elif text == "Ver Productos":
        db = _db_load()
        user = _get_user(db, update.effective_user.id)
        msg = "📦 Productos:\n"
        for cat, prods in user['productos'].items():
            msg += f"\n*{cat}*:\n"
            for p, v in prods.items():
                msg += f"  - {p}: {fmt_cup(v)}\n"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=productos_keyboard)
        return PRODUCTO_OPCION
    else:
        await update.message.reply_text("Opción no válida.", reply_markup=productos_keyboard)
        return PRODUCTO_OPCION

async def producto_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categoria = update.message.text.strip()
    context.user_data['producto_categoria'] = categoria
    await update.message.reply_text("Ahora escribe el nombre del producto y su precio separado por coma (Ej: Arroz, 50):")
    return PRODUCTO_NUEVO

async def producto_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    try:
        producto, precio = update.message.text.split(",")
        producto = producto.strip()
        precio = float(precio.strip())
        cat = context.user_data.get('producto_categoria', 'Otros')
        if cat not in user['productos']:
            user['productos'][cat] = {}
        user['productos'][cat][producto] = precio
        _db_save(db)
        await update.message.reply_text(f"✅ Producto '{producto}' agregado con precio {fmt_cup(precio)}", reply_markup=productos_keyboard)
    except ValueError:
        await update.message.reply_text("⚠️ Formato inválido, intenta de nuevo.", reply_markup=productos_keyboard)
    return PRODUCTO_OPCION

async def producto_eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    cat = update.message.text.strip()
    if cat in user['productos'] and user['productos'][cat]:
        msg = "Escribe el nombre del producto a eliminar:\n" + ", ".join(user['productos'][cat].keys())
        context.user_data['producto_categoria'] = cat
        await update.message.reply_text(msg)
        return PRODUCTO_ELIMINAR
    else:
        await update.message.reply_text("Categoría vacía o no existe.", reply_markup=productos_keyboard)
        return PRODUCTO_OPCION

async def producto_actualizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    cat = update.message.text.strip()
    if cat in user['productos'] and user['productos'][cat]:
        msg = "Escribe el nombre del producto a actualizar:\n" + ", ".join(user['productos'][cat].keys())
        context.user_data['producto_categoria'] = cat
        await update.message.reply_text(msg)
        return PRODUCTO_ACTUALIZAR_PRECIO
    else:
        await update.message.reply_text("Categoría vacía o no existe.", reply_markup=productos_keyboard)
        return PRODUCTO_OPCION

async def producto_actualizar_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    cat = context.user_data.get('producto_categoria', 'Otros')
    try:
        producto, precio = update.message.text.split(",")
        producto = producto.strip()
        precio = float(precio.strip())
        if cat in user['productos'] and producto in user['productos'][cat]:
            user['productos'][cat][producto] = precio
            _db_save(db)
            await update.message.reply_text(f"✅ Producto '{producto}' actualizado a {fmt_cup(precio)}", reply_markup=productos_keyboard)
        else:
            await update.message.reply_text("Producto no encontrado.", reply_markup=productos_keyboard)
    except ValueError:
        await update.message.reply_text("⚠️ Formato inválido, intenta de nuevo.", reply_markup=productos_keyboard)
    return PRODUCTO_OPCION

# -----------------------------
# CONFIGURACIÓN
# -----------------------------
async def config_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Opciones de configuración:", reply_markup=config_keyboard)
    return CONFIG_OPCION

async def config_opcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    db = _db_load()
    user = _get_user(db, update.effective_user.id)

    if text == "🔙 Menú principal":
        await update.message.reply_text("Volviendo al menú principal.", reply_markup=main_keyboard)
        return ConversationHandler.END
    elif text == "➕ Agregar categoría":
        await update.message.reply_text("Escribe el nombre de la nueva categoría de gasto:")
        return CONFIG_OPCION
    elif text == "📊 Resumen financiero":
        total_ingresos = sum(i['monto'] for i in user['ingresos'])
        total_gastos = sum(g['monto'] for g in user['gastos'])
        saldo = total_ingresos - total_gastos
        msg = (f"📊 *Resumen Financiero*\n\n"
               f"Ingresos: {fmt_cup(total_ingresos)}\n"
               f"Gastos: {fmt_cup(total_gastos)}\n"
               f"Saldo: {fmt_cup(saldo)}")
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard)
        return ConversationHandler.END
    else:
        categoria = text.strip()
        if categoria not in user['categorias_gasto']:
            user['categorias_gasto'].append(categoria)
            _db_save(db)
            await update.message.reply_text(f"✅ Categoría '{categoria}' agregada.", reply_markup=config_keyboard)
        else:
            await update.message.reply_text("⚠️ La categoría ya existe.", reply_markup=config_keyboard)
        return CONFIG_OPCION

# =============================
# MAIN
# =============================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_ingreso = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("➕ Ingreso"), ingreso_start)],
        states={
            SELECT_INGRESO_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingreso_categoria)],
            INGRESO_OTRO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingreso_otro)],
            INGRESO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingreso_monto)]
        },
        fallbacks=[MessageHandler(filters.Regex("🔙 Menú principal"), lambda u,c: ConversationHandler.END)]
    )

    conv_gasto = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("➖ Gasto"), gasto_start)],
        states={
            SELECT_GASTO_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_categoria)],
            SELECT_PRODUCTO_GASTO: [CallbackQueryHandler(gasto_producto_seleccion)],
            GASTO_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_manual)]
        },
        fallbacks=[MessageHandler(filters.Regex("🔙 Menú principal"), lambda u,c: ConversationHandler.END)]
    )

    conv_producto = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("📦 Productos"), productos_start)],
        states={
            PRODUCTO_OPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, productos_opcion)],
            PRODUCTO_CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, producto_categoria)],
            PRODUCTO_NUEVO: [MessageHandler(filters.TEXT & ~filters.COMMAND, producto_nuevo)],
            PRODUCTO_ELIMINAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, producto_eliminar)],
            PRODUCTO_ACTUALIZAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, producto_actualizar)],
            PRODUCTO_ACTUALIZAR_PRECIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, producto_actualizar_precio)]
        },
        fallbacks=[MessageHandler(filters.Regex("🔙 Menú principal"), lambda u,c: ConversationHandler.END)]
    )

    conv_config = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("⚙️ Configuración"), config_start)],
        states={CONFIG_OPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_opcion)]},
        fallbacks=[MessageHandler(filters.Regex("🔙 Menú principal"), lambda u,c: ConversationHandler.END)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_ingreso)
    app.add_handler(conv_gasto)
    app.add_handler(conv_producto)
    app.add_handler(conv_config)

    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/{TOKEN}"
    logger.info(f"Configurando webhook en: {webhook_url}")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=webhook_url
    )

if __name__ == "__main__":
    main()
