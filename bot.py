from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler, JobQueue
)
import json
from pathlib import Path
from datetime import datetime, time
import matplotlib.pyplot as plt
import seaborn as sns
import io
import logging
import signal
import pickle
import os

# Configuración inicial
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "8433317544:AAF03S8ysvqf6_DwwgRiznZ5kafh4HL3Snw"
DB_FILE = Path(__file__).parent / "finanzas.json"
STATE_FILE = Path(__file__).parent / "conversation_states.pkl"

# =============================
# ESTADOS
# =============================
SELECT_INGRESO_CAT, INGRESO_OTRO, INGRESO_MONTO = range(3)
SELECT_GASTO_CAT, SELECT_PRODUCTO_GASTO, GASTO_MANUAL = range(3,6)
PRODUCTO_OPCION, PRODUCTO_NUEVO, PRODUCTO_ELIMINAR, PRODUCTO_ACTUALIZAR, PRODUCTO_ACTUALIZAR_PRECIO = range(6,11)
RESUMEN_OPCION = 11
SET_BUDGET_CAT, SET_BUDGET_AMOUNT = range(12,14)

# =============================
# TECLADOS
# =============================
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
    [["Resumen de gastos", "Resumen de ingresos"], 
     ["Resumen general", "Gráfico", "Análisis de hábitos"],
     ["Exportar datos", "🔙 Menú principal"]],
    resize_keyboard=True
)

config_keyboard = ReplyKeyboardMarkup(
    [["💸 Establecer presupuesto", "⏰ Recordatorios"], ["🔙 Menú principal"]],
    resize_keyboard=True
)

# =============================
# DB
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
    
    # Inicializar estructuras si no existen
    if "ingresos" not in user:
        user["ingresos"] = []
    if "gastos" not in user:
        user["gastos"] = []
    if "productos" not in user:
        user["productos"] = {}
    if "presupuestos" not in user:
        user["presupuestos"] = {}
    if "recordatorio" not in user:
        user["recordatorio"] = {"activo": False, "hora": "20:00"}
    
    return user

def saldo_actual(user):
    total_ingresos = sum(i['monto'] for i in user.get('ingresos', []))
    total_gastos = sum(g['monto'] for g in user.get('gastos', []))
    return total_ingresos - total_gastos

# =============================
# FORMATO
# =============================
def fmt_cup(value: float) -> str:
    s = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s} CUP"

# =============================
# START
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Qué bolá, mi hermano. Usa los botones para navegar:", reply_markup=main_keyboard)

# =============================
# INGRESOS
# =============================
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
        await update.message.reply_text(
            f"✅ Ingreso registrado: {fmt_cup(monto)} en '{categoria}'", 
            reply_markup=main_keyboard
        )
    except ValueError:
        await update.message.reply_text("⚠️ Monto inválido. Debe ser un número (ej: 150 o 75.50).", reply_markup=main_keyboard)
    except Exception as e:
        logger.error(f"Error en ingreso_monto: {e}")
        await update.message.reply_text("😵‍💫 Error inesperado. Intenta nuevamente.", reply_markup=main_keyboard)
    return ConversationHandler.END

# =============================
# GASTOS
# =============================
async def gasto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Selecciona la categoría del gasto:", reply_markup=categorias_gasto_keyboard)
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
    data = _db_load()
    user = _get_user(data, query.from_user.id)

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
            await query.message.reply_text(
                f"⚠️ Saldo insuficiente: {fmt_cup(saldo)}\nNo puedes registrar este gasto de {fmt_cup(precio)}", 
                reply_markup=main_keyboard
            )
            return ConversationHandler.END
        
        user['gastos'].append({
            "monto": precio, 
            "categoria": context.user_data['gasto_categoria'], 
            "producto": producto, 
            "fecha": datetime.now().isoformat()
        })
        _db_save(data)
        await query.message.reply_text(
            f"💸 Gasto registrado: {producto} - {fmt_cup(precio)}", 
            reply_markup=main_keyboard
        )
        return ConversationHandler.END

async def gasto_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    categoria = context.user_data.get('gasto_categoria')
    try:
        if "," in update.message.text:
            nombre, monto = map(str.strip, update.message.text.split(","))
            monto = float(monto)
            if categoria not in user['productos']:
                user['productos'][categoria] = {}
            user['productos'][categoria][nombre] = monto
            await update.message.reply_text(f"✅ Producto '{nombre}' agregado automáticamente a {fmt_cup(monto)} en '{categoria}'")
        else:
            monto = float(update.message.text)

        saldo = saldo_actual(user)
        if saldo < monto:
            await update.message.reply_text(
                f"⚠️ Saldo insuficiente: {fmt_cup(saldo)}\nNo puedes registrar este gasto de {fmt_cup(monto)}.", 
                reply_markup=main_keyboard
            )
            return ConversationHandler.END

        user['gastos'].append({
            "monto": monto, 
            "categoria": categoria, 
            "fecha": datetime.now().isoformat()
        })
        _db_save(db)
        await update.message.reply_text(f"💸 Gasto registrado: {fmt_cup(monto)} en '{categoria}'", reply_markup=main_keyboard)
    except ValueError:
        await update.message.reply_text("⚠️ Formato inválido. Usa 'nombre, monto' o solo 'monto' (ej: Arroz, 50 o 75.50).", reply_markup=main_keyboard)
    except Exception as e:
        logger.error(f"Error en gasto_manual: {e}")
        await update.message.reply_text("😵‍💫 Error inesperado. Intenta nuevamente.", reply_markup=main_keyboard)
    return ConversationHandler.END

# =============================
# PRODUCTOS
# =============================
async def productos_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📦 Gestión de productos:", reply_markup=productos_keyboard)
    return PRODUCTO_OPCION

async def productos_opcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    db = _db_load()
    user = _get_user(db, update.effective_user.id)

    if text == "🔙 Menú principal":
        await update.message.reply_text("Volvemos al menú principal.", reply_markup=main_keyboard)
        return ConversationHandler.END
    elif text == "Agregar Producto":
        await update.message.reply_text("Escribe el nombre del producto y precio separados por coma (Ej: Arroz, 50):")
        return PRODUCTO_NUEVO
    elif text == "Eliminar Producto":
        productos = [(cat,p) for cat in user['productos'] for p in user['productos'][cat]]
        if not productos:
            await update.message.reply_text("No tienes productos para eliminar.", reply_markup=productos_keyboard)
            return PRODUCTO_OPCION
        keyboard = [[InlineKeyboardButton(f"{c}: {p}", callback_data=f"{c}|{p}")] for c,p in productos]
        keyboard.append([InlineKeyboardButton("🔙 Menú principal", callback_data="cancel")])
        await update.message.reply_text("Selecciona el producto a eliminar:", reply_markup=InlineKeyboardMarkup(keyboard))
        return PRODUCTO_ELIMINAR
    elif text == "Actualizar Producto":
        productos = [(cat,p) for cat in user['productos'] for p in user['productos'][cat]]
        if not productos:
            await update.message.reply_text("No tienes productos para actualizar.", reply_markup=productos_keyboard)
            return PRODUCTO_OPCION
        keyboard = [[InlineKeyboardButton(f"{c}: {p}", callback_data=f"{c}|{p}")] for c,p in productos]
        keyboard.append([InlineKeyboardButton("🔙 Menú principal", callback_data="cancel")])
        await update.message.reply_text("Selecciona el producto a actualizar:", reply_markup=InlineKeyboardMarkup(keyboard))
        return PRODUCTO_ACTUALIZAR
    elif text == "Ver Productos":
        msg = "📦 Productos guardados:\n"
        for cat, prods in user['productos'].items():
            for p, val in prods.items():
                msg += f"- {cat} → {p}: {fmt_cup(val)}\n"
        if not user['productos']:
            msg += "No tienes productos registrados aún."
        await update.message.reply_text(msg, reply_markup=productos_keyboard)
        return PRODUCTO_OPCION
    else:
        await update.message.reply_text("Opción no válida", reply_markup=productos_keyboard)
        return PRODUCTO_OPCION

async def agregar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    try:
        if "," not in update.message.text:
            raise ValueError("Formato incorrecto")
            
        nombre, precio = map(str.strip, update.message.text.split(","))
        precio = float(precio)
        categoria = "📦 Otros"  # Categoría por defecto
        if categoria not in user['productos']:
            user['productos'][categoria] = {}
        user['productos'][categoria][nombre] = precio
        _db_save(db)
        await update.message.reply_text(f"✅ Producto '{nombre}' agregado a {fmt_cup(precio)} en '{categoria}'", reply_markup=productos_keyboard)
    except ValueError:
        await update.message.reply_text("⚠️ Formato inválido. Usa 'nombre, precio' (ej: Arroz, 50)", reply_markup=productos_keyboard)
    except Exception as e:
        logger.error(f"Error en agregar_producto: {e}")
        await update.message.reply_text("😵‍💫 Error inesperado. Intenta nuevamente.", reply_markup=productos_keyboard)
    return PRODUCTO_OPCION

async def eliminar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.message.reply_text("Operación cancelada.", reply_markup=productos_keyboard)
        return PRODUCTO_OPCION
    
    try:
        categoria, producto = query.data.split("|")
        db = _db_load()
        user = _get_user(db, query.from_user.id)
        
        if categoria in user['productos'] and producto in user['productos'][categoria]:
            del user['productos'][categoria][producto]
            # Eliminar categoría si queda vacía
            if not user['productos'][categoria]:
                del user['productos'][categoria]
            _db_save(db)
            await query.message.reply_text(f"❌ Producto '{producto}' eliminado de '{categoria}'", reply_markup=productos_keyboard)
        else:
            await query.message.reply_text("⚠️ Producto no encontrado", reply_markup=productos_keyboard)
    except Exception as e:
        logger.error(f"Error en eliminar_producto: {e}")
        await query.message.reply_text("😵‍💫 Error al eliminar producto", reply_markup=productos_keyboard)
    
    return PRODUCTO_OPCION

async def actualizar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.message.reply_text("Operación cancelada.", reply_markup=productos_keyboard)
        return PRODUCTO_OPCION
    
    try:
        categoria, producto = query.data.split("|")
        context.user_data['producto_actualizar'] = (categoria, producto)
        await query.message.reply_text(f"Actualizando '{producto}' en '{categoria}'. Escribe el nuevo precio:")
        return PRODUCTO_ACTUALIZAR_PRECIO
    except Exception as e:
        logger.error(f"Error en actualizar_producto: {e}")
        await query.message.reply_text("😵‍💫 Error inesperado", reply_markup=productos_keyboard)
        return PRODUCTO_OPCION

async def guardar_actualizacion_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nuevo_precio = float(update.message.text)
        categoria, producto = context.user_data['producto_actualizar']
        
        db = _db_load()
        user = _get_user(db, update.effective_user.id)
        
        if categoria in user['productos'] and producto in user['productos'][categoria]:
            user['productos'][categoria][producto] = nuevo_precio
            _db_save(db)
            await update.message.reply_text(f"✅ '{producto}' actualizado a {fmt_cup(nuevo_precio)}", reply_markup=productos_keyboard)
        else:
            await update.message.reply_text("❌ Producto no encontrado", reply_markup=productos_keyboard)
    except ValueError:
        await update.message.reply_text("⚠️ Precio inválido. Debe ser un número (ej: 50 o 75.50)", reply_markup=productos_keyboard)
    except Exception as e:
        logger.error(f"Error en guardar_actualizacion_producto: {e}")
        await update.message.reply_text("😵‍💫 Error al actualizar producto", reply_markup=productos_keyboard)
    
    return PRODUCTO_OPCION

# =============================
# RESUMEN
# =============================
async def resumen_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Selecciona el tipo de resumen:", reply_markup=resumen_keyboard)
    return RESUMEN_OPCION

def analisis_habitos(user):
    gastos = user.get('gastos', [])
    if not gastos:
        return None
    
    # Agrupar gastos por día de la semana
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    gastos_por_dia = {dia: 0 for dia in dias}
    
    for gasto in gastos:
        try:
            fecha = datetime.fromisoformat(gasto['fecha'])
            dia_semana = fecha.weekday()
            gastos_por_dia[dias[dia_semana]] += gasto['monto']
        except:
            continue
    
    # Encontrar categoría más frecuente
    categorias = {}
    for gasto in gastos:
        cat = gasto.get('categoria', 'Sin categoría')
        categorias[cat] = categorias.get(cat, 0) + 1
    
    categoria_frecuente = max(categorias, key=categorias.get) if categorias else "Ninguna"
    
    # Encontrar el gasto más común
    productos = {}
    for gasto in gastos:
        prod = gasto.get('producto', 'Sin producto')
        if prod:
            productos[prod] = productos.get(prod, 0) + gasto['monto']
    
    producto_mas_comun = max(productos, key=productos.get) if productos else "Ninguno"
    
    return {
        "gasto_promedio_diario": sum(g['monto'] for g in gastos) / len(gastos),
        "dia_mas_gastos": max(gastos_por_dia, key=gastos_por_dia.get),
        "categoria_frecuente": categoria_frecuente,
        "producto_mas_comun": producto_mas_comun
    }

async def resumen_opcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    db = _db_load()
    user = _get_user(db, update.effective_user.id)
    now = datetime.now()
    
    # Filtrar por mes actual
    def filtrar_mes(item):
        try:
            fecha = datetime.fromisoformat(item['fecha'])
            return fecha.month == now.month and fecha.year == now.year
        except:
            return False
    
    ingresos = [i for i in user.get('ingresos', []) if filtrar_mes(i)]
    gastos = [g for g in user.get('gastos', []) if filtrar_mes(g)]

    if text == "🔙 Menú principal":
        await update.message.reply_text("Volvemos al menú principal.", reply_markup=main_keyboard)
        return ConversationHandler.END

    if text == "Resumen de gastos":
        msg = "📊 Gastos del mes:\n"
        for g in gastos:
            producto = g.get("producto","")
            msg += f"- {g['categoria']}{(' → '+producto) if producto else ''}: {fmt_cup(g['monto'])}\n"
        if not gastos:
            msg += "No hay gastos registrados este mes."
        await update.message.reply_text(msg, reply_markup=resumen_keyboard)

    elif text == "Resumen de ingresos":
        msg = "📊 Ingresos del mes:\n"
        for i in ingresos:
            msg += f"- {i['categoria']}: {fmt_cup(i['monto'])}\n"
        if not ingresos:
            msg += "No hay ingresos registrados este mes."
        await update.message.reply_text(msg, reply_markup=resumen_keyboard)

    elif text == "Resumen general":
        total_ingresos = sum(i['monto'] for i in ingresos)
        total_gastos = sum(g['monto'] for g in gastos)
        detalle_gastos = {}
        for g in gastos:
            cat = g['categoria']
            detalle_gastos[cat] = detalle_gastos.get(cat, 0) + g['monto']
        
        msg = f"📊 Resumen general mes {now.strftime('%B %Y')}\n"
        msg += f"Total Ingresos: {fmt_cup(total_ingresos)}\n"
        msg += f"Total Gastos: {fmt_cup(total_gastos)}\n"
        msg += f"Balance: {fmt_cup(total_ingresos - total_gastos)}\n\n"
        msg += "Gastos por categoría:\n"
        
        for cat, val in detalle_gastos.items():
            # Mostrar porcentaje del presupuesto si existe
            presupuesto = user['presupuestos'].get(cat)
            if presupuesto:
                porcentaje = (val / presupuesto) * 100
                msg += f"- {cat}: {fmt_cup(val)} ({porcentaje:.1f}% del presupuesto)\n"
            else:
                msg += f"- {cat}: {fmt_cup(val)}\n"
        
        await update.message.reply_text(msg, reply_markup=resumen_keyboard)

    elif text == "Gráfico":
        if not ingresos and not gastos:
            await update.message.reply_text("No hay datos para generar el gráfico.", reply_markup=resumen_keyboard)
            return RESUMEN_OPCION
            
        categorias = list({g['categoria'] for g in gastos})
        valores_gastos = [sum(g['monto'] for g in gastos if g['categoria']==c) for c in categorias]
        
        categorias_ingresos = list({i['categoria'] for i in ingresos})
        valores_ingresos = [sum(i['monto'] for i in ingresos if i['categoria']==c) for c in categorias_ingresos]

        plt.figure(figsize=(10, 6))
        sns.set_theme(style="whitegrid")
        
        # Combinar todas las categorías
        todas_categorias = list(set(categorias + categorias_ingresos))
        gastos_por_cat = {cat: sum(g['monto'] for g in gastos if g['categoria'] == cat) for cat in todas_categorias}
        ingresos_por_cat = {cat: sum(i['monto'] for i in ingresos if i['categoria'] == cat) for cat in todas_categorias}
        
        # Crear gráfico de barras
        x = range(len(todas_categorias))
        width = 0.35
        
        plt.bar([i - width/2 for i in x], [gastos_por_cat[cat] for cat in todas_categorias], 
                width, label='Gastos', color='#ff7f7f')
        plt.bar([i + width/2 for i in x], [ingresos_por_cat[cat] for cat in todas_categorias], 
                width, label='Ingresos', color='#7fbf7f')
        
        plt.xlabel('Categorías')
        plt.ylabel('Monto (CUP)')
        plt.title('Ingresos vs Gastos por Categoría')
        plt.xticks(x, todas_categorias, rotation=45, ha='right')
        plt.legend()
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        await update.message.reply_photo(photo=buf, reply_markup=resumen_keyboard)

    elif text == "Análisis de hábitos":
        analisis = analisis_habitos(user)
        if not analisis:
            await update.message.reply_text("No hay suficientes datos para el análisis de hábitos.", reply_markup=resumen_keyboard)
            return RESUMEN_OPCION
            
        msg = "📈 Análisis de hábitos de gastos:\n\n"
        msg += f"• Gasto promedio diario: {fmt_cup(analisis['gasto_promedio_diario'])}\n"
        msg += f"• Día con más gastos: {analisis['dia_mas_gastos']}\n"
        msg += f"• Categoría más frecuente: {analisis['categoria_frecuente']}\n"
        msg += f"• Producto más comprado: {analisis['producto_mas_comun']}\n"
        
        await update.message.reply_text(msg, reply_markup=resumen_keyboard)

    elif text == "Exportar datos":
        # Crear CSV
        csv_content = "Tipo,Categoría,Producto,Monto,Fecha\n"
        for ingreso in user.get('ingresos', []):
            csv_content += f"Ingreso,{ingreso['categoria']},,{ingreso['monto']},{ingreso['fecha']}\n"
        for gasto in user.get('gastos', []):
            producto = gasto.get('producto', '')
            csv_content += f"Gasto,{gasto['categoria']},{producto},{gasto['monto']},{gasto['fecha']}\n"
        
        # Enviar archivo
        with io.BytesIO(csv_content.encode()) as file:
            file.name = f"finanzas_{datetime.now().strftime('%Y%m%d')}.csv"
            await update.message.reply_document(
                document=InputFile(file),
                caption="📤 Aquí tienes tus datos financieros",
                reply_markup=resumen_keyboard
            )

    return RESUMEN_OPCION

# =============================
# CONFIGURACIÓN
# =============================
async def config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ Configuración:", reply_markup=config_keyboard)
    return RESUMEN_OPCION

async def config_opcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🔙 Menú principal":
        await update.message.reply_text("Volvemos al menú principal.", reply_markup=main_keyboard)
        return ConversationHandler.END
    elif text == "💸 Establecer presupuesto":
        await update.message.reply_text(
            "Selecciona la categoría para el presupuesto:", 
            reply_markup=categorias_gasto_keyboard
        )
        return SET_BUDGET_CAT
    elif text == "⏰ Recordatorios":
        db = _db_load()
        user = _get_user(db, update.effective_user.id)
        estado = "✅ ACTIVADO" if user['recordatorio']['activo'] else "❌ DESACTIVADO"
        hora = user['recordatorio']['hora']
        await update.message.reply_text(
            f"Configuración de recordatorios:\n\n"
            f"Estado actual: {estado}\n"
            f"Hora actual: {hora}\n\n"
            "Envía la nueva hora en formato HH:MM (ej: 20:30) o escribe:\n"
            "• 'on' para activar\n"
            "• 'off' para desactivar"
        )
        return RESUMEN_OPCION

async def set_budget_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categoria = update.message.text
    if categoria == "🔙 Menú principal":
        await update.message.reply_text("Volvemos al menú principal.", reply_markup=main_keyboard)
        return ConversationHandler.END
    
    context.user_data['budget_cat'] = categoria
    await update.message.reply_text(f"Escribe el monto del presupuesto para '{categoria}':")
    return SET_BUDGET_AMOUNT

async def set_budget_monto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monto = float(update.message.text)
        categoria = context.user_data['budget_cat']
        
        db = _db_load()
        user = _get_user(db, update.effective_user.id)
        user['presupuestos'][categoria] = monto
        _db_save(db)
        
        await update.message.reply_text(
            f"✅ Presupuesto establecido para '{categoria}': {fmt_cup(monto)}", 
            reply_markup=config_keyboard
        )
    except ValueError:
        await update.message.reply_text("⚠️ Monto inválido. Debe ser un número (ej: 500 o 1200.50)", reply_markup=config_keyboard)
    except Exception as e:
        logger.error(f"Error en set_budget_monto: {e}")
        await update.message.reply_text("😵‍💫 Error al establecer presupuesto", reply_markup=config_keyboard)
    
    return RESUMEN_OPCION

# =============================
# RECORDATORIOS AUTOMÁTICOS
# =============================
async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Ejecutando recordatorio diario")
    db = _db_load()
    
    for user_id, user_data in db["users"].items():
        try:
            if user_data.get('recordatorio', {}).get('activo', False):
                balance = saldo_actual(user_data)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ Recordatorio diario!\n\n"
                         f"Tu saldo actual: {fmt_cup(balance)}\n"
                         f"¡Revisa tus gastos con /resumen!"
                )
        except Exception as e:
            logger.error(f"Error enviando recordatorio a {user_id}: {e}")

# =============================
# MAIN
# =============================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Configurar job de recordatorios
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(
            daily_reminder,
            time=time(20, 0, 0, tzinfo=None),  # 8:00 PM
            name="daily_reminder"
        )
    else:
        logger.warning("JobQueue no está disponible")

    # Handlers
    conv_ingreso = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("➕ Ingreso"), ingreso_start)],
        states={
            SELECT_INGRESO_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingreso_categoria)],
            INGRESO_OTRO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingreso_otro)],
            INGRESO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingreso_monto)],
        },
        fallbacks=[CommandHandler("start", start)],
        map_to_parent={ConversationHandler.END: ConversationHandler.END}
    )

    conv_gasto = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("➖ Gasto"), gasto_start)],
        states={
            SELECT_GASTO_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_categoria)],
            SELECT_PRODUCTO_GASTO: [CallbackQueryHandler(gasto_producto_seleccion)],
            GASTO_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_manual)],
        },
        fallbacks=[CommandHandler("start", start)],
        map_to_parent={ConversationHandler.END: ConversationHandler.END}
    )

    conv_productos = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("📦 Productos"), productos_menu)],
        states={
            PRODUCTO_OPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, productos_opcion)],
            PRODUCTO_NUEVO: [MessageHandler(filters.TEXT & ~filters.COMMAND, agregar_producto)],
            PRODUCTO_ELIMINAR: [CallbackQueryHandler(eliminar_producto)],
            PRODUCTO_ACTUALIZAR: [CallbackQueryHandler(actualizar_producto)],
            PRODUCTO_ACTUALIZAR_PRECIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, guardar_actualizacion_producto)]
        },
        fallbacks=[CommandHandler("start", start)],
        map_to_parent={ConversationHandler.END: ConversationHandler.END}
    )

    conv_resumen = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("📊 Resumen"), resumen_start)],
        states={
            RESUMEN_OPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, resumen_opcion)],
        },
        fallbacks=[CommandHandler("start", start)],
        map_to_parent={ConversationHandler.END: ConversationHandler.END}
    )

    conv_config = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("⚙️ Configuración"), config_menu)],
        states={
            RESUMEN_OPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_opcion)],
            SET_BUDGET_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_budget_categoria)],
            SET_BUDGET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_budget_monto)]
        },
        fallbacks=[CommandHandler("start", start)],
        map_to_parent={ConversationHandler.END: ConversationHandler.END}
    )

    # Añadir todos los handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_ingreso)
    app.add_handler(conv_gasto)
    app.add_handler(conv_productos)
    app.add_handler(conv_resumen)
    app.add_handler(conv_config)

    # Manejar persistencia de estados
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'rb') as f:
                app.persistence = pickle.load(f)
        except Exception as e:
            logger.error(f"Error cargando estados: {e}")

    # Guardar estados al cerrar
    def save_states(signum, frame):
        logger.info("Guardando estados de conversación...")
        try:
            with open(STATE_FILE, 'wb') as f:
                pickle.dump(app.persistence, f)
            logger.info("Estados guardados exitosamente")
        except Exception as e:
            logger.error(f"Error guardando estados: {e}")
        signal.signal(signal.SIGINT, original_sigint)
        exit(0)

    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, save_states)

    print("Bot corriendo…")
    app.run_polling()

if __name__ == "__main__":
    main()
