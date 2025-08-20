from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, filters, ConversationHandler
)
from telegram.constants import ParseMode
import json
import asyncio

# Bot ayarları
BOT_TOKEN = "8085361560:AAEsZKphKDtQyfxMGUcUUd2XXXSh-VBHojk"
ADMIN_ID = 6472876244  # Buraya sizin Telegram ID'nizi yazın (önce /chatid ile öğrenin)
GROUP_CHAT_ID = -1002882964046  # Bira Raf Kota grubu

# ConversationHandler için state ve geçici kullanıcı ilerleme dict'i
UPDATE_KOTA = range(1)
update_progress = {}

# Kategori sırası
kategori_sirasi = ["cinsiyet", "yas", "ses", "marka", "calisma_durumu", "mezuniyet", "medeni_durum", "kullanim"]

# Global değişkenler
kotalar = {}
user_secimleri = {}
user_gruplari = {}
user_last_click = {}

def kotalari_yukle():
    """Kotaları JSON dosyasından yükler"""
    try:
        with open("kotalar.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def kotalari_kaydet():
    """Kotaları JSON dosyasına kaydeder"""
    with open("kotalar.json", "w", encoding="utf-8") as f:
        json.dump(kotalar, f, ensure_ascii=False, indent=2)

def kategori_adi_formatla(kategori):
    """Kategori adını güzel formatta döndürür"""
    return kategori.replace('_', ' ').title()

def admin_kontrol(user_id):
    """Kullanıcının admin olup olmadığını kontrol eder"""
    return user_id == ADMIN_ID

# Kotaları yükle
kotalar = kotalari_yukle()

# === ConversationHandler ile KOTA GÜNCELLEME ===
async def update_kota_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkiniz yok")
        return ConversationHandler.END
    
    update_progress[user_id] = {"kategori_index": 0, "kategori": None, "secenek": None, "secenek_index": 0}
    await ask_next_kota(update.message, user_id)
    return UPDATE_KOTA

async def ask_next_kota(update_or_message, user_id):
    idx = update_progress[user_id]["kategori_index"]
    if idx >= len(kategori_sirasi):
        await update_or_message.reply_text("✅ Tüm kategoriler için kota güncellendi!")
        update_progress.pop(user_id, None)
        return ConversationHandler.END
    
    kategori = kategori_sirasi[idx]
    update_progress[user_id]["kategori"] = kategori
    secenekler = list(kotalar[kategori].keys())
    
    if not secenekler:
        await update_or_message.reply_text(f"{kategori_adi_formatla(kategori)} kategorisinde hiç seçenek yok, atlanıyor...")
        update_progress[user_id]["kategori_index"] += 1
        await ask_next_kota(update_or_message, user_id)
        return
    
    # Seçenek index'ini kontrol et
    secenek_idx = update_progress[user_id].get("secenek_index", 0)
    
    if secenek_idx >= len(secenekler):
        # Bu kategorideki tüm seçenekler tamamlandı, sonraki kategoriye geç
        update_progress[user_id]["kategori_index"] += 1
        update_progress[user_id]["secenek_index"] = 0
        await ask_next_kota(update_or_message, user_id)
        return
    
    # Şu anki seçeneği göster
    secenek = secenekler[secenek_idx]
    mevcut_kota = kotalar[kategori][secenek]
    
    await update_or_message.reply_text(
        f"📝 **{kategori_adi_formatla(kategori)}** kategorisi - **{secenek}**\n"
        f"Şu anki kota: **{mevcut_kota}**\n\n"
        f"Yeni kotayı girin:"
    )

async def update_kota_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID or user_id not in update_progress:
        await update.message.reply_text("❌ Yetkiniz yok veya işlem başlatmadınız.")
        return ConversationHandler.END
    
    idx = update_progress[user_id]["kategori_index"]
    kategori = update_progress[user_id]["kategori"]
    secenekler = list(kotalar[kategori].keys())
    secenek_idx = update_progress[user_id].get("secenek_index", 0)
    
    text = update.message.text.strip()
    try:
        yeni_kota = int(text)
    except ValueError:
        await update.message.reply_text("❌ Lütfen sadece sayı giriniz.")
        return UPDATE_KOTA
    
    # Şu anki seçeneği al
    secenek = secenekler[secenek_idx]
    
    # Kotayı güncelle
    kotalar[kategori][secenek] = yeni_kota
    kotalari_kaydet()
    
    await update.message.reply_text(
        f"✅ **{kategori_adi_formatla(kategori)}** - **{secenek}** kotası **{yeni_kota}** olarak güncellendi."
    )
    
    # Seçenek index'ini artır
    update_progress[user_id]["secenek_index"] = secenek_idx + 1
    
    # Sonraki seçeneğe veya kategoriye geç
    await ask_next_kota(update.message, user_id)
    
    # Eğer tüm kategoriler tamamlandıysa ConversationHandler'ı sonlandır
    if update_progress[user_id]["kategori_index"] >= len(kategori_sirasi):
        return ConversationHandler.END
    
    return UPDATE_KOTA

# === ANA FONKSİYONLAR ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    print(f"=== START KOMUTU ===")
    print(f"user_id: {user_id}")
    print(f"chat_id: {chat_id}")
    print(f"ADMIN_ID: {ADMIN_ID}")
    print(f"admin_kontrol(user_id): {admin_kontrol(user_id)}")
    
    # Kullanıcının önceki seçimlerini sıfırla
    if user_id in user_secimleri:
        del user_secimleri[user_id]
    
    # Kullanıcı için yeni seçim sözlüğü oluştur
    user_secimleri[user_id] = {}
    user_gruplari[user_id] = chat_id
    
    print(f"START sonrası user_secimleri: {user_secimleri}")
    
    # Ana menüyü göster
    await show_main_menu(update.message, user_id)

async def show_main_menu(message_obj, user_id):
    """Ana menüyü gösterir"""
    keyboard = [
        [InlineKeyboardButton("🚀 Anketi Başlat", callback_data="menu_start_survey")],
        [InlineKeyboardButton("📊 Kotaları Göster", callback_data="menu_show_kota")],
        [InlineKeyboardButton("📋 Durum", callback_data="menu_status")],
        [InlineKeyboardButton("🔄 Yeni Anket", callback_data="menu_new_survey")],
        [InlineKeyboardButton("📱 Yardım", callback_data="menu_help")]
    ]
    
    # Admin ise admin menüsü butonu ekle
    if admin_kontrol(user_id):
        keyboard.append([InlineKeyboardButton("🔧 Admin Menüsü", callback_data="admin_menu")])
    
    await message_obj.reply_text(
        "🎯 **KOTA BOT ANA MENÜSÜ**\n\nHangi işlemi yapmak istiyorsunuz?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_admin_menu(message_obj):
    """Admin menüsünü gösterir"""
    keyboard = [
        [InlineKeyboardButton("🔧 Admin Yardım", callback_data="admin_help")],
        [InlineKeyboardButton("📊 Admin Bilgileri", callback_data="admin_bilgi")],
        [InlineKeyboardButton("➕ Kota Ekle", callback_data="admin_kota_ekle")],
        [InlineKeyboardButton("✏️ Kota Güncelle", callback_data="admin_kota_guncelle")],
        [InlineKeyboardButton("🗑️ Kota Sil", callback_data="admin_kota_sil")],
        [InlineKeyboardButton("📁 Kategori Ekle", callback_data="admin_kategori_ekle")],
        [InlineKeyboardButton("🗂️ Kategori Sil", callback_data="admin_kategori_sil")],
        [InlineKeyboardButton("🔄 Yeni Anket", callback_data="admin_yeni_anket")],
        [InlineKeyboardButton("🏠 Ana Menüye Dön", callback_data="menu_main")]
    ]
    await message_obj.reply_text(
        "🔧 **ADMIN MENÜSÜ**\n\nHangi admin işlemini yapmak istiyorsunuz?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_category_buttons(message_obj, user_id, kategori_index, context=None):
    print(f"show_category_buttons: user_id={user_id}, index={kategori_index}")
    
    if kategori_index >= len(kategori_sirasi):
        # Tüm kategoriler tamamlandı
        await complete_survey(message_obj, user_id)
        return
    
    kategori = kategori_sirasi[kategori_index]
    secenekler = kotalar[kategori]
    
    print(f"Kategori: {kategori}, Seçenekler: {list(secenekler.keys())}")
    
    # Butonları oluştur
    keyboard = []
    for i, (secenek, kalan) in enumerate(secenekler.items(), 1):
        if kalan > 0:  # Sadece kotası olan seçenekleri göster
            label = f"{i}. {secenek} ({kalan})"
            callback_data = f"sel_{kategori}_{i}"
            print(f"Button {i}: {label} -> {callback_data}")
            keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    
    # Geri Al butonu ekle (eğer bu kategoriden önce seçim yapıldıysa)
    if kategori_index > 0:
        keyboard.append([InlineKeyboardButton("⬅️ Geri Al", callback_data=f"geri_{kategori_index-1}")])
    
    # Mesajı gönder
    await message_obj.reply_text(
        text=f"📊 {kategori_adi_formatla(kategori)} seçiniz:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def complete_survey(message_obj, user_id):
    """Anketi tamamlar ve kotaları günceller"""
    if user_id not in user_secimleri:
        await message_obj.reply_text("❌ Anket verisi bulunamadı")
        return
    
    secimler = user_secimleri[user_id]
    
    # Kotaları güncelle
    for kategori, secim in secimler.items():
        if kategori in kotalar and secim in kotalar[kategori]:
            kotalar[kategori][secim] -= 1
    
    # JSON'a kaydet
    kotalari_kaydet()
    
    # Kotaları göster
    await send_kotas_to_bira_raf_kota(message_obj, user_id)
    
    # Gruba güncel kotaları gönder
    await send_kotas_to_group()
    
    # Kullanıcı verilerini temizle
    if user_id in user_secimleri:
        del user_secimleri[user_id]
    if user_id in user_gruplari:
        del user_gruplari[user_id]

async def send_kotas_to_bira_raf_kota(message_obj, user_id, context=None):
    # Güncel kotaları güzel alt alta formatında hazırla
    mesaj = "📊 **GÜNCEL KOTALAR** 📊\n\n"
    
    for i, kategori in enumerate(kategori_sirasi):
        mesaj += f"🔹 **{kategori_adi_formatla(kategori).upper()}**\n"
        
        for secenek, kalan in kotalar[kategori].items():
            # Kota durumuna göre renk belirle (0 = kırmızı)
            if kalan <= 0:
                color = "🔴"  # Kırmızı (0 ve altı)
            elif kalan <= 5:
                color = "🟡"  # Sarı (1-5 arası)
            else:
                color = "🟢"  # Yeşil (6 ve üstü)
            
            # Alt alta format: renk + seçenek adı + kota sayısı (kalın)
            mesaj += f"{color}{secenek}\n**({kalan})**\n\n"
        
        # Kategoriler arasında çizgi ekle (son kategoride değil)
        if i < len(kategori_sirasi) - 1:
            mesaj += "---------------------------\n\n"
    
    # Ana menüye dönüş butonu ekle
    keyboard = [
        [InlineKeyboardButton("🏠 Ana Menüye Dön", callback_data="menu_main")]
    ]
    
    await message_obj.reply_text(mesaj, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def send_kotas_to_group():
    """Güncel kotaları gruba gönderir"""
    if GROUP_CHAT_ID is None:
        print("⚠️ GROUP_CHAT_ID ayarlanmamış, gruba mesaj gönderilmiyor")
        return
        
    try:
        # Güncel kotaları güzel alt alta formatında hazırla
        mesaj = "🆕 **YENİ ANKET TAMAMLANDI!** 🆕\n\n"
        mesaj += "📊 **GÜNCEL KOTALAR** 📊\n\n"
        
        for i, kategori in enumerate(kategori_sirasi):
            mesaj += f"🔹 **{kategori_adi_formatla(kategori).upper()}**\n"
            
            for secenek, kalan in kotalar[kategori].items():
                # Kota durumuna göre renk belirle (0 = kırmızı)
                if kalan <= 0:
                    color = "🔴"  # Kırmızı (0 ve altı)
                elif kalan <= 5:
                    color = "🟡"  # Sarı (1-5 arası)
                else:
                    color = "🟢"  # Yeşil (6 ve üstü)
                
                # Alt alta format: renk + seçenek adı + kota sayısı (kalın)
                mesaj += f"{color}{secenek}\n**({kalan})**\n\n"
            
            # Kategoriler arasında çizgi ekle (son kategoride değil)
            if i < len(kategori_sirasi) - 1:
                mesaj += "---------------------------\n\n"
        
        # Gruba mesaj gönder (context.bot kullan)
        # Bu fonksiyon context olmadan çağrıldığı için global app kullan
        global app
        await app.bot.send_message(chat_id=GROUP_CHAT_ID, text=mesaj, parse_mode='Markdown')
        print(f"✅ Güncel kotalar gruba gönderildi: {GROUP_CHAT_ID}")
        
    except Exception as e:
        print(f"❌ Gruba mesaj gönderme hatası: {e}")
        # Hata olursa da anketi tamamlamaya devam et

async def show_kota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Güncel kotaları güzel alt alta formatında hazırla
    mesaj = "📊 **GÜNCEL KOTALAR** 📊\n\n"
    
    for i, kategori in enumerate(kategori_sirasi):
        mesaj += f"🔹 **{kategori_adi_formatla(kategori).upper()}**\n"
        
        for secenek, kalan in kotalar[kategori].items():
            # Kota durumuna göre renk belirle (0 = kırmızı)
            if kalan <= 0:
                color = "🔴"  # Kırmızı (0 ve altı)
            elif kalan <= 5:
                color = "🟡"  # Sarı (1-5 arası)
            else:
                color = "🟢"  # Yeşil (6 ve üstü)
            
            # Alt alta format: renk + seçenek adı + kota sayısı (kalın)
            mesaj += f"{color}{secenek}\n**({kalan})**\n\n"
        
        # Kategoriler arasında çizgi ekle (son kategoride değil)
        if i < len(kategori_sirasi) - 1:
            mesaj += "---------------------------\n\n"
    
    # Ana menüye dönüş butonu ekle
    keyboard = [
        [InlineKeyboardButton("🏠 Ana Menüye Dön", callback_data="menu_main")]
    ]
    
    await update.message.reply_text(mesaj, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_secimleri or not user_secimleri[user_id]:
        await update.message.reply_text("Henüz hiçbir seçim yapmadınız.")
        return
    
    mesaj = "📋 Mevcut Seçimleriniz:\n"
    for kategori, secim in user_secimleri[user_id].items():
        mesaj += f"  {kategori_adi_formatla(kategori)}: {secim}\n"
    
    # Hangi kategorinin kaldığını göster
    kalan_kategoriler = [k for k in kategori_sirasi if k not in user_secimleri[user_id]]
    if kalan_kategoriler:
        mesaj += f"\n⏳ Kalan kategoriler: {', '.join([kategori_adi_formatla(k) for k in kalan_kategoriler])}"
    
    await update.message.reply_text(mesaj)

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yardım mesajını gösterir"""
    help_text = """
📱 **KOTA BOT YARDIM**

🚀 **Komutlar:**
/start - Anketi başlat
/help - Bu yardım mesajı
/showkota - Güncel kotaları göster
/status - Anket durumunuzu göster
/yeni_anket - Yeni anket başlat

🔧 **Admin Komutları:**
/updatekota - Kotaları güncelle
/addkota - Yeni kota ekle
/delkota - Kota sil
/addkategori - Kategori ekle
/delkategori - Kategori sil

📊 **Anket Süreci:**
1. /start ile başlayın
2. Her kategoriden bir seçenek seçin
3. Tüm kategoriler tamamlandığında kotalar güncellenir
4. Güncel kotaları görebilirsiniz
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chat ID'yi gösterir"""
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    chat_type = update.message.chat.type
    
    # Chat türü bilgisi
    if chat_type == "private":
        chat_type_text = "👤 Özel Sohbet"
    elif chat_type == "group":
        chat_type_text = "👥 Grup"
    elif chat_type == "supergroup":
        chat_type_text = "👥 Süper Grup"
    elif chat_type == "channel":
        chat_type_text = "📢 Kanal"
    else:
        chat_type_text = f"❓ {chat_type}"
    
    # Chat adı
    chat_title = update.message.chat.title or "Özel Sohbet"
    
    mesaj = f"📱 **Chat ID Bilgileri:**\n\n"
    mesaj += f"💬 **Chat ID:** `{chat_id}`\n"
    mesaj += f"👤 **User ID:** `{user_id}`\n"
    mesaj += f"📝 **Chat Türü:** {chat_type_text}\n"
    mesaj += f"🏷️ **Chat Adı:** {chat_title}\n\n"
    
    if chat_type in ["group", "supergroup"]:
        mesaj += "✅ **Bu bir grup!** Gruba mesaj göndermek için bu Chat ID'yi kullanın.\n\n"
        mesaj += "🔧 **Kullanım:**\n"
        mesaj += "1. Bu Chat ID'yi kopyalayın\n"
        mesaj += "2. `bot.py` dosyasındaki `GROUP_CHAT_ID` değerini güncelleyin\n"
        mesaj += "3. Bot'u yeniden başlatın"
    
    await update.message.reply_text(mesaj, parse_mode='Markdown')

async def yeni_anket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yeni anket başlatır"""
    user_id = update.message.from_user.id
    
    # Kullanıcının önceki seçimlerini sıfırla
    if user_id in user_secimleri:
        del user_secimleri[user_id]
    
    # Kullanıcı için yeni seçim sözlüğü oluştur
    user_secimleri[user_id] = {}
    user_gruplari[user_id] = update.message.chat_id
    
    # İlk kategoriyi göster
    await show_category_buttons(update.message, user_id, 0)

# === ADMIN KOMUTLARI ===
async def add_kota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkiniz yok")
        return
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Kullanım: /addkota <kategori> <secenek> <sayi>")
        return
    
    kategori, secenek, sayi = args[0], args[1], args[2]
    try:
        sayi = int(sayi)
    except ValueError:
        await update.message.reply_text("Sayı geçersiz")
        return
    
    if kategori not in kotalar:
        await update.message.reply_text(f"Kategori '{kategori}' bulunamadı")
        return
    
    kotalar[kategori][secenek] = sayi
    kotalari_kaydet()
    await update.message.reply_text(f"✅ {kategori} kategorisine '{secenek}' seçeneği {sayi} kotası ile eklendi.")

async def add_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkiniz yok")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Kullanım: /addkategori <kategori_adi> <secenek1> <secenek2> ...")
        return
    
    kategori_adi = args[0]
    secenekler = args[1:]
    
    if kategori_adi in kotalar:
        await update.message.reply_text(f"Kategori '{kategori_adi}' zaten mevcut")
        return
    
    kotalar[kategori_adi] = {secenek: 10 for secenek in secenekler}
    kategori_sirasi.append(kategori_adi)
    kotalari_kaydet()
    await update.message.reply_text(f"✅ '{kategori_adi}' kategorisi eklendi: {', '.join(secenekler)}")

async def del_kota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkiniz yok")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Kullanım: /delkota <kategori> <secenek>")
        return
    
    kategori, secenek = args[0], args[1]
    if kategori not in kotalar:
        await update.message.reply_text(f"Kategori '{kategori}' bulunamadı")
        return
    
    if secenek not in kotalar[kategori]:
        await update.message.reply_text(f"Seçenek '{secenek}' bulunamadı")
        return
    
    del kotalar[kategori][secenek]
    kotalari_kaydet()
    await update.message.reply_text(f"✅ {kategori} kategorisinden '{secenek}' silindi.")

async def del_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkiniz yok")
        return
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Kullanım: /delkategori <kategori>")
        return
    
    kategori = args[0]
    if kategori not in kotalar:
        await update.message.reply_text(f"Kategori '{kategori}' bulunamadı")
        return
    
    del kotalar[kategori]
    if kategori in kategori_sirasi:
        kategori_sirasi.remove(kategori)
    kotalari_kaydet()
    await update.message.reply_text(f"✅ '{kategori}' kategorisi silindi.")

# === BUTON CALLBACK HANDLER ===
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    print(f"Button callback: {data} from user {user_id}")
    
    if data.startswith("menu_"):
        await handle_menu_callback(query, data)
    elif data.startswith("admin_"):
        await handle_admin_callback(query, data)
    elif data.startswith("sel_"):
        await handle_selection_callback(query, data, user_id)
    elif data.startswith("geri_"):
        await handle_back_callback(query, data, user_id)
    else:
        await query.message.reply_text("❌ Bilinmeyen buton")

async def handle_menu_callback(query, data):
    """Menü butonlarını işler"""
    user_id = query.from_user.id
    
    if data == "menu_main":
        await show_main_menu(query.message, user_id)
    elif data == "menu_start_survey":
        await start_survey(query.message, user_id)
    elif data == "menu_show_kota":
        # show_kota fonksiyonu Update objesi bekliyor, mock oluştur
        mock_update = type('MockUpdate', (), {'message': query.message})()
        await show_kota(mock_update, None)
    elif data == "menu_status":
        # show_status fonksiyonu Update objesi bekliyor, mock oluştur
        mock_update = type('MockUpdate', (), {'message': query.message})()
        await show_status(mock_update, None)
    elif data == "menu_new_survey":
        # yeni_anket fonksiyonu Update objesi bekliyor, mock oluştur
        mock_update = type('MockUpdate', (), {'message': query.message})()
        await yeni_anket(mock_update, None)
    elif data == "menu_help":
        # help fonksiyonu Update objesi bekliyor, mock oluştur
        mock_update = type('MockUpdate', (), {'message': query.message})()
        await help(mock_update, None)

async def handle_admin_callback(query, data):
    """Admin butonlarını işler"""
    user_id = query.from_user.id
    
    if not admin_kontrol(user_id):
        await query.message.reply_text("❌ Yetkiniz yok")
        return
    
    if data == "admin_menu":
        await show_admin_menu(query.message)
    elif data == "admin_help":
        await query.message.reply_text("🔧 **ADMIN YARDIM**\n\n/adminhelp - Bu yardım mesajı\n/adminbilgi - Admin bilgileri\n/updatekota - Kotaları güncelle\n/addkota - Kota ekle\n/delkota - Kota sil\n/addkategori - Kategori ekle\n/delkategori - Kategori sil", parse_mode='Markdown')
    elif data == "admin_bilgi":
        await query.message.reply_text(f"🔧 **ADMIN BİLGİLERİ**\n\n👤 Admin ID: `{ADMIN_ID}`\n📊 Toplam Kategori: {len(kategori_sirasi)}\n📝 Toplam Seçenek: {sum(len(kotalar[k]) for k in kotalar)}", parse_mode='Markdown')
    elif data == "admin_kota_guncelle":
        # update_kota_start fonksiyonu Update objesi bekliyor, mock oluştur
        mock_update = type('MockUpdate', (), {'message': query.message})()
        await update_kota_start(mock_update, None)
    elif data == "admin_yeni_anket":
        # yeni_anket fonksiyonu Update objesi bekliyor, mock oluştur
        mock_update = type('MockUpdate', (), {'message': query.message})()
        await yeni_anket(mock_update, None)

async def handle_selection_callback(query, data, user_id):
    """Seçim butonlarını işler"""
    try:
        print(f"Selection callback data: {data}")
        
        # Callback data formatı: sel_KATEGORI_INDEX
        # Örnek: sel_calisma_durumu_1, sel_cinsiyet_2
        
        if not data.startswith('sel_'):
            await query.message.reply_text("❌ Geçersiz seçim formatı")
            return
        
        # "sel_" kısmını çıkar
        data_without_sel = data[4:]
        
        # Son alt çizgiden böl (index için)
        last_underscore_index = data_without_sel.rfind('_')
        if last_underscore_index == -1:
            await query.message.reply_text("❌ Geçersiz seçim formatı")
            return
        
        kategori = data_without_sel[:last_underscore_index]
        secenek_index = int(data_without_sel[last_underscore_index + 1:]) - 1
        
        print(f"Kategori: {kategori}, Secenek index: {secenek_index}")
        
        if kategori not in kotalar:
            await query.message.reply_text(f"❌ Kategori bulunamadı: {kategori}")
            return
        
        secenekler = list(kotalar[kategori].keys())
        if secenek_index >= len(secenekler):
            await query.message.reply_text(f"❌ Seçenek index'i geçersiz: {secenek_index + 1}")
            return
        
        secenek = secenekler[secenek_index]
        print(f"Seçilen seçenek: {secenek}")
        
        # Seçimi kaydet
        if user_id not in user_secimleri:
            user_secimleri[user_id] = {}
        user_secimleri[user_id][kategori] = secenek
        
        print(f"Seçim kaydedildi: {user_secimleri[user_id]}")
        
        # Sonraki kategoriyi göster
        current_index = kategori_sirasi.index(kategori)
        next_index = current_index + 1
        
        await show_category_buttons(query.message, user_id, next_index)
        
    except Exception as e:
        print(f"Selection callback hatası: {e}")
        await query.message.reply_text(f"❌ Seçim işlenirken hata oluştu: {str(e)}")

async def handle_back_callback(query, data, user_id):
    """Geri butonlarını işler"""
    parts = data.split('_')
    if len(parts) != 2:
        await query.message.reply_text("❌ Geçersiz geri butonu")
        return
    
    kategori_index = int(parts[1])
    
    # Son seçimi sil
    if user_id in user_secimleri:
        current_kategori = kategori_sirasi[kategori_index + 1]
        if current_kategori in user_secimleri[user_id]:
            del user_secimleri[user_id][current_kategori]
    
    # Önceki kategoriyi göster
    await show_category_buttons(query.message, user_id, kategori_index)

async def start_survey(message_obj, user_id):
    """Anketi başlatır"""
    # İlk kategoriyi göster
    await show_category_buttons(message_obj, user_id, 0)

# Bot menü butonunu ayarla
async def set_bot_menu(application):
    """Bot menü butonunu ayarlar"""
    try:
        from telegram import BotCommand
        
        # Genel kullanıcı komutları
        commands = [
            BotCommand("start", "🚀 Anketi başlat"),
            BotCommand("help", "📱 Yardım"),
            BotCommand("showkota", "📊 Kotaları göster"),
            BotCommand("status", "📋 Durum"),
            BotCommand("yeni_anket", "🔄 Yeni anket"),
            BotCommand("chatid", "🆔 Chat ID"),
        ]
        
        # Admin komutları ekle
        admin_commands = [
            BotCommand("updatekota", "✏️ Kota Güncelle"),
            BotCommand("addkota", "➕ Kota Ekle"),
            BotCommand("delkota", "🗑️ Kota Sil"),
            BotCommand("addkategori", "📁 Kategori Ekle"),
            BotCommand("delkategori", "🗂️ Kategori Sil"),
        ]
        
        # Tüm komutları birleştir
        all_commands = commands + admin_commands
        
        await application.bot.set_my_commands(all_commands)
        print("✅ Bot menü butonları ayarlandı!")
        
    except Exception as e:
        print(f"❌ Bot menü butonları ayarlanamadı: {e}")

# Ana fonksiyon
async def main():
    """Ana fonksiyon"""
    # Bot uygulamasını oluştur
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Bot menü butonlarını ayarla
    app.post_init = set_bot_menu
    
    # Handler'ları ekle
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("chatid", get_chat_id))
    app.add_handler(CommandHandler("showkota", show_kota))
    app.add_handler(CommandHandler("status", show_status))
    app.add_handler(CommandHandler("yeni_anket", yeni_anket))
    
    # Admin komutları
    app.add_handler(CommandHandler("addkota", add_kota))
    app.add_handler(CommandHandler("addkategori", add_kategori))
    app.add_handler(CommandHandler("delkota", del_kota))
    app.add_handler(CommandHandler("delkategori", del_kategori))
    
    # ConversationHandler ile güncelleme
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("updatekota", update_kota_start)],
        states={UPDATE_KOTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_kota_process)]},
        fallbacks=[]
    )
    app.add_handler(conv_handler)
    
    print("Bot çalışıyor...")
    
    # Render için: Manuel polling yap
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    
    # Bot'u çalışır durumda tut
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Bot durduruluyor...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

# Bot başlatıldığında menü butonlarını ayarla
if __name__ == "__main__":
    print("🚀 Bot başlatılıyor...")
    
    try:
        # Bot'u çalıştır
        print("✅ Bot başlatıldı, polling başlıyor...")
        
        # En basit yaklaşım: asyncio.run kullan
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n🛑 Bot durduruldu")
    except Exception as e:
        print(f"❌ Bot hatası: {e}")
        import traceback
        traceback.print_exc()
