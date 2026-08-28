# 🎌 ANIME BOT PRO v4

Professional, production-ready Telegram Anime Bot.  
**Faqat Python standart kutubxonasidan** foydalaniladi — hech qanday `pip install` kerak emas.

---

## ✅ Xususiyatlar

| Kategoriya | Funksiyalar |
|-----------|------------|
| **Anime** | Qidirish, ID orqali qidirish, Katalog, Janrlar, Sahifalash |
| **Ko'rish** | Qismlar, Ko'rish tarixi, Davom ettirish, Telegram file_id |
| **Foydalanuvchi** | Profil, Sevimlilar, Kuzatish ro'yxati, XP/Daraja |
| **Ijtimoiy** | Baholash (1–5 yulduz), Sharhlar (moderatsiya), Ulashish |
| **Gamifikatsiya** | Kunlik bonus, Streak, Referal tizimi, Liderboard |
| **Premium** | 7/30/90/365 kunlik rejalar, Balansdan to'lov |
| **Admin** | CRUD anime/qism, Broadcast, Statistika, Backup, Export |
| **Xavfsizlik** | Rate limiting, Blok tizimi, Texnik ish rejimi |
| **Kanallar** | Majburiy obuna tekshiruvi |
| **Reklama** | Reklama tizimi (premium foydalanuvchilarga ko'rsatilmaydi) |

---

## 📋 Talablar

- Python **3.9+** (tashqi paketlarsiz)
- Telegram Bot Token ([BotFather](https://t.me/BotFather) dan oling)
- cPanel / aHOST / VPS / SSH kirish

---

## ⚡ Tez ishga tushirish

### 1. Fayllarni serverga yuklang

```bash
cd ~/ani
```

### 2. Python versiyasini tekshiring

```bash
python --version
# yoki
python3 --version
```

`Python 3.9.x` yoki undan yuqori bo'lishi kerak.  
Agar `python` ishlamasa `python3` ga almashtiring.

### 3. Konfiguratsiyani yarating

```bash
cp config.example.json config.json
```

`config.json` ni oching va to'ldiring:

```json
{
  "bot_token": "123456789:AAF-sizning-haqiqiy-tokeningiz",
  "bot_username": "SizningBotUsername",
  "admin_ids": [SIZNING_TELEGRAM_ID],
  "welcome_bonus": 1000,
  "referral_bonus": 1000
}
```

> ⚠️ **Muhim:** `config.json` **hech qachon** git repoga yuklanmasin.  
> `config.json` `.gitignore` da mavjud.

### 4. Botni ishga tushiring

```bash
python bot.py
```

Muvaffaqiyatli ishga tushganda:

```
=========================================
  ANIME BOT PRO v4
  Python: 3.9.x
  Dependencies: 0
  Database: SQLite
  Telegram API: Connected
  Status: ONLINE
=========================================

  Bot: @SizningBotUsername (Bot Name)
  Loglar: logs/bot.log
  To'xtatish: Ctrl+C
```

---

## 🔐 Token xavfsizligi

Agar bot token avval public repoga tushib qolgan bo'lsa:

1. **Darhol revoke qiling:** [@BotFather](https://t.me/BotFather) → Your Bot → API Token → **Revoke**
2. Yangi token oling
3. `config.json` ga yangi tokenni yozing
4. Token hech qachon kod ichida yoki `.py` faylida bo'lmasin

---

## 🗂 Loyiha tuzilishi

```
ani/
├── bot.py          ← Asosiy ishga tushirish fayli (python bot.py)
├── api.py          ← Telegram Bot API client (urllib, tashqi paket yo'q)
├── config.py       ← Konfiguratsiya loader
├── database.py     ← SQLite3 ma'lumotlar bazasi (auto yaratiladi)
├── handlers.py     ← Barcha xabar va callback ishlovchilari
├── keyboards.py    ← Inline va Reply klaviaturalar
├── admin.py        ← Admin panel (43 ta funksiya)
├── payments.py     ← Premium va balans tizimi
├── scheduler.py    ← Fon vazifalar (threading, APScheduler yo'q)
├── utils.py        ← Yordamchi funksiyalar, Rate limiter
├── config.example.json  ← Shablon (git da saqlanadi)
├── config.json          ← Haqiqiy sozlamalar (git IGNORE)
│
├── data/
│   ├── anime.db    ← SQLite bazasi (birinchi ishga tushirishda yaratiladi)
│   ├── backups/    ← Admin backup fayllari
│   └── exports/    ← CSV export fayllari
│
├── logs/
│   └── bot.log     ← Log fayli
│
├── public/
│   └── index.html  ← Statik veb sahifa (ixtiyoriy)
│
└── tmp/            ← Vaqtinchalik fayllar
```

---

## 🖥️ cPanel / aHOST da ishga tushirish

### SSH orqali oddiy ishga tushirish

```bash
cd ~/ani
python bot.py
```

### Fon rejimida (nohup bilan)

```bash
cd ~/ani
nohup python bot.py >> logs/bot.log 2>&1 &
echo $! > bot.pid
echo "Bot ishga tushdi, PID: $(cat bot.pid)"
```

### Botni to'xtatish

```bash
kill $(cat ~/ani/bot.pid)
```

### Log kuzatish

```bash
tail -f ~/ani/logs/bot.log
```

---

## ⚠️ cPanel Passenger haqida

cPanel Passenger **WSGI web application** uchun mo'ljallangan.  
Bu bot **Telegram long-polling** orqali ishlaydi — u WSGI web app emas.

**Noto'g'ri:** `passenger_wsgi.py` ga bot kodini yozish  
**To'g'ri:** SSH orqali `nohup python bot.py &` bilan ishga tushirish

Agar cPanel da Python App mavjud bo'lsa, `passenger_wsgi.py` faqat web health check uchun ishlatilishi mumkin — bot.py dan alohida.

---

## 👑 Admin buyruqlari

| Buyruq | Tavsif |
|--------|--------|
| `/admin` | Admin panelni ochish |
| `/stats` | Statistika ko'rish |
| `/broadcast` | Barcha foydalanuvchilarga xabar |

---

## 🎬 Anime qo'shish

1. `/admin` → 🎬 Anime → ➕ Anime qo'shish
2. Bosqichma-bosqich ma'lumot kiriting
3. Tasdiqlang

## 📺 Qism qo'shish

1. `/admin` → 📺 Qismlar → ➕ Qism qo'shish
2. Anime ID kiriting
3. Qism raqami va sarlavha kiriting
4. **Video faylni Telegram video sifatida yuboring**

> ⚠️ Video serverga yuklanmaydi. Bot faqat Telegram `file_id` ni saqlaydi.  
> Video Telegram serverlarida saqlanadi va Telegram CDN orqali yetkaziladi.

---

## 💎 Premium tizimi

Premium narxlarni admin paneldan o'zgartirish:

1. `/admin` → ⚙️ Sozlamalar
2. Kiriting: `price:30:20000` (30 kunlik narxni 20 000 UZS qilish)

Format: `price:<kunlar>:<narx_uzs>`

---

## 📢 Kanal obuna tizimi

1. `/admin` → 📢 Kanallar → ➕ Kanal qo'shish
2. Kanal ID: `@kanalUsername` yoki `-1001234567890`
3. Bot foydalanuvchini har safar tekshiradi
4. Bot kanalda **administrator** bo'lishi shart

---

## ⚙️ config.json parametrlari

| Kalit | Tavsif | Standart |
|-------|--------|---------|
| `bot_token` | BotFather token | **Majburiy** |
| `admin_ids` | Admin Telegram ID lari | **Majburiy** |
| `bot_username` | Bot username (@ siz) | **Majburiy** |
| `welcome_bonus` | Yangi foydalanuvchi bonusi | `1000` |
| `referral_bonus` | Referal bonusi | `1000` |
| `premium_prices` | Premium reja narxlari | `{"7":5000,...}` |
| `polling_timeout` | Long-polling timeout (soniya) | `30` |
| `retry_delay` | Xatolikda kutish (soniya) | `5` |
| `max_retries` | Maksimal qayta urinish | `3` |
| `pagination_size` | Sahifadagi elementlar | `8` |
| `broadcast_delay` | Broadcast orasidagi pauza | `0.05` |
| `log_level` | Log darajasi | `INFO` |
| `maintenance_mode` | Texnik ish rejimi | `false` |

---

## 🔒 Xavfsizlik

- Bot token faqat `config.json` da, hech qachon kodda emas
- Barcha SQL so'rovlar parametrlashtirilgan (SQL injection yo'q)
- HTML xavfsiz escape qilinadi
- Admin ID lari `config.json` da belgilanadi
- Duplicate referal oldini olish
- Rate limiting (spam himoyasi)
- Unique transaction ID lar (to'lov dubliklari oldini olish)

---

## ❌ Tez-tez uchraydigan muammolar

**Bot ishga tushmaydi — Python versiya xatosi:**
```bash
python --version    # 3.9+ kerak
python3 --version   # yoki python3 ishlatib ko'ring
```

**"config.json topilmadi":**
```bash
cp config.example.json config.json
# Keyin config.json ni tahrirlang
```

**"bot_token o'rnatilmagan":**  
`config.json` ichida `bot_token` ni haqiqiy token bilan to'ldiring.

**Database xatosi:**  
Bot `data/` papkasini avtomatik yaratadi. Agar xatolik bo'lsa:
```bash
mkdir -p ~/ani/data ~/ani/logs ~/ani/tmp
```

**Kanal tekshiruvi ishlamayapti:**  
Bot kanalda **administrator** bo'lishi kerak.

**Video yuborilmayapti:**  
Video `file_id` Telegram da saqlanadi. Bot video fayllarini serverga yuklamaydi.  
Shuning uchun video faylning o'zi serverda bo'lmasligi normal.

---

## 📦 Tashqi kutubxonalar

```
# Hech qanday tashqi paket kerak emas!
# Faqat Python 3.9+ standart kutubxonasi ishlatiladi.
# pip install talab qilinmaydi.
```

---

*ANIME BOT PRO v4 — aHOST/cPanel uchun optimallashtirilgan*
