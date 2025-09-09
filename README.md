# 📧➡️📱 SMTP-Telegram мост

![Build Status](https://github.com/ВАШЕ_ИМЯ/smtp-telegram-bridge/workflows/Build%20Windows%20EXE/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-blue.svg)

**Автоматическая пересылка email отчетов из кассовых программ в Telegram**

## 🎯 Что это?

Программа создает локальный SMTP сервер, который:
- ✅ Принимает письма от кассовых систем
- ✅ Пересылает содержимое в Telegram чат/группу  
- ✅ Работает в фоне (системный трей)
- ✅ Удобный GUI интерфейс
- ✅ Готовый EXE файл

## 📥 Скачать готовый EXE

### Последняя версия:
[![Download](https://img.shields.io/badge/📥_Скачать-EXE_файл-success?style=for-the-badge)](https://github.com/ВАШЕ_ИМЯ/smtp-telegram-bridge/releases/latest/download/SMTP-Telegram-Bridge.exe)

### Все релизы:
[📋 Посмотреть все версии](https://github.com/ВАШЕ_ИМЯ/smtp-telegram-bridge/releases)

## 🚀 Быстрый старт

1. **Скачайте** `SMTP-Telegram-Bridge.exe`
2. **Создайте Telegram бота:**
   - Откройте [@BotFather](https://t.me/botfather)
   - Отправьте `/newbot`
   - Сохраните **TOKEN**
3. **Получите Chat ID:**
   - Отправьте сообщение боту
   - Откройте: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Найдите `"chat":{"id":ВАШЕ_ID`
4. **Запустите программу** и введите настройки
5. **Настройте кассу** на `localhost:2525`

## ⚙️ Настройка кассовой программы

В настройках отправки отчетов укажите:
```
SMTP сервер: localhost
Порт: 2525
Логин: (пустой)
Пароль: (пустой)
Шифрование: Нет
```

## 📸 Скриншоты

### Главное окно:
![Интерфейс](https://via.placeholder.com/600x400/4a90e2/ffffff?text=Основной+интерфейс)

### Логи в реальном времени:
![Логи](https://via.placeholder.com/600x300/28a745/ffffff?text=Логи+работы)

## 🔧 Возможности

- 🖥️ **Графический интерфейс** - простая настройка
- 📱 **Telegram интеграция** - мгновенные уведомления  
- 🔄 **Работа в фоне** - системный трей
- 📋 **Логирование** - отслеживание работы
- ⚡ **Автозапуск** - запуск с программой
- 🧪 **Тест подключения** - проверка настроек
- 💾 **Сохранение настроек** - не нужно настраивать заново

## 🛠️ Сборка из исходников

### Требования:
- Python 3.7+
- Windows

### Установка:
```bash
git clone https://github.com/ВАШЕ_ИМЯ/smtp-telegram-bridge.git
cd smtp-telegram-bridge
pip install -r requirements.txt
```

### Запуск:
```bash
python smtp_telegram_bridge.py
```

### Сборка EXE:
```bash
pyinstaller --onefile --windowed smtp_telegram_bridge.py
```

## 📋 Системные требования

- **ОС:** Windows 7/10/11
- **RAM:** 50MB
- **Место:** 15MB
- **Сеть:** Интернет для Telegram

## 🔒 Безопасность

- ✅ Работает локально
- ✅ Не передает данные третьим лицам
- ✅ Токен Telegram хранится локально
- ✅ Открытый исходный код

## 📚 Поддерживаемые кассы

Программа работает с любой кассовой системой, которая умеет отправлять email:
- ✅ **Атол** (всех серий)
- ✅ **Штрих-М** 
- ✅ **Эвотор**
- ✅ **МойСклад**
- ✅ **1С:Розница**
- ✅ **Любые POS системы** с email

## 🆘 Поддержка

### Частые проблемы:
- [📖 Wiki с решениями](https://github.com/ВАШЕ_ИМЯ/smtp-telegram-bridge/wiki)
- [❓ FAQ](https://github.com/ВАШЕ_ИМЯ/smtp-telegram-bridge/wiki/FAQ)

### Сообщить о проблеме:
- [🐛 Создать Issue](https://github.com/ВАШЕ_ИМЯ/smtp-telegram-bridge/issues/new)

## 📄 Лицензия

MIT License - используйте свободно!

## 🤝 Участие в разработке

Приветствуются:
- 🐛 Сообщения об ошибках
- 💡 Предложения улучшений  
- 🔧 Pull requests
- ⭐ Звезды на GitHub

## 📊 Статистика

![GitHub stars](https://img.shields.io/github/stars/ВАШЕ_ИМЯ/smtp-telegram-bridge?style=social)
![GitHub forks](https://img.shields.io/github/forks/ВАШЕ_ИМЯ/smtp-telegram-bridge?style=social)
![GitHub issues](https://img.shields.io/github/issues/ВАШЕ_ИМЯ/smtp-telegram-bridge)

---

**💡 Сделано с ❤️ для упрощения работы с кассами**
