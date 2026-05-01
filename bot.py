#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🐍 كوبرا - بوت تيليجرام الإداري الكامل
Firebase Realtime Database + Telegram Bot API
"""

import os
import json
import time
import logging
import asyncio
import hashlib
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ─── إعداد اللوج ───
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ─── الإعدادات ───
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8570136394:AAFL3DPXKU3E-P6pGFwKzhG7YKoCqnnKHTI")
ADMIN_PASSWORD = "20262024"

FIREBASE_URL = "https://cobra-cefaa-default-rtdb.firebaseio.com"
FIREBASE_API_KEY = "AIzaSyAqMJzHwqnMPgfKb6LkoBQlFDW8y5XHbmA"

# الباقات
PKGS = {
    "samsung":       {"name": "سامسونج 🥇",      "price": 1200,  "daily": 60,  "refReward": 100},
    "nokia":         {"name": "نوكيا سمارت 🥈",  "price": 3200,  "daily": 160, "refReward": 200},
    "oppo":          {"name": "Oppo 🥉",          "price": 5200,  "daily": 260, "refReward": 400},
    "ultra":         {"name": "Samsung Ultra 🏅", "price": 7200,  "daily": 360, "refReward": 600},
    "iphone":        {"name": "iPhone 💎",        "price": 12000, "daily": 600, "refReward": 1000},
    "iphone_latest": {"name": "iPhone Latest 🔒", "price": 20000, "daily": 0,   "refReward": 2000},
}

# ─── المستخدمون المصادق عليهم ───
authenticated_admins = set()  # chat_ids المصادق عليها
pending_auth = {}             # chat_id -> True (ينتظر كلمة السر)


# ════════════════════════════════════════════
#  Firebase Helpers
# ════════════════════════════════════════════

def fb_get(path: str):
    try:
        r = requests.get(f"{FIREBASE_URL}/{path}.json", timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Firebase GET error [{path}]: {e}")
        return None

def fb_set(path: str, data):
    try:
        r = requests.put(f"{FIREBASE_URL}/{path}.json", json=data, timeout=15)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Firebase SET error [{path}]: {e}")
        return False

def fb_update(path: str, data: dict):
    try:
        r = requests.patch(f"{FIREBASE_URL}/{path}.json", json=data, timeout=15)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Firebase UPDATE error [{path}]: {e}")
        return False

def fb_delete(path: str):
    try:
        r = requests.delete(f"{FIREBASE_URL}/{path}.json", timeout=15)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Firebase DELETE error [{path}]: {e}")
        return False

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def fmt_num(n):
    try:
        return f"{int(n):,}".replace(",", "،")
    except:
        return str(n)


# ════════════════════════════════════════════
#  Auth
# ════════════════════════════════════════════

def is_admin(chat_id: int) -> bool:
    return chat_id in authenticated_admins


# ════════════════════════════════════════════
#  لوحة التحكم الرئيسية
# ════════════════════════════════════════════

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات الكاملة", callback_data="stats")],
        [
            InlineKeyboardButton("📦 طلبات الشراء", callback_data="orders_pending"),
            InlineKeyboardButton("💸 طلبات السحب", callback_data="wd_pending"),
        ],
        [
            InlineKeyboardButton("👥 المستخدمون", callback_data="users_list"),
            InlineKeyboardButton("🎁 الإحالات", callback_data="referrals_pending"),
        ],
        [
            InlineKeyboardButton("🆘 الدعم الفني", callback_data="support_open"),
            InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings_menu"),
        ],
        [InlineKeyboardButton("💰 تعديل رصيد", callback_data="balance_menu")],
        [InlineKeyboardButton("📢 إرسال إشعار جماعي", callback_data="broadcast_menu")],
    ])


async def send_main_menu(update: Update, text: str = None):
    msg = text or "🐍 *لوحة تحكم كوبرا*\nاختر من القائمة أدناه:"
    if update.callback_query:
        await update.callback_query.edit_message_text(
            msg, reply_markup=main_menu_keyboard(), parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            msg, reply_markup=main_menu_keyboard(), parse_mode="Markdown"
        )


# ════════════════════════════════════════════
#  /start
# ════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if is_admin(chat_id):
        await send_main_menu(update, "🐍 *مرحباً بك في لوحة تحكم كوبرا!*")
        return

    pending_auth[chat_id] = True
    await update.message.reply_text(
        "🔐 *بوت كوبرا الإداري*\n\nأدخل كلمة المرور للوصول:",
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════
#  معالجة الرسائل النصية (كلمة السر + قيم)
# ════════════════════════════════════════════

# تخزين حالة الأوامر المعلقة
user_state = {}  # chat_id -> {"action": str, "data": dict}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip() if update.message.text else ""

    # ── Auth ──
    if pending_auth.get(chat_id) and not is_admin(chat_id):
        if text == ADMIN_PASSWORD:
            authenticated_admins.add(chat_id)
            del pending_auth[chat_id]
            await update.message.reply_text("✅ *تم التحقق! مرحباً بك في لوحة التحكم.*", parse_mode="Markdown")
            await send_main_menu(update)
        else:
            await update.message.reply_text("❌ كلمة المرور غير صحيحة. حاول مجدداً:")
        return

    if not is_admin(chat_id):
        pending_auth[chat_id] = True
        await update.message.reply_text("🔐 أدخل كلمة المرور:")
        return

    # ── معالجة الحالات المعلقة ──
    state = user_state.get(chat_id, {})
    action = state.get("action")

    if action == "balance_phone":
        user_state[chat_id] = {"action": "balance_amount", "data": {"phone": text}}
        await update.message.reply_text(f"📱 الهاتف: `{text}`\n\nأدخل المبلغ (سالب للخصم):", parse_mode="Markdown")

    elif action == "balance_amount":
        try:
            amount = float(text)
            phone = state["data"]["phone"]
            user_state[chat_id] = {"action": "balance_reason", "data": {"phone": phone, "amount": amount}}
            await update.message.reply_text(f"💰 المبلغ: *{amount}* جنيه\n\nأدخل سبب التعديل (أو اكتب تخطي):", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ أدخل رقماً صحيحاً:")

    elif action == "balance_reason":
        phone = state["data"]["phone"]
        amount = state["data"]["amount"]
        reason = text if text.lower() != "تخطي" else "تعديل يدوي من الأدمن"
        del user_state[chat_id]
        await do_adjust_balance(update, phone, amount, reason)

    elif action == "broadcast_text":
        del user_state[chat_id]
        await do_broadcast(update, text)

    elif action == "user_search":
        del user_state[chat_id]
        await do_search_user(update, text)

    elif action == "add_balance_direct":
        uid = state["data"]["uid"]
        try:
            amount = float(text)
            del user_state[chat_id]
            await do_adjust_balance_uid(update, uid, amount, "إضافة من الأدمن")
        except:
            await update.message.reply_text("❌ أدخل رقماً:")

    else:
        await send_main_menu(update)


# ════════════════════════════════════════════
#  الإحصائيات
# ════════════════════════════════════════════

async def show_stats(update: Update):
    await update.callback_query.answer("⏳ جاري التحميل...")
    users = fb_get("users") or {}
    orders_all = fb_get("orders") or {}
    withdrawals_all = fb_get("withdrawals") or {}
    referrals_all = fb_get("referrals") or {}
    tickets = fb_get("support_tickets") or {}

    today = datetime.now().strftime("%Y-%m-%d")

    # Flatten orders
    flat_orders = []
    for uid, uorders in orders_all.items():
        if isinstance(uorders, dict):
            for oid, o in uorders.items():
                if isinstance(o, dict):
                    o["_uid"] = uid
                    flat_orders.append(o)

    # Flatten withdrawals
    flat_wd = []
    for uid, uwds in withdrawals_all.items():
        if isinstance(uwds, dict):
            for wid, w in uwds.items():
                if isinstance(w, dict):
                    flat_wd.append(w)

    total_users = len(users)
    today_users = sum(1 for u in users.values() if isinstance(u, dict) and str(u.get("createdAt", ""))[:10] == today)

    approved_orders = [o for o in flat_orders if o.get("status") == "approved"]
    pending_orders = [o for o in flat_orders if o.get("status") == "pending"]
    total_revenue = sum(o.get("amount", 0) for o in approved_orders)
    today_revenue = sum(o.get("amount", 0) for o in approved_orders if str(o.get("createdAt", ""))[:10] == today)

    approved_wd = [w for w in flat_wd if w.get("status") == "approved"]
    pending_wd = [w for w in flat_wd if w.get("status") == "pending"]
    total_wd = sum(w.get("amount", 0) for w in approved_wd)

    # Daily profit
    daily_profit = sum(PKGS.get(u.get("package", ""), {}).get("daily", 0) for u in users.values() if isinstance(u, dict))

    open_tickets = sum(1 for t in tickets.values() if isinstance(t, dict) and t.get("status") == "open")

    # Count referrals
    total_refs = sum(len(v) for v in referrals_all.values() if isinstance(v, dict))

    msg = f"""📊 *إحصائيات كوبرا الشاملة*
🕐 {now_str()}

👥 *المستخدمون*
• الإجمالي: *{fmt_num(total_users)}* مستخدم
• اليوم: *{today_users}* مستخدم جديد

💰 *الإيرادات*
• الإجمالي: *{fmt_num(total_revenue)}* جنيه
• اليوم: *{fmt_num(today_revenue)}* جنيه

📦 *الطلبات*
• معلقة: *{len(pending_orders)}* طلب شراء
• معتمدة: *{len(approved_orders)}* طلب

💸 *السحوبات*
• معلقة: *{len(pending_wd)}* طلب
• مصروفة: *{fmt_num(total_wd)}* جنيه

📈 *الأرباح اليومية للمستثمرين*
• {fmt_num(daily_profit)} جنيه/يوم

🎁 *الإحالات*: {fmt_num(total_refs)} إحالة
🆘 *تذاكر مفتوحة*: {open_tickets}"""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 تحديث", callback_data="stats")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")],
    ])
    await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")


# ════════════════════════════════════════════
#  طلبات الشراء
# ════════════════════════════════════════════

async def show_orders_pending(update: Update):
    await update.callback_query.answer()
    orders_all = fb_get("orders") or {}
    pending = []
    for uid, uorders in orders_all.items():
        if isinstance(uorders, dict):
            for oid, o in uorders.items():
                if isinstance(o, dict) and o.get("status") == "pending":
                    o["_uid"] = uid
                    o["_oid"] = oid
                    pending.append(o)

    pending.sort(key=lambda x: x.get("createdAt", 0), reverse=True)

    if not pending:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]])
        await update.callback_query.edit_message_text("✅ لا توجد طلبات شراء معلقة.", reply_markup=kb)
        return

    msg = f"📦 *طلبات الشراء المعلقة* ({len(pending)})\n\n"
    buttons = []
    for o in pending[:10]:
        pkg_name = PKGS.get(o.get("package", ""), {}).get("name", o.get("package", "?"))
        phone = o.get("phone", o.get("_uid", "?"))
        amount = o.get("amount", 0)
        msg += f"• *{phone}* — {pkg_name} — {fmt_num(amount)} ج\n"
        buttons.append([
            InlineKeyboardButton(f"✅ قبول {phone}", callback_data=f"approve_order_{o['_uid']}_{o['_oid']}"),
            InlineKeyboardButton(f"❌ رفض", callback_data=f"reject_order_{o['_uid']}_{o['_oid']}"),
        ])

    buttons.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")])
    await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def approve_order(update: Update, uid: str, oid: str):
    await update.callback_query.answer("⏳")
    order = fb_get(f"orders/{uid}/{oid}")
    if not order:
        await update.callback_query.answer("❌ الطلب غير موجود!", show_alert=True)
        return

    pkg_key = order.get("package", "")
    pkg = PKGS.get(pkg_key, {})
    amount = order.get("amount", 0)
    daily = pkg.get("daily", 0)

    # تحديث حالة الطلب
    fb_update(f"orders/{uid}/{oid}", {
        "status": "approved",
        "approvedAt": int(time.time() * 1000),
        "approvedBy": "admin_bot"
    })

    # تفعيل الباقة للمستخدم
    fb_update(f"users/{uid}", {
        "package": pkg_key,
        "packageActivatedAt": int(time.time() * 1000),
        "dailyProfit": daily,
    })

    # إضافة إشعار للمستخدم
    fb_set(f"notifications/{uid}/{int(time.time()*1000)}", {
        "type": "order_approved",
        "title": "✅ تم تفعيل باقتك",
        "body": f"تم تفعيل باقة {pkg.get('name', pkg_key)} بنجاح! ستحصل على {fmt_num(daily)} جنيه يومياً.",
        "createdAt": int(time.time() * 1000),
        "read": False
    })

    await update.callback_query.answer("✅ تم قبول الطلب!", show_alert=True)
    await show_orders_pending(update)


async def reject_order(update: Update, uid: str, oid: str):
    fb_update(f"orders/{uid}/{oid}", {"status": "rejected", "rejectedAt": int(time.time() * 1000)})

    fb_set(f"notifications/{uid}/{int(time.time()*1000)}", {
        "type": "order_rejected",
        "title": "❌ تم رفض طلبك",
        "body": "تم رفض طلب الشراء. تواصل مع الدعم لمزيد من المعلومات.",
        "createdAt": int(time.time() * 1000),
        "read": False
    })

    await update.callback_query.answer("❌ تم رفض الطلب", show_alert=True)
    await show_orders_pending(update)


# ════════════════════════════════════════════
#  طلبات السحب
# ════════════════════════════════════════════

async def show_wd_pending(update: Update):
    await update.callback_query.answer()
    wd_all = fb_get("withdrawals") or {}
    pending = []
    for uid, uwds in wd_all.items():
        if isinstance(uwds, dict):
            for wid, w in uwds.items():
                if isinstance(w, dict) and w.get("status") == "pending":
                    w["_uid"] = uid
                    w["_wid"] = wid
                    pending.append(w)

    pending.sort(key=lambda x: x.get("createdAt", 0), reverse=True)

    if not pending:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]])
        await update.callback_query.edit_message_text("✅ لا توجد طلبات سحب معلقة.", reply_markup=kb)
        return

    msg = f"💸 *طلبات السحب المعلقة* ({len(pending)})\n\n"
    buttons = []
    for w in pending[:10]:
        phone = w.get("phone", w.get("_uid", "?"))
        amount = w.get("amount", 0)
        wallet = w.get("walletNumber", "?")
        msg += f"• *{phone}* — {fmt_num(amount)} ج — محفظة: `{wallet}`\n"
        buttons.append([
            InlineKeyboardButton(f"✅ صرف {fmt_num(amount)}ج", callback_data=f"approve_wd_{w['_uid']}_{w['_wid']}"),
            InlineKeyboardButton(f"❌ رفض", callback_data=f"reject_wd_{w['_uid']}_{w['_wid']}"),
        ])

    buttons.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")])
    await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def approve_wd(update: Update, uid: str, wid: str):
    wd = fb_get(f"withdrawals/{uid}/{wid}")
    if not wd:
        await update.callback_query.answer("❌ الطلب غير موجود!", show_alert=True)
        return

    amount = wd.get("amount", 0)

    # خصم المبلغ من الرصيد
    bal_data = fb_get(f"balances/{uid}") or {}
    current_bal = bal_data.get("balance", 0)
    new_bal = max(0, current_bal - amount)
    fb_update(f"balances/{uid}", {"balance": new_bal})

    fb_update(f"withdrawals/{uid}/{wid}", {"status": "approved", "approvedAt": int(time.time() * 1000)})

    fb_set(f"notifications/{uid}/{int(time.time()*1000)}", {
        "type": "withdrawal_approved",
        "title": "✅ تم صرف مبلغك",
        "body": f"تم صرف {fmt_num(amount)} جنيه على محفظتك بنجاح!",
        "createdAt": int(time.time() * 1000),
        "read": False
    })

    await update.callback_query.answer(f"✅ تم صرف {amount} جنيه!", show_alert=True)
    await show_wd_pending(update)


async def reject_wd(update: Update, uid: str, wid: str):
    fb_update(f"withdrawals/{uid}/{wid}", {"status": "rejected", "rejectedAt": int(time.time() * 1000)})

    fb_set(f"notifications/{uid}/{int(time.time()*1000)}", {
        "type": "withdrawal_rejected",
        "title": "❌ تم رفض طلب السحب",
        "body": "تم رفض طلب السحب. تواصل مع الدعم.",
        "createdAt": int(time.time() * 1000),
        "read": False
    })

    await update.callback_query.answer("❌ تم رفض السحب", show_alert=True)
    await show_wd_pending(update)


# ════════════════════════════════════════════
#  المستخدمون
# ════════════════════════════════════════════

async def show_users_list(update: Update):
    await update.callback_query.answer()
    users = fb_get("users") or {}
    total = len(users)
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = sum(1 for u in users.values() if isinstance(u, dict) and str(u.get("createdAt", ""))[:10] == today)

    active = sum(1 for u in users.values() if isinstance(u, dict) and u.get("package"))

    msg = f"""👥 *المستخدمون*

📊 الإجمالي: *{fmt_num(total)}*
✅ لديهم باقة نشطة: *{fmt_num(active)}*
🆕 اليوم: *{today_count}*

اختر إجراء:"""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 بحث عن مستخدم", callback_data="user_search")],
        [InlineKeyboardButton("📋 آخر 10 مستخدمين", callback_data="users_recent")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")],
    ])
    await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")


async def show_users_recent(update: Update):
    await update.callback_query.answer("⏳")
    users = fb_get("users") or {}
    sorted_users = sorted(
        [(uid, u) for uid, u in users.items() if isinstance(u, dict)],
        key=lambda x: x[1].get("createdAt", 0),
        reverse=True
    )[:10]

    msg = "📋 *آخر 10 مستخدمين مسجلين*\n\n"
    for uid, u in sorted_users:
        name = u.get("name", "—")
        phone = u.get("phone", uid)
        pkg = PKGS.get(u.get("package", ""), {}).get("name", "بدون باقة")
        bal = fb_get(f"balances/{uid}") or {}
        balance = bal.get("balance", 0)
        msg += f"• *{name}* | 📱 `{phone}` | {pkg} | 💰 {fmt_num(balance)} ج\n"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")],
    ])
    await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")


async def do_search_user(update: Update, query: str):
    users = fb_get("users") or {}
    results = []
    for uid, u in users.items():
        if not isinstance(u, dict):
            continue
        phone = u.get("phone", "")
        name = u.get("name", "")
        code = u.get("referralCode", "")
        if query in phone or query.lower() in name.lower() or query in code or query in uid:
            results.append((uid, u))

    if not results:
        await update.message.reply_text("❌ لم يتم العثور على مستخدم.")
        return

    uid, u = results[0]
    await show_user_detail_msg(update, uid, u)


async def show_user_detail_msg(update, uid, u):
    name = u.get("name", "—")
    phone = u.get("phone", uid)
    pkg_key = u.get("package", "")
    pkg = PKGS.get(pkg_key, {}).get("name", "بدون باقة")
    ref_code = u.get("referralCode", "—")
    created = str(u.get("createdAt", ""))[:10]

    bal_data = fb_get(f"balances/{uid}") or {}
    balance = bal_data.get("balance", 0)

    # عدد الإحالات
    refs = fb_get(f"referrals/{uid}") or {}
    ref_count = len(refs) if isinstance(refs, dict) else 0

    msg = f"""👤 *بيانات المستخدم*

📛 الاسم: *{name}*
📱 الهاتف: `{phone}`
📦 الباقة: *{pkg}*
💰 الرصيد: *{fmt_num(balance)}* جنيه
🎁 كود الإحالة: `{ref_code}`
👥 إحالاته: *{ref_count}*
📅 تاريخ التسجيل: {created}"""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 تعديل رصيده", callback_data=f"edit_bal_{uid}")],
        [InlineKeyboardButton("🚫 حذف المستخدم", callback_data=f"delete_user_{uid}")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")],
    ])

    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, reply_markup=kb, parse_mode="Markdown")


# ════════════════════════════════════════════
#  الإحالات
# ════════════════════════════════════════════

async def show_referrals_pending(update: Update):
    await update.callback_query.answer()
    referrals_all = fb_get("referrals") or {}
    pending = []
    for uid, refs in referrals_all.items():
        if not isinstance(refs, dict):
            continue
        for rid, r in refs.items():
            if isinstance(r, dict) and not r.get("rewarded") and r.get("package"):
                r["_uid"] = uid
                r["_rid"] = rid
                pending.append(r)

    if not pending:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]])
        await update.callback_query.edit_message_text("✅ لا توجد مكافآت إحالة معلقة.", reply_markup=kb)
        return

    msg = f"🎁 *مكافآت الإحالة المعلقة* ({len(pending)})\n\n"
    buttons = []
    for r in pending[:10]:
        uid = r.get("_uid", "?")
        pkg_key = r.get("package", "")
        reward = PKGS.get(pkg_key, {}).get("refReward", 0)
        users = fb_get("users") or {}
        name = users.get(uid, {}).get("name", uid) if isinstance(users.get(uid, {}), dict) else uid
        msg += f"• *{name}* — {PKGS.get(pkg_key, {}).get('name', pkg_key)} — مكافأة: {fmt_num(reward)} ج\n"
        buttons.append([
            InlineKeyboardButton(f"✅ صرف {fmt_num(reward)}ج لـ{name}", callback_data=f"pay_ref_{uid}_{r['_rid']}"),
        ])

    buttons.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")])
    await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def pay_referral(update: Update, uid: str, rid: str):
    ref = fb_get(f"referrals/{uid}/{rid}")
    if not ref:
        await update.callback_query.answer("❌ غير موجود!", show_alert=True)
        return

    pkg_key = ref.get("package", "")
    reward = PKGS.get(pkg_key, {}).get("refReward", 0)

    bal_data = fb_get(f"balances/{uid}") or {}
    current_bal = bal_data.get("balance", 0)
    fb_update(f"balances/{uid}", {"balance": current_bal + reward})
    fb_update(f"referrals/{uid}/{rid}", {"rewarded": True, "rewardedAt": int(time.time() * 1000)})

    fb_set(f"notifications/{uid}/{int(time.time()*1000)}", {
        "type": "referral_reward",
        "title": "🎁 مكافأة إحالة",
        "body": f"تم إضافة {fmt_num(reward)} جنيه مكافأة إحالة إلى رصيدك!",
        "createdAt": int(time.time() * 1000),
        "read": False
    })

    await update.callback_query.answer(f"✅ تم صرف {reward} جنيه!", show_alert=True)
    await show_referrals_pending(update)


# ════════════════════════════════════════════
#  الدعم الفني
# ════════════════════════════════════════════

async def show_support_open(update: Update):
    await update.callback_query.answer()
    tickets = fb_get("support_tickets") or {}
    open_tickets = [(tid, t) for tid, t in tickets.items() if isinstance(t, dict) and t.get("status") == "open"]

    if not open_tickets:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]])
        await update.callback_query.edit_message_text("✅ لا توجد تذاكر دعم مفتوحة.", reply_markup=kb)
        return

    msg = f"🆘 *تذاكر الدعم المفتوحة* ({len(open_tickets)})\n\n"
    buttons = []
    for tid, t in open_tickets[:10]:
        problem = t.get("problemType", "غير محدد")
        user = t.get("userName", t.get("userPhone", "?"))
        details = str(t.get("details", ""))[:50]
        msg += f"• *{user}* — {problem}\n  {details}...\n"
        buttons.append([
            InlineKeyboardButton(f"✅ إغلاق تذكرة {user}", callback_data=f"close_ticket_{tid}"),
        ])

    buttons.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")])
    await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def close_ticket(update: Update, tid: str):
    fb_update(f"support_tickets/{tid}", {"status": "closed", "closedAt": int(time.time() * 1000)})
    await update.callback_query.answer("✅ تم إغلاق التذكرة", show_alert=True)
    await show_support_open(update)


# ════════════════════════════════════════════
#  الإعدادات
# ════════════════════════════════════════════

async def show_settings_menu(update: Update):
    await update.callback_query.answer()
    settings = fb_get("app_settings") or {}
    payment_method = settings.get("paymentMethod", "—")
    payment_number = settings.get("paymentNumber", "—")
    tg_token = settings.get("telegramBotToken", "—")
    tg_chats = settings.get("telegramChatIds", "—")

    msg = f"""⚙️ *إعدادات كوبرا*

💳 *الدفع*
• الطريقة: {payment_method}
• الرقم: `{payment_number}`

🤖 *تيليجرام*
• التوكن: `{str(tg_token)[:20]}...`
• Chat IDs: `{tg_chats}`"""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إرسال إشعار جماعي", callback_data="broadcast_menu")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")],
    ])
    await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")


# ════════════════════════════════════════════
#  تعديل الرصيد
# ════════════════════════════════════════════

async def show_balance_menu(update: Update):
    await update.callback_query.answer()
    msg = "💰 *تعديل رصيد مستخدم*\n\nأدخل رقم هاتف المستخدم:"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="main_menu")]])
    await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")
    user_state[update.effective_chat.id] = {"action": "balance_phone", "data": {}}


async def do_adjust_balance(update: Update, phone: str, amount: float, reason: str):
    users = fb_get("users") or {}
    uid = None
    for u_id, u_data in users.items():
        if isinstance(u_data, dict) and u_data.get("phone") == phone:
            uid = u_id
            break

    if not uid:
        await update.message.reply_text(f"❌ لم يتم العثور على مستخدم بالهاتف `{phone}`", parse_mode="Markdown")
        return

    await do_adjust_balance_uid(update, uid, amount, reason)


async def do_adjust_balance_uid(update, uid: str, amount: float, reason: str):
    bal_data = fb_get(f"balances/{uid}") or {}
    current = bal_data.get("balance", 0)
    new_bal = max(0, current + amount)
    fb_update(f"balances/{uid}", {"balance": new_bal})

    fb_set(f"notifications/{uid}/{int(time.time()*1000)}", {
        "type": "balance_adjusted",
        "title": "💰 تم تعديل رصيدك",
        "body": f"تم {'إضافة' if amount >= 0 else 'خصم'} {fmt_num(abs(amount))} جنيه. السبب: {reason}",
        "createdAt": int(time.time() * 1000),
        "read": False
    })

    sign = "+" if amount >= 0 else ""
    msg = f"✅ *تم تعديل الرصيد*\n\nالرصيد القديم: {fmt_num(current)} ج\nالتغيير: {sign}{fmt_num(amount)} ج\nالرصيد الجديد: *{fmt_num(new_bal)} ج*\nالسبب: {reason}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]])

    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, reply_markup=kb, parse_mode="Markdown")


# ════════════════════════════════════════════
#  البث الجماعي
# ════════════════════════════════════════════

async def show_broadcast_menu(update: Update):
    await update.callback_query.answer()
    msg = "📢 *إرسال إشعار جماعي*\n\nأدخل نص الإشعار الذي سيُرسل لجميع المستخدمين:"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="main_menu")]])
    await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")
    user_state[update.effective_chat.id] = {"action": "broadcast_text", "data": {}}


async def do_broadcast(update: Update, text: str):
    users = fb_get("users") or {}
    count = 0
    ts = int(time.time() * 1000)
    for uid in users:
        fb_set(f"notifications/{uid}/{ts + count}", {
            "type": "broadcast",
            "title": "📢 إشعار من كوبرا",
            "body": text,
            "createdAt": ts + count,
            "read": False
        })
        count += 1

    msg = f"✅ *تم إرسال الإشعار*\nإلى *{count}* مستخدم:\n\n_{text}_"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]])
    await update.message.reply_text(msg, reply_markup=kb, parse_mode="Markdown")


# ════════════════════════════════════════════
#  حذف مستخدم
# ════════════════════════════════════════════

async def delete_user(update: Update, uid: str):
    fb_delete(f"users/{uid}")
    fb_delete(f"balances/{uid}")
    fb_delete(f"orders/{uid}")
    fb_delete(f"withdrawals/{uid}")
    fb_delete(f"referrals/{uid}")
    fb_delete(f"notifications/{uid}")
    await update.callback_query.answer("🗑 تم حذف المستخدم", show_alert=True)
    await send_main_menu(update)


# ════════════════════════════════════════════
#  CallbackQuery Handler الرئيسي
# ════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    data = query.data

    if not is_admin(chat_id):
        await query.answer("🔐 غير مصرح!", show_alert=True)
        return

    if data == "main_menu":
        await send_main_menu(update)
    elif data == "stats":
        await show_stats(update)
    elif data == "orders_pending":
        await show_orders_pending(update)
    elif data == "wd_pending":
        await show_wd_pending(update)
    elif data == "users_list":
        await show_users_list(update)
    elif data == "users_recent":
        await show_users_recent(update)
    elif data == "user_search":
        await query.answer()
        user_state[chat_id] = {"action": "user_search", "data": {}}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="main_menu")]])
        await query.edit_message_text("🔍 أدخل اسم أو هاتف أو كود الإحالة:", reply_markup=kb)
    elif data == "referrals_pending":
        await show_referrals_pending(update)
    elif data == "support_open":
        await show_support_open(update)
    elif data == "settings_menu":
        await show_settings_menu(update)
    elif data == "balance_menu":
        await show_balance_menu(update)
    elif data == "broadcast_menu":
        await show_broadcast_menu(update)

    # Actions with IDs
    elif data.startswith("approve_order_"):
        parts = data.split("_", 4)
        await approve_order(update, parts[2], parts[3])
    elif data.startswith("reject_order_"):
        parts = data.split("_", 4)
        await reject_order(update, parts[2], parts[3])
    elif data.startswith("approve_wd_"):
        parts = data.split("_", 4)
        await approve_wd(update, parts[2], parts[3])
    elif data.startswith("reject_wd_"):
        parts = data.split("_", 4)
        await reject_wd(update, parts[2], parts[3])
    elif data.startswith("pay_ref_"):
        parts = data.split("_", 3)
        await pay_referral(update, parts[2], parts[3])
    elif data.startswith("close_ticket_"):
        tid = data.replace("close_ticket_", "")
        await close_ticket(update, tid)
    elif data.startswith("delete_user_"):
        uid = data.replace("delete_user_", "")
        await delete_user(update, uid)
    elif data.startswith("edit_bal_"):
        uid = data.replace("edit_bal_", "")
        await query.answer()
        user_state[chat_id] = {"action": "add_balance_direct", "data": {"uid": uid}}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="main_menu")]])
        await query.edit_message_text("💰 أدخل المبلغ (موجب للإضافة / سالب للخصم):", reply_markup=kb)
    else:
        await query.answer()


# ════════════════════════════════════════════
#  Firebase Polling للإشعارات التلقائية
# ════════════════════════════════════════════

_last_orders_keys = set()
_last_wd_keys = set()
_last_ticket_keys = set()

async def poll_firebase_notifications(app):
    """يفحص Firebase كل 30 ثانية ويرسل إشعارات للمشرفين"""
    global _last_orders_keys, _last_wd_keys, _last_ticket_keys

    # Initialize on first run
    orders_all = fb_get("orders") or {}
    for uid, uorders in orders_all.items():
        if isinstance(uorders, dict):
            for oid in uorders:
                _last_orders_keys.add(f"{uid}_{oid}")

    wd_all = fb_get("withdrawals") or {}
    for uid, uwds in wd_all.items():
        if isinstance(uwds, dict):
            for wid in uwds:
                _last_wd_keys.add(f"{uid}_{wid}")

    tickets = fb_get("support_tickets") or {}
    for tid in tickets:
        _last_ticket_keys.add(tid)

    logger.info("🔔 Firebase polling started")

    while True:
        try:
            await asyncio.sleep(30)

            # Check new orders
            orders_all = fb_get("orders") or {}
            for uid, uorders in orders_all.items():
                if not isinstance(uorders, dict):
                    continue
                for oid, o in uorders.items():
                    key = f"{uid}_{oid}"
                    if key not in _last_orders_keys and isinstance(o, dict) and o.get("status") == "pending":
                        _last_orders_keys.add(key)
                        pkg = PKGS.get(o.get("package", ""), {}).get("name", "؟")
                        amount = o.get("amount", 0)
                        phone = o.get("phone", uid)
                        notif_text = f"🛒 *طلب شراء جديد!*\n📱 الهاتف: `{phone}`\n📦 الباقة: {pkg}\n💰 المبلغ: {fmt_num(amount)} جنيه"
                        for admin_id in authenticated_admins:
                            try:
                                await app.bot.send_message(
                                    chat_id=admin_id, text=notif_text,
                                    parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup([[
                                        InlineKeyboardButton("✅ قبول", callback_data=f"approve_order_{uid}_{oid}"),
                                        InlineKeyboardButton("❌ رفض", callback_data=f"reject_order_{uid}_{oid}"),
                                    ]])
                                )
                            except Exception as e:
                                logger.error(f"Notify error: {e}")

            # Check new withdrawals
            wd_all = fb_get("withdrawals") or {}
            for uid, uwds in wd_all.items():
                if not isinstance(uwds, dict):
                    continue
                for wid, w in uwds.items():
                    key = f"{uid}_{wid}"
                    if key not in _last_wd_keys and isinstance(w, dict) and w.get("status") == "pending":
                        _last_wd_keys.add(key)
                        amount = w.get("amount", 0)
                        phone = w.get("phone", uid)
                        wallet = w.get("walletNumber", "?")
                        notif_text = f"💸 *طلب سحب جديد!*\n📱 الهاتف: `{phone}`\n💰 المبلغ: {fmt_num(amount)} جنيه\n🏦 المحفظة: `{wallet}`"
                        for admin_id in authenticated_admins:
                            try:
                                await app.bot.send_message(
                                    chat_id=admin_id, text=notif_text,
                                    parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup([[
                                        InlineKeyboardButton("✅ صرف", callback_data=f"approve_wd_{uid}_{wid}"),
                                        InlineKeyboardButton("❌ رفض", callback_data=f"reject_wd_{uid}_{wid}"),
                                    ]])
                                )
                            except Exception as e:
                                logger.error(f"Notify error: {e}")

            # Check new support tickets
            tickets = fb_get("support_tickets") or {}
            for tid, t in tickets.items():
                if tid not in _last_ticket_keys and isinstance(t, dict) and t.get("status") == "open":
                    _last_ticket_keys.add(tid)
                    problem = t.get("problemType", "غير محدد")
                    user = t.get("userName", t.get("userPhone", "?"))
                    details = str(t.get("details", ""))[:100]
                    notif_text = f"🆘 *تذكرة دعم جديدة!*\n👤 المستخدم: {user}\n📌 المشكلة: {problem}\n📝 التفاصيل: {details}"
                    for admin_id in authenticated_admins:
                        try:
                            await app.bot.send_message(
                                chat_id=admin_id, text=notif_text,
                                parse_mode="Markdown",
                                reply_markup=InlineKeyboardMarkup([[
                                    InlineKeyboardButton("✅ إغلاق", callback_data=f"close_ticket_{tid}"),
                                ]])
                            )
                        except Exception as e:
                            logger.error(f"Notify error: {e}")

        except Exception as e:
            logger.error(f"Polling error: {e}")
            await asyncio.sleep(10)


# ════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════

async def post_init(app):
    asyncio.create_task(poll_firebase_notifications(app))
    logger.info("✅ Bot started with Firebase polling")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", lambda u, c: send_main_menu(u) if is_admin(u.effective_chat.id) else None))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🐍 كوبرا بوت يعمل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
