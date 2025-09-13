from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, filters, ConversationHandler
)
from telegram.constants import ParseMode
import json
import asyncio
from flask import Flask, request
import threading
import os
import time

# Flask app oluştur (Railway/Vercel için)
web_app = Flask(__name__)
# Vercel '@vercel/python' Flask uygulamasını 'app' adıyla bekler
app = web_app

# Bot ayarları
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8085361560:AAEsZKphKDtQyfxMGUcUUd2XXXSh-VBHojk")  # Env > fallback
ADMIN_ID = int(os.environ.get("ADMIN_ID", 6472876244))
GROUP_CHAT_ID = int(os.environ.get("GROUP_CHAT_ID", -1002882964046))

# Environment variable kontrolü
PAUSE_BOT = os.environ.get("PAUSE_BOT", "false").lower() == "true"

# ConversationHandler için state ve geçici kullanıcı ilerleme dict'i
# Not: Tek bir state kullanılacak; int olmalı (range değil)
UPDATE_KOTA = 1
update_progress = {}

# Kategori sırası
kategori_sirasi = ["il", "cinsiyet", "yas", "ses", "sokak_isyeri_hane", "cadde"]

# İller listesi
iller = ["Lefkoşa", "Gazimağusa", "Girne", "Güzelyurt", "İskele"]

# Cinsiyet seçenekleri
cinsiyet_secenekleri = ["Erkek", "Kadın"]

# Yaş grupları
yas_gruplari = ["18-24", "25-34", "35-44", "45-54", "55-64"]

# SES grupları
ses_gruplari = ["AB", "C1", "C2", "DE"]

# Sokak/İşyeri/Hane seçenekleri
sokak_isyeri_hane_secenekleri = ["Sokak", "İşyeri", "Hane"]

# Cadde seçenekleri (her il için farklı olabilir)
cadde_secenekleri = ["Merkez", "Çevre", "Kırsal"]

# Global değişkenler
kotalar = {}
user_secimleri = {}
user_gruplari = {}
user_last_click = {}

# Global bot app
bot_app = None

def kotalari_yukle():
    """Kotaları JSON dosyasından yükler"""
    try:
        with open("kotalar.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # Yeni yapıya göre varsayılan kotaları oluştur
        return yeni_kota_yapisi_olustur()

def yeni_kota_yapisi_olustur():
    """Yeni proje yapısına göre kotaları oluşturur"""
    kotalar = {}
    
    # Her il için kotaları oluştur
    for il in iller:
        kotalar[il] = {
            "cinsiyet": {cinsiyet: 10 for cinsiyet in cinsiyet_secenekleri},
            "yas": {yas: 10 for yas in yas_gruplari},
            "ses": {ses: 10 for ses in ses_gruplari},
            "sokak_isyeri_hane": {secenek: 10 for secenek in sokak_isyeri_hane_secenekleri},
            "cadde": {cadde: 10 for cadde in cadde_secenekleri}
        }
    
    return kotalar

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
    
    # Önceki işlem varsa temizle
    if user_id in update_progress:
        del update_progress[user_id]
    
    # Yeni işlem başlat
    update_progress[user_id] = {"kategori_index": 0, "kategori": None, "secenek": None, "secenek_index": 0}
    
    print(f"🚀 updatekota başlatıldı: user_id={user_id}, progress={update_progress[user_id]}")
    
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
    
    # İl seçimi özel işlem
    if kategori == "il":
        await update_or_message.reply_text(
            f"📝 **{kategori_adi_formatla(kategori)}** kategorisi\n\n"
            f"Hangi ilin kotalarını güncellemek istiyorsunuz?\n"
            f"İller: {', '.join(iller)}\n\n"
            f"İl adını girin:"
        )
        return UPDATE_KOTA
    
    # İl seçimi yapılmış mı kontrol et
    if "secilen_il" not in update_progress[user_id]:
        await update_or_message.reply_text("❌ Önce il seçimi yapmalısınız.")
        return ConversationHandler.END
    
    secilen_il = update_progress[user_id]["secilen_il"]
    secenekler = list(kotalar[secilen_il][kategori].keys())
    
    if not secenekler:
        await update_or_message.reply_text(f"{kategori_adi_formatla(kategori)} kategorisinde hiç seçenek yok, atlanıyor...")
        update_progress[user_id]["kategori_index"] += 1
        update_progress[user_id]["secenek_index"] = 0
        # Recursive call yerine döngü kullan
        return await ask_next_kota(update_or_message, user_id)
    
    # Seçenek index'ini kontrol et
    secenek_idx = update_progress[user_id].get("secenek_index", 0)
    
    if secenek_idx >= len(secenekler):
        # Bu kategorideki tüm seçenekler tamamlandı, sonraki kategoriye geç
        update_progress[user_id]["kategori_index"] += 1
        update_progress[user_id]["secenek_index"] = 0
        # Recursive call yerine döngü kullan
        return await ask_next_kota(update_or_message, user_id)
    
    # Şu anki seçeneği göster
    secenek = secenekler[secenek_idx]
    mevcut_kota = kotalar[secilen_il][kategori][secenek]
    
    await update_or_message.reply_text(
        f"📝 **{secilen_il}** - **{kategori_adi_formatla(kategori)}** kategorisi - **{secenek}**\n"
        f"Şu anki kota: **{mevcut_kota}**\n\n"
        f"Yeni kotayı girin:"
    )
    
    return UPDATE_KOTA  # Devam etmek için UPDATE_KOTA döndür

async def update_kota_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"🔍 update_kota_process çağrıldı")
    print(f"🔍 update type: {type(update)}")
    print(f"🔍 update.message: {update.message}")
    
    user_id = update.message.from_user.id
    print(f"🔍 user_id: {user_id}")
    print(f"🔍 ADMIN_ID: {ADMIN_ID}")
    print(f"🔍 update_progress: {update_progress}")
    
    if user_id != ADMIN_ID or user_id not in update_progress:
        await update.message.reply_text("❌ Yetkiniz yok veya işlem başlatmadınız.")
        return ConversationHandler.END
    
    idx = update_progress[user_id]["kategori_index"]
    kategori = update_progress[user_id]["kategori"]
    
    print(f"🔍 kategori: {kategori}")
    
    text = update.message.text.strip()
    print(f"🔍 text: {text}")
    
    # İl seçimi özel işlem
    if kategori == "il":
        if text not in iller:
            await update.message.reply_text(f"❌ Geçersiz il. Lütfen şunlardan birini seçin: {', '.join(iller)}")
            return UPDATE_KOTA
        
        update_progress[user_id]["secilen_il"] = text
        await update.message.reply_text(f"✅ İl seçildi: **{text}**\n\nŞimdi bu ilin kotalarını güncelleyeceğiz.")
        
        # Sonraki kategoriye geç
        result = await ask_next_kota(update.message, user_id)
        if result == ConversationHandler.END:
            return ConversationHandler.END
        return UPDATE_KOTA
    
    # Diğer kategoriler için
    if "secilen_il" not in update_progress[user_id]:
        await update.message.reply_text("❌ Önce il seçimi yapmalısınız.")
        return ConversationHandler.END
    
    secilen_il = update_progress[user_id]["secilen_il"]
    secenekler = list(kotalar[secilen_il][kategori].keys())
    secenek_idx = update_progress[user_id].get("secenek_index", 0)
    
    print(f"🔍 secilen_il: {secilen_il}")
    print(f"🔍 secenekler: {secenekler}")
    print(f"🔍 secenek_idx: {secenek_idx}")
    
    try:
        yeni_kota = int(text)
        print(f"🔍 yeni_kota: {yeni_kota}")
    except ValueError:
        await update.message.reply_text("❌ Lütfen sadece sayı giriniz.")
        return UPDATE_KOTA
    
    # Şu anki seçeneği al
    secenek = secenekler[secenek_idx]
    
    # Kotayı güncelle
    kotalar[secilen_il][kategori][secenek] = yeni_kota
    kotalari_kaydet()
    
    await update.message.reply_text(
        f"✅ **{secilen_il}** - **{kategori_adi_formatla(kategori)}** - **{secenek}** kotası **{yeni_kota}** olarak güncellendi."
    )
    
    # Seçenek index'ini artır
    update_progress[user_id]["secenek_index"] = secenek_idx + 1
    
    # Sonraki seçeneğe veya kategoriye geç
    result = await ask_next_kota(update.message, user_id)
    
    # ask_next_kota fonksiyonundan dönen değeri kontrol et
    if result == ConversationHandler.END:
        print(f"✅ updatekota tamamlandı: user_id={user_id}")
        return ConversationHandler.END
    
    print(f"🔄 updatekota devam ediyor: user_id={user_id}, kategori_index={update_progress[user_id]['kategori_index']}")
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
    
    # İlk kategori (il) ise özel işlem
    if kategori == "il":
        await show_il_buttons(message_obj, user_id)
        return
    
    # Kullanıcının seçtiği ili al
    if user_id not in user_secimleri or "il" not in user_secimleri[user_id]:
        await message_obj.reply_text("❌ Önce il seçimi yapmalısınız.")
        return
    
    secilen_il = user_secimleri[user_id]["il"]
    secenekler = kotalar[secilen_il][kategori]
    
    print(f"Kategori: {kategori}, İl: {secilen_il}, Seçenekler: {list(secenekler.keys())}")
    
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
        text=f"📊 **{secilen_il}** - {kategori_adi_formatla(kategori)} seçiniz:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_il_buttons(message_obj, user_id):
    """İl seçim butonlarını gösterir"""
    keyboard = []
    for i, il in enumerate(iller, 1):
        label = f"{i}. {il}"
        callback_data = f"sel_il_{i}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    
    await message_obj.reply_text(
        text="🏙️ **Nerede Yaşıyorsunuz?**\n\nLütfen yaşadığınız ili seçiniz:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def complete_survey(message_obj, user_id):
    """Anketi tamamlar ve kotaları günceller"""
    if user_id not in user_secimleri:
        await message_obj.reply_text("❌ Anket verisi bulunamadı")
        return
    
    secimler = user_secimleri[user_id]
    secilen_il = secimler.get("il")
    
    if not secilen_il:
        await message_obj.reply_text("❌ İl seçimi bulunamadı")
        return
    
    # Seçilen ilin kotalarını güncelle
    for kategori, secim in secimler.items():
        if kategori != "il" and kategori in kotalar[secilen_il] and secim in kotalar[secilen_il][kategori]:
            kotalar[secilen_il][kategori][secim] -= 1
    
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
    
    for il in iller:
        mesaj += f"🏙️ **{il.upper()}**\n"
        mesaj += "=" * 20 + "\n\n"
        
        for kategori in kategori_sirasi[1:]:  # il hariç diğer kategoriler
            mesaj += f"🔹 **{kategori_adi_formatla(kategori).upper()}**\n"
            
            for secenek, kalan in kotalar[il][kategori].items():
                # Kota durumuna göre renk belirle (0 = kırmızı)
                if kalan <= 0:
                    color = "🔴"  # Kırmızı (0 ve altı)
                elif kalan <= 5:
                    color = "🟡"  # Sarı (1-5 arası)
                else:
                    color = "🟢"  # Yeşil (6 ve üstü)
                
                # Alt alta format: renk + seçenek adı + kota sayısı (kalın)
                mesaj += f"{color}{secenek}\n**({kalan})**\n\n"
            
            mesaj += "---------------------------\n\n"
        
        mesaj += "\n" + "=" * 30 + "\n\n"
    
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
        
        for il in iller:
            mesaj += f"🏙️ **{il.upper()}**\n"
            mesaj += "=" * 20 + "\n\n"
            
            for kategori in kategori_sirasi[1:]:  # il hariç diğer kategoriler
                mesaj += f"🔹 **{kategori_adi_formatla(kategori).upper()}**\n"
                
                for secenek, kalan in kotalar[il][kategori].items():
                    # Kota durumuna göre renk belirle (0 = kırmızı)
                    if kalan <= 0:
                        color = "🔴"  # Kırmızı (0 ve altı)
                    elif kalan <= 5:
                        color = "🟡"  # Sarı (1-5 arası)
                    else:
                        color = "🟢"  # Yeşil (6 ve üstü)
                    
                    # Alt alta format: renk + seçenek adı + kota sayısı (kalın)
                    mesaj += f"{color}{secenek}\n**({kalan})**\n\n"
                
                mesaj += "---------------------------\n\n"
            
            mesaj += "\n" + "=" * 30 + "\n\n"
        
        # Gruba mesaj gönder (context.bot kullan)
        # Bu fonksiyon context olmadan çağrıldığı için global app kullan
        global bot_app
        await bot_app.bot.send_message(chat_id=GROUP_CHAT_ID, text=mesaj, parse_mode='Markdown')
        print(f"✅ Güncel kotalar gruba gönderildi: {GROUP_CHAT_ID}")
        
    except Exception as e:
        print(f"❌ Gruba mesaj gönderme hatası: {e}")
        # Hata olursa da anketi tamamlamaya devam et

async def show_kota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Güncel kotaları güzel alt alta formatında hazırla
    mesaj = "📊 **GÜNCEL KOTALAR** 📊\n\n"
    
    for il in iller:
        mesaj += f"🏙️ **{il.upper()}**\n"
        mesaj += "=" * 20 + "\n\n"
        
        for kategori in kategori_sirasi[1:]:  # il hariç diğer kategoriler
            mesaj += f"🔹 **{kategori_adi_formatla(kategori).upper()}**\n"
            
            for secenek, kalan in kotalar[il][kategori].items():
                # Kota durumuna göre renk belirle (0 = kırmızı)
                if kalan <= 0:
                    color = "🔴"  # Kırmızı (0 ve altı)
                elif kalan <= 5:
                    color = "🟡"  # Sarı (1-5 arası)
                else:
                    color = "🟢"  # Yeşil (6 ve üstü)
                
                # Alt alta format: renk + seçenek adı + kota sayısı (kalın)
                mesaj += f"{color}{secenek}\n**({kalan})**\n\n"
            
            mesaj += "---------------------------\n\n"
        
        mesaj += "\n" + "=" * 30 + "\n\n"
    
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
        
        # Callback data formatı: sel_KATEGORI_INDEX veya sel_il_INDEX
        # Örnek: sel_il_1, sel_cinsiyet_2, sel_yas_3
        
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
        
        # İl seçimi özel işlem
        if kategori == "il":
            if secenek_index >= len(iller):
                await query.message.reply_text(f"❌ İl index'i geçersiz: {secenek_index + 1}")
                return
            
            secilen_il = iller[secenek_index]
            print(f"Seçilen il: {secilen_il}")
            
            # Seçimi kaydet
            if user_id not in user_secimleri:
                user_secimleri[user_id] = {}
            user_secimleri[user_id][kategori] = secilen_il
            
            print(f"İl seçimi kaydedildi: {user_secimleri[user_id]}")
            
            # Sonraki kategoriyi göster
            current_index = kategori_sirasi.index(kategori)
            next_index = current_index + 1
            
            await show_category_buttons(query.message, user_id, next_index)
            return
        
        # Diğer kategoriler için
        if user_id not in user_secimleri or "il" not in user_secimleri[user_id]:
            await query.message.reply_text("❌ Önce il seçimi yapmalısınız.")
            return
        
        secilen_il = user_secimleri[user_id]["il"]
        
        if secilen_il not in kotalar or kategori not in kotalar[secilen_il]:
            await query.message.reply_text(f"❌ Kategori bulunamadı: {kategori}")
            return
        
        secenekler = list(kotalar[secilen_il][kategori].keys())
        if secenek_index >= len(secenekler):
            await query.message.reply_text(f"❌ Seçenek index'i geçersiz: {secenek_index + 1}")
            return
        
        secenek = secenekler[secenek_index]
        print(f"Seçilen seçenek: {secenek}")
        
        # Seçimi kaydet
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
    global bot_app
    
    # Eğer PAUSE_BOT true ise bot'u çalıştırma
    if PAUSE_BOT:
        print("⏸️ Bot duraklatıldı (PAUSE_BOT=true)")
        return None
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    # Bot menü butonlarını ayarla
    bot_app.post_init = set_bot_menu
    
    # Handler'ları ekle
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(button_callback))
    bot_app.add_handler(CommandHandler("help", help))
    bot_app.add_handler(CommandHandler("chatid", get_chat_id))
    bot_app.add_handler(CommandHandler("showkota", show_kota))
    bot_app.add_handler(CommandHandler("status", show_status))
    bot_app.add_handler(CommandHandler("yeni_anket", yeni_anket))
    
    # Admin komutları
    bot_app.add_handler(CommandHandler("addkota", add_kota))
    bot_app.add_handler(CommandHandler("addkategori", add_kategori))
    bot_app.add_handler(CommandHandler("delkota", del_kota))
    bot_app.add_handler(CommandHandler("delkategori", del_kategori))
    
    # ConversationHandler ile güncelleme
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("updatekota", update_kota_start)],
        states={
            UPDATE_KOTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_kota_process)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    bot_app.add_handler(conv_handler)

    print("Bot çalışıyor...")
    
    # Geçici olarak polling mode'a geri dön
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)
    
    print("✅ Bot polling mode'da çalışıyor")
    
    # Bot'u çalışır durumda tut
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Bot durduruluyor...")
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
    
    return bot_app

# Flask health check endpoint'i
@web_app.route('/')
def health_check():
    return "OK"

# Railway health check için /health endpoint'i de ekle
@web_app.route('/health')
def health_check_alt():
    return "OK"

# Webhook test endpoint'i
@web_app.route('/test')
def test_endpoint():
    try:
        ensure_bot_initialized()
        return {"status": "OK", "bot_initialized": bot_app is not None, "commit": "e7be69f"}, 200
    except Exception as e:
        return {"status": "Error", "error": str(e)}, 500

# Debug endpoint'i
@web_app.route('/debug')
def debug_endpoint():
    try:
        ensure_bot_initialized()
        
        debug_info = {
            "status": "OK",
            "bot_initialized": bot_app is not None,
            "bot_token_set": bool(BOT_TOKEN),
            "admin_id": ADMIN_ID,
            "group_chat_id": GROUP_CHAT_ID,
            "pause_bot": PAUSE_BOT,
            "kotalar_count": len(kotalar),
            "kategori_sirasi": kategori_sirasi,
            "update_progress_count": len(update_progress),
            "user_secimleri_count": len(user_secimleri),
            "user_gruplari_count": len(user_gruplari),
            "environment": {
                "VERCEL": os.environ.get("VERCEL", "Not set"),
                "BOT_TOKEN": "Set" if os.environ.get("BOT_TOKEN") else "Not set",
                "ADMIN_ID": os.environ.get("ADMIN_ID", "Not set"),
                "GROUP_CHAT_ID": os.environ.get("GROUP_CHAT_ID", "Not set"),
                "PAUSE_BOT": os.environ.get("PAUSE_BOT", "Not set")
            }
        }
        
        return debug_info, 200
    except Exception as e:
        return {"status": "Error", "error": str(e)}, 500

# Webhook test endpoint'i (POST ile test)
@web_app.route('/test-webhook', methods=['POST'])
def test_webhook():
    try:
        print(f"🧪 Test webhook çağrıldı")
        print(f"🧪 Headers: {dict(request.headers)}")
        print(f"🧪 Data: {request.get_json()}")
        
        # Bot'u initialize et
        ensure_bot_initialized()
        
        # Test update oluştur
        from telegram import Update, Message, User, Chat
        
        # Mock user ve chat
        user = User(id=6472876244, first_name="Test", is_bot=False)
        chat = Chat(id=6472876244, type="private")
        message = Message(message_id=1, date=1234567890, chat=chat, from_user=user, text="/start")
        
        # Mock update
        update = Update(update_id=1, message=message)
        
        print(f"🧪 Mock update oluşturuldu: {update}")
        
        # Update'i işle
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(process_update(update))
            print(f"🧪 Test update işlendi: {result}")
        finally:
            loop.close()
        
        return {"status": "OK", "test_completed": True}, 200
    except Exception as e:
        print(f"❌ Test webhook hatası: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "Error", "error": str(e)}, 500

# Telegram webhook endpoint'i
@web_app.route('/webhook', methods=['POST'])
def webhook():
    try:
        print(f"🔔 Webhook çağrıldı: {request.method}")
        print(f"🔔 Headers: {dict(request.headers)}")
        print(f"🔔 Content-Type: {request.headers.get('Content-Type', 'Not set')}")
        
        # Bot'u initialize et
        ensure_bot_initialized()
        
        data = request.get_json()
        print(f"🔔 Webhook data: {data}")
        
        if data:
            update = Update.de_json(data, bot_app.bot)
            print(f"🔔 Update parsed: {update}")
            print(f"🔔 Update type: {type(update)}")
            
            # Update'i işle
            result = process_update_sync(update)
            print(f"✅ Update işlendi, result: {result}")
        else:
            print("⚠️ Webhook data boş")
            
        return "OK", 200
    except Exception as e:
        print(f"❌ Webhook hatası: {e}")
        import traceback
        traceback.print_exc()
        return "Error", 500

# Sync wrapper for process_update
def process_update_sync(update):
    """Update'i sync olarak işler"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(process_update(update))
            return result
        finally:
            loop.close()
    except Exception as e:
        print(f"❌ Sync update işleme hatası: {e}")
        import traceback
        traceback.print_exc()
        return None

# Bot'u lazy-init eden yardımcı
def ensure_bot_initialized():
    global bot_app
    if bot_app is not None:
        print(f"✅ Bot zaten initialize edilmiş")
        return
    
    print(f"🚀 Bot initialize ediliyor...")
    
    # Minimal init: handler'ları kur
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.post_init = set_bot_menu
    
    # Handler'ları ekle
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(button_callback))
    bot_app.add_handler(CommandHandler("help", help))
    bot_app.add_handler(CommandHandler("chatid", get_chat_id))
    bot_app.add_handler(CommandHandler("showkota", show_kota))
    bot_app.add_handler(CommandHandler("status", show_status))
    bot_app.add_handler(CommandHandler("yeni_anket", yeni_anket))
    bot_app.add_handler(CommandHandler("addkota", add_kota))
    bot_app.add_handler(CommandHandler("addkategori", add_kategori))
    bot_app.add_handler(CommandHandler("delkota", del_kota))
    bot_app.add_handler(CommandHandler("delkategori", del_kategori))
    
    # ConversationHandler ekle
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("updatekota", update_kota_start)],
        states={
            UPDATE_KOTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_kota_process)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    bot_app.add_handler(conv_handler)
    
    print(f"✅ Handler'lar eklendi")
    
    # Initialize app to be able to process updates
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot_app.initialize())
        print(f"✅ Bot initialize edildi")
    except Exception as e:
        print(f"❌ Lazy init initialize hatası: {e}")
        import traceback
        traceback.print_exc()

# Update'i işle
async def process_update(update):
    try:
        print(f"🔄 process_update başladı: {update}")
        print(f"🔄 Update type: {type(update)}")
        
        if hasattr(update, 'message') and update.message:
            print(f"🔄 Message from user: {update.message.from_user.id}")
            print(f"🔄 Message text: {update.message.text}")
        
        # Update'i bot'a gönder
        result = await bot_app.process_update(update)
        print(f"✅ process_update tamamlandı: {result}")
        return result
    except Exception as e:
        print(f"❌ Update işleme hatası: {e}")
        import traceback
        traceback.print_exc()
        raise

# Flask health check thread'i
def run_flask_server():
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

# Vercel için webhook setup
async def setup_webhook():
    """Vercel'de webhook kurar"""
    global bot_app
    if bot_app is None:
        ensure_bot_initialized()
    
    try:
        # Webhook URL'ini ayarla
        webhook_url = os.environ.get("WEBHOOK_URL")
        if webhook_url:
            # Webhook'u temizle ve yeniden kur
            await bot_app.bot.delete_webhook()
            await bot_app.bot.set_webhook(url=webhook_url + "/webhook")
            print(f"✅ Webhook kuruldu: {webhook_url}/webhook")
            
            # Webhook bilgilerini kontrol et
            webhook_info = await bot_app.bot.get_webhook_info()
            print(f"🔍 Webhook bilgileri: {webhook_info}")
        else:
            print("⚠️ WEBHOOK_URL environment variable bulunamadı")
    except Exception as e:
        print(f"❌ Webhook kurulum hatası: {e}")
        import traceback
        traceback.print_exc()

# Webhook setup endpoint'i
@web_app.route('/setup-webhook')
def setup_webhook_endpoint():
    try:
        ensure_bot_initialized()
        webhook_url = os.environ.get("WEBHOOK_URL")
        if not webhook_url:
            return {"status": "Error", "error": "WEBHOOK_URL not set"}, 400
        # Run async setup in a fresh loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(setup_webhook())
            # Fetch webhook info to return
            webhook_info = loop.run_until_complete(bot_app.bot.get_webhook_info())
        finally:
            loop.close()
        return {"status": "OK", "webhook_url": f"{webhook_url}/webhook", "webhook_info": webhook_info.to_dict()}, 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "Error", "error": str(e)}, 500

# Bot başlatıldığında menü butonlarını ayarla
if __name__ == "__main__":
    print("🚀 Bot başlatılıyor...")
    
    try:
        # Vercel'de çalışıyorsa webhook mode, local'de polling mode
        if os.environ.get("VERCEL"):
            print("🌐 Vercel'de çalışıyor - webhook mode")
            # Vercel'de bot'u initialize et ve webhook kur
            ensure_bot_initialized()
            # Webhook'u asenkron olarak kur
            if os.environ.get("WEBHOOK_URL"):
                # Webhook kurulumu için bir kez çalıştır
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(setup_webhook())
                loop.close()
        else:
            print("🏠 Local'de çalışıyor - polling mode")
            # Flask server'ı ayrı thread'de başlat
            flask_thread = threading.Thread(target=run_flask_server, daemon=True)
            flask_thread.start()
            print("✅ Flask server başlatıldı")
            
            # Bot'u polling mode'da başlat
            print("✅ Bot polling mode'da başlatıldı")
            
            # Bot'u çalıştır
            asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n🛑 Bot durduruldu")
    except Exception as e:
        print(f"❌ Bot hatası: {e}")
        import traceback
        traceback.print_exc()
