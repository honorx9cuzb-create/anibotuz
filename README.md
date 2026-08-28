# 🎌 Ani — Telegram Anime Bot

Professional production-ready Telegram Anime Bot.  
**Faqat Python standart kutubxonasidan** foydalaniladi — hech qanday `pip install` kerak emas.

---

## 📋 Talablar

- Python 3.9+
- Telegram Bot Token ([BotFather](https://t.me/BotFather) dan oling)
- cPanel / VPS / SSH kirish

---

## ⚡ Tez ishga tushirish

### 1. Bot tokenini sozlang

`config.json` faylini oching va `bot_token` maydonini to'ldiring:

```json
{
  "bot_token": "123456789:AAF-your-real-token-here",
  "admin_ids": [YOUR_TELEGRAM_ID],
  "bot_username": "YourBotUsername"
}
```

> **Muhim:** `bot_username` — `@` belgisisiz yozing (masalan: `AniAnimeBot`)

### 2. Python versiyasini tekshiring

```bash
cd ~/ani
python --version
```

`Python 3.9.x` yoki undan yuqori bo'lishi kerak.

### 3. Botni ishga tushiring

```bash
python bot.py
```

Shunday ko'rinadi:

```
✅  Bot ishga tushdi: @YourAnimeBot (Ani Bot)
📋  Loglar: logs/bot.log
🛑  To'xtatish uchun: Ctrl+C
```

---

## 🗂 Loyiha tuzilishi

```
ani/
├── bot.py          ← Asosiy ishga tushirish fayli
├── api.py          ← Telegram API client (urllib)
├── config.py       ← Konfiguratsiya loader
├── database.py     ← SQLite3 ma'lumotlar bazasi
├── handlers.py     ← Xabar va callback ishlovchilari
├── keyboards.py    ← Inline va Reply klaviaturalar
├── admin.py        ← Admin panel logic
├── payments.py     ← Premium va balans tizimi
├── utils.py        ← Yordamchi funksiyalar
├── config.json     ← Sozlamalar fayli
│
├── data/
│   ├── anime.db    ← SQLite ma'lumotlar bazasi (auto yaratiladi)
│   ├── users.json  ← Placeholder
│   ├── anime.json  ← Placeholder
│   ├── channels.json
│   ├── payments.json
│   └── settings.json
│
├── logs/
│   └── bot.log     ← Log fayli
│
├── public/
│   └── index.html  ← Veb sahifa
│
└── tmp/            ← Vaqtinchalik fayllar
```

---

## ⚙️ config.json parametrlari

| Kalit | Tavsif | Standart |
|-------|--------|---------|
| `bot_token` | BotFather dan olingan token | **Majburiy** |
| `admin_ids` | Admin Telegram ID lari ro'yxati | **Majburiy** |
| `bot_username` | Bot username (@ siz) | **Majburiy** |
| `referral_bonus` | Referal uchun bonus (UZS) | `1000` |
| `welcome_bonus` | Yangi foydalanuvchi bonusi (UZS) | `1000` |
| `premium_prices` | Premium reja narxlari | `{"7":5000,"30":15000,"365":100000}` |
| `polling_timeout` | Long-polling timeout (soniya) | `30` |
| `retry_delay` | Xatolikda kutish vaqti (soniya) | `5` |
| `max_retries` | Maksimal qayta urinish | `3` |
| `pagination_size` | Sahifadagi elementlar soni | `8` |
| `broadcast_delay` | Broadcast orasidagi kutish (soniya) | `0.05` |
| `log_level` | Log darajasi | `INFO` |

---

## 👑 Admin buyruqlari

| Buyruq | Tavsif |
|--------|--------|
| `/admin` | Admin panelni ochish |
| `/stats` | Statistika ko'rish |
| `/users` | Foydalanuvchi qidirish |
| `/broadcast` | Barcha foydalanuvchilarga xabar |
| `/anime` | Katalogni ko'rish |

---

## 🤖 Bot funksiyalari

### Foydalanuvchi uchun

| Tugma | Tavsif |
|-------|--------|
| 🔎 Anime qidirish | Nom bo'yicha qidirish |
| 🔢 ID orqali qidirish | ID bo'yicha topish |
| 📚 Katalog | Barcha animeni sahifalab ko'rish |
| ⭐ Sevimlilar | Saqlangan animeler |
| 👤 Profil | Foydalanuvchi ma'lumotlari |
| 💰 Balans | Joriy balans va referal havola |
| 💎 Premium | Premium sotib olish |
| 🎁 Referal | Referal tizimi |

### Admin uchun

- ➕ Anime qo'shish (bosqichma-bosqich)
- ➕ Qism qo'shish (video file_id saqlanadi)
- ✏️ Anime tahrirlash
- 🗑 Anime o'chirish (tasdiqlash bilan)
- 👥 Foydalanuvchi boshqaruvi
- 📊 Statistika
- 📢 Kanal obuna majburiyati
- 💰 Balans boshqaruvi
- 💎 Premium berish
- ⚙️ Narxlarni sozlash
- 📢 Broadcast

---

## 💎 Premium tizimi

Premium narxlarni admin paneldan o'zgartirish mumkin:

```
⚙️ Sozlamalar → price:30:20000
```

Format: `price:<kunlar>:<narx_uzs>`

---

## 📢 Kanal obuna tizimi

1. `/admin` → 📢 Kanallar → ➕ Kanal qo'shish
2. Kanal ID sini kiriting: `@kanalUsername` yoki `-1001234567890`
3. Bot har bir foydalanuvchini tekshiradi

---

## 🎬 Anime va qism qo'shish

### Anime qo'shish:
1. `/admin` → ➕ Anime qo'shish
2. Bosqichma-bosqich ma'lumot kiriting

### Qism qo'shish:
1. `/admin` → ➕ Qism qo'shish
2. Anime ID kiriting
3. Qism raqami va sarlavha
4. **Video faylni yuboring** — bot `file_id` ni saqlaydi

> ⚠️ Video server ga yuklanmaydi. Faqat Telegram `file_id` saqlanadi.

---

## 🔁 cPanel da doimiy ishlash (nohup)

```bash
cd ~/ani
nohup python bot.py > /dev/null 2>&1 &
echo $! > bot.pid
```

To'xtatish:
```bash
kill $(cat ~/ani/bot.pid)
```

---

## 📊 Log fayli

```bash
tail -f logs/bot.log
```

---

## 🔒 Xavfsizlik

- Bot token faqat `config.json` da saqlanadi
- Barcha SQL so'rovlar parametrlashtirilgan
- HTML escape qilinadi
- Admin ID lari `config.json` da belgilanadi
- Duplicate referal oldini olish mavjud
- Unique transaction ID lar

---

## ❌ Tez-tez uchraydigan muammolar

**Bot ishga tushmaydi:**
```bash
python --version   # 3.9+ bo'lishi kerak
cat config.json    # token to'g'ri yozilganmi?
```

**"bot_token is not set" xatosi:**  
`config.json` da `bot_token` ni to'g'ri token bilan almashtiring.

**Database xatosi:**  
`data/` papkasi mavjudligini tekshiring. Bot uni avtomatik yaratadi.

**Kanal tekshiruvi ishlamayapti:**  
Bot kanalda **administrator** bo'lishi kerak.

---

## 📦 Tashqi kutubxonalar

```
# Tashqi kutubxona kerak emas!
# Faqat Python 3.9+ standart kutubxonasi ishlatiladi.
```

---

*Ani Bot — @YourAnimeBot*
