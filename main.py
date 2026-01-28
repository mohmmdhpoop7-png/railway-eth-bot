import os
import time
import requests
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from mnemonic import Mnemonic
from eth_account import Account
from web3 import Web3
from bip44 import Wallet

# --- إعدادات من الأسرار ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

# --- إعدادات الشبكات ومزودي الخدمة ---
INFURA_PROJECT_ID = "f253c5b3780f4490956884604ad3a79a" # مفتاح عام ومجاني
ETH_PROVIDER_URL = f"https://mainnet.infura.io/v3/{INFURA_PROJECT_ID}"
BNB_PROVIDER_URL = "https://bsc-dataseed.binance.org/"

# --- عناوين عقود التوكنز (USDT, USDC) ---
TOKEN_ADDRESSES = {
    "ETH": {
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    },
    "BNB": {
        "USDT": "0x55d398326f99059fF775485246999027B3197955",
        "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
    }
}

# --- ABI مصغر لقراءة رصيد التوكن ---
MINIMAL_ABI = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]

# متغيرات عالمية للتحكم
search_active = False
wallets_checked = 0

# --- وظائف البحث الرئيسية ---
def search_wallets():
    global search_active, wallets_checked
    
    mnemo = Mnemonic("english")
    web3_eth = Web3(Web3.HTTPProvider(ETH_PROVIDER_URL))
    web3_bnb = Web3(Web3.HTTPProvider(BNB_PROVIDER_URL))

    send_telegram_message("🚀 البوت الخارق بدأ البحث عن (BTC, ETH, BNB, USDT, USDC)...")
    
    while search_active:
        try:
            phrase = mnemo.generate(strength=128)
            wallets_checked += 1
            
            # --- 1. البحث عن البيتكوين (BTC) ---
            wallet_btc = Wallet(phrase)
            path_btc = "m/44'/0'/0'/0/0"
            # السطر التالي هو الذي تم تصحيحه
            address_btc = wallet_btc.derive_account("btc", path=path_btc).address()
            res_btc = requests.get(f"https://blockchain.info/rawaddr/{address_btc}", timeout=10)
            if res_btc.status_code == 200 and res_btc.json().get('total_received', 0) > 0:
                send_telegram_message(f"💰 *وجدنا بيتكوين (BTC)!* \n\n*الكلمات:* `{phrase}`\n*العنوان:* `{address_btc}`")

            # --- 2. البحث عن عملات شبكة الإيثريوم (ETH, USDT, USDC) ---
            Account.enable_unaudited_hdwallet_features()
            account_eth = Account.from_mnemonic(phrase)
            address_eth = account_eth.address
            
            # فحص رصيد ETH الأصلي
            balance_eth_wei = web3_eth.eth.get_balance(address_eth)
            if balance_eth_wei > 0:
                balance_eth = web3_eth.from_wei(balance_eth_wei, 'ether')
                send_telegram_message(f"💰 *وجدنا إيثريوم (ETH)!* \n\n*الكلمات:* `{phrase}`\n*العنوان:* `{address_eth}`\n*الرصيد:* `{balance_eth:.6f} ETH`")
            
            # فحص رصيد USDT على شبكة ETH
            check_token_balance(web3_eth, address_eth, "USDT", "ETH", phrase)
            # فحص رصيد USDC على شبكة ETH
            check_token_balance(web3_eth, address_eth, "USDC", "ETH", phrase)

            # --- 3. البحث عن عملات شبكة BNB (BNB, USDT, USDC) ---
            # نستخدم نفس العنوان لأنه متوافق
            
            # فحص رصيد BNB الأصلي
            balance_bnb_wei = web3_bnb.eth.get_balance(address_eth)
            if balance_bnb_wei > 0:
                balance_bnb = web3_bnb.from_wei(balance_bnb_wei, 'ether')
                send_telegram_message(f"🟡 *وجدنا بينانس (BNB)!* \n\n*الكلمات:* `{phrase}`\n*العنوان:* `{address_eth}`\n*الرصيد:* `{balance_bnb:.6f} BNB`")

            # فحص رصيد USDT على شبكة BNB
            check_token_balance(web3_bnb, address_eth, "USDT", "BNB", phrase)
            # فحص رصيد USDC على شبكة BNB
            check_token_balance(web3_bnb, address_eth, "USDC", "BNB", phrase)

            # إرسال تحديث دوري
            if wallets_checked % 500 == 0:
                send_telegram_message(f"📊 تحديث: تم فحص {wallets_checked} مجموعة محافظ. البحث مستمر...")

            time.sleep(1) # فاصل زمني لتجنب حظر الـ IP

        except Exception as e:
            print(f"حدث خطأ في حلقة البحث: {e}")
            time.sleep(10)

# --- وظيفة مساعدة لفحص رصيد التوكنز ---
def check_token_balance(web3, wallet_address, token_symbol, chain_symbol, phrase):
    try:
        token_address = TOKEN_ADDRESSES[chain_symbol][token_symbol]
        contract = web3.eth.contract(address=Web3.to_checksum_address(token_address), abi=MINIMAL_ABI)
        balance_wei = contract.functions.balanceOf(wallet_address).call()
        
        if balance_wei > 0:
            # التوكنز لها عدد خانات عشرية مختلف (USDT=6, USDC=6, others=18)
            decimals = 6 if token_symbol in ["USDT", "USDC"] else 18
            balance = balance_wei / (10 ** decimals)
            msg = f"💵 *وجدنا {token_symbol} على شبكة {chain_symbol}!* \n\n*الكلمات:* `{phrase}`\n*العنوان:* `{wallet_address}`\n*الرصيد:* `{balance:.2f} {token_symbol}`"
            send_telegram_message(msg)
    except Exception as e:
        print(f"خطأ في فحص توكن {token_symbol} على {chain_symbol}: {e}")


# --- وظائف بوت التليجرام (تبقى كما هي مع تعديل بسيط في الرسائل) ---
def send_telegram_message(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                      json={"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"فشل إرسال رسالة تليجرام: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك في البوت الخارق 🤖\n\n/search - لبدء البحث الشامل.\n/status - لمعرفة الحالة.\n/stop - لإيقاف البحث.")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global search_active
    if str(update.message.chat_id) != ADMIN_CHAT_ID: return
    if not search_active:
        search_active = True
        Thread(target=search_wallets).start()
        await update.message.reply_text("✅ *تم إعطاء أمر بدء البحث الشامل.*\nالعملية ستبدأ في الخلفية الآن.")
    else:
        await update.message.reply_text("⚠️ البحث يعمل بالفعل.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global wallets_checked
    if str(update.message.chat_id) != ADMIN_CHAT_ID: return
    status_msg = "🟢 *الحالة: البحث يعمل.*" if search_active else "🔴 *الحالة: البحث متوقف.*"
    await update.message.reply_text(f"{status_msg}\nتم فحص {wallets_checked} مجموعة محافظ حتى الآن.")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global search_active
    if str(update.message.chat_id) != ADMIN_CHAT_ID: return
    if search_active:
        search_active = False
        await update.message.reply_text("⏳ *تم إعطاء أمر الإيقاف.*")
    else:
        await update.message.reply_text("⚠️ البحث متوقف بالفعل.")

def main():
    print("🚀 البوت الخارق يبدأ الآن...")
    if not TOKEN or not ADMIN_CHAT_ID:
        print("خطأ: لم يتم العثور على التوكن أو الـ ID.")
        return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stop", stop_command))

    print("البوت جاهز لاستقبال الأوامر...")
    send_telegram_message("✅ البوت الخارق بدأ العمل بنجاح على خادم Railway!")
    app.run_polling()

if __name__ == "__main__":
    main()
MINIMAL_ABI = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]

# متغيرات عالمية للتحكم
search_active = False
wallets_checked = 0

# --- وظائف البحث الرئيسية ---
def search_wallets():
    global search_active, wallets_checked
    
    mnemo = Mnemonic("english")
    web3_eth = Web3(Web3.HTTPProvider(ETH_PROVIDER_URL))
    web3_bnb = Web3(Web3.HTTPProvider(BNB_PROVIDER_URL))

    send_telegram_message("🚀 البوت الخارق بدأ البحث عن (BTC, ETH, BNB, USDT, USDC)...")
    
    while search_active:
        try:
            phrase = mnemo.generate(strength=128)
            wallets_checked += 1
            
            # --- 1. البحث عن البيتكوين (BTC) ---
            wallet_btc = Wallet(phrase)
            path_btc = "m/44'/0'/0'/0/0"
            address_btc = get_btc_addr(wallet_btc.derive_account("btc", path=path_btc))
            res_btc = requests.get(f"https://blockchain.info/rawaddr/{address_btc}", timeout=10)
            if res_btc.status_code == 200 and res_btc.json().get('total_received', 0) > 0:
                send_telegram_message(f"💰 *وجدنا بيتكوين (BTC)!* \n\n*الكلمات:* `{phrase}`\n*العنوان:* `{address_btc}`")

            # --- 2. البحث عن عملات شبكة الإيثريوم (ETH, USDT, USDC) ---
            Account.enable_unaudited_hdwallet_features()
            account_eth = Account.from_mnemonic(phrase)
            address_eth = account_eth.address
            
            # فحص رصيد ETH الأصلي
            balance_eth_wei = web3_eth.eth.get_balance(address_eth)
            if balance_eth_wei > 0:
                balance_eth = web3_eth.from_wei(balance_eth_wei, 'ether')
                send_telegram_message(f"💰 *وجدنا إيثريوم (ETH)!* \n\n*الكلمات:* `{phrase}`\n*العنوان:* `{address_eth}`\n*الرصيد:* `{balance_eth:.6f} ETH`")
            
            # فحص رصيد USDT على شبكة ETH
            check_token_balance(web3_eth, address_eth, "USDT", "ETH", phrase)
            # فحص رصيد USDC على شبكة ETH
            check_token_balance(web3_eth, address_eth, "USDC", "ETH", phrase)

            # --- 3. البحث عن عملات شبكة BNB (BNB, USDT, USDC) ---
            # نستخدم نفس العنوان لأنه متوافق
            
            # فحص رصيد BNB الأصلي
            balance_bnb_wei = web3_bnb.eth.get_balance(address_eth)
            if balance_bnb_wei > 0:
                balance_bnb = web3_bnb.from_wei(balance_bnb_wei, 'ether')
                send_telegram_message(f"🟡 *وجدنا بينانس (BNB)!* \n\n*الكلمات:* `{phrase}`\n*العنوان:* `{address_eth}`\n*الرصيد:* `{balance_bnb:.6f} BNB`")

            # فحص رصيد USDT على شبكة BNB
            check_token_balance(web3_bnb, address_eth, "USDT", "BNB", phrase)
            # فحص رصيد USDC على شبكة BNB
            check_token_balance(web3_bnb, address_eth, "USDC", "BNB", phrase)

            # إرسال تحديث دوري
            if wallets_checked % 500 == 0:
                send_telegram_message(f"📊 تحديث: تم فحص {wallets_checked} مجموعة محافظ. البحث مستمر...")

            time.sleep(1) # فاصل زمني لتجنب حظر الـ IP

        except Exception as e:
            print(f"حدث خطأ في حلقة البحث: {e}")
            time.sleep(10)

# --- وظيفة مساعدة لفحص رصيد التوكنز ---
def check_token_balance(web3, wallet_address, token_symbol, chain_symbol, phrase):
    try:
        token_address = TOKEN_ADDRESSES[chain_symbol][token_symbol]
        contract = web3.eth.contract(address=Web3.to_checksum_address(token_address), abi=MINIMAL_ABI)
        balance_wei = contract.functions.balanceOf(wallet_address).call()
        
        if balance_wei > 0:
            # التوكنز لها عدد خانات عشرية مختلف (USDT=6, USDC=6, others=18)
            decimals = 6 if token_symbol in ["USDT", "USDC"] else 18
            balance = balance_wei / (10 ** decimals)
            msg = f"💵 *وجدنا {token_symbol} على شبكة {chain_symbol}!* \n\n*الكلمات:* `{phrase}`\n*العنوان:* `{wallet_address}`\n*الرصيد:* `{balance:.2f} {token_symbol}`"
            send_telegram_message(msg)
    except Exception as e:
        print(f"خطأ في فحص توكن {token_symbol} على {chain_symbol}: {e}")


# --- وظائف بوت التليجرام (تبقى كما هي مع تعديل بسيط في الرسائل) ---
def send_telegram_message(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                      json={"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"فشل إرسال رسالة تليجرام: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك في البوت الخارق 🤖\n\n/search - لبدء البحث الشامل.\n/status - لمعرفة الحالة.\n/stop - لإيقاف البحث.")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global search_active
    if str(update.message.chat_id) != ADMIN_CHAT_ID: return
    if not search_active:
        search_active = True
        Thread(target=search_wallets).start()
        await update.message.reply_text("✅ *تم إعطاء أمر بدء البحث الشامل.*\nالعملية ستبدأ في الخلفية الآن.")
    else:
        await update.message.reply_text("⚠️ البحث يعمل بالفعل.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global wallets_checked
    if str(update.message.chat_id) != ADMIN_CHAT_ID: return
    status_msg = "🟢 *الحالة: البحث يعمل.*" if search_active else "🔴 *الحالة: البحث متوقف.*"
    await update.message.reply_text(f"{status_msg}\nتم فحص {wallets_checked} مجموعة محافظ حتى الآن.")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global search_active
    if str(update.message.chat_id) != ADMIN_CHAT_ID: return
    if search_active:
        search_active = False
        await update.message.reply_text("⏳ *تم إعطاء أمر الإيقاف.*")
    else:
        await update.message.reply_text("⚠️ البحث متوقف بالفعل.")

def main():
    print("🚀 البوت الخارق يبدأ الآن...")
    if not TOKEN or not ADMIN_CHAT_ID:
        print("خطأ: لم يتم العثور على التوكن أو الـ ID.")
        return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stop", stop_command))

    print("البوت جاهز لاستقبال الأوامر...")
    send_telegram_message("✅ البوت الخارق بدأ العمل بنجاح على خادم Railway!")
    app.run_polling()

if __name__ == "__main__":
    main()
