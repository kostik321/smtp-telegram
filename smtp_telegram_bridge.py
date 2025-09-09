#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import smtpd
import asyncore
import email
import requests
from email.header import decode_header
import logging
import json
import os
from datetime import datetime
import base64

CONFIG_FILE = "smtp_config.json"

class SMTPTelegramBridge:
    def __init__(self):
        self.server = None
        self.server_thread = None
        self.is_running = False
        self.config = self.load_config()
        
        # Настройка логирования
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('smtp_bridge.log', encoding='utf-8')
            ]
        )
        self.logger = logging.getLogger(__name__)

    def load_config(self):
        """Загрузка конфигурации"""
        default_config = {
            "telegram_token": "",
            "telegram_chat_id": "",
            "smtp_host": "localhost",
            "smtp_port": 2525,
            "auto_start": False
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            except:
                pass
        
        return default_config

    def save_config(self):
        """Сохранение конфигурации"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Ошибка сохранения конфигурации: {e}")

    def start_server(self):
        """Запуск SMTP сервера"""
        if self.is_running:
            return False
        
        if not self.config["telegram_token"] or not self.config["telegram_chat_id"]:
            return False
        
        try:
            self.server = TelegramSMTPServer(
                (self.config["smtp_host"], self.config["smtp_port"]),
                None,
                self.config["telegram_token"],
                self.config["telegram_chat_id"],
                self.logger
            )
            
            self.server_thread = threading.Thread(target=self._run_server, daemon=True)
            self.server_thread.start()
            
            self.is_running = True
            self.logger.info(f"SMTP сервер запущен на {self.config['smtp_host']}:{self.config['smtp_port']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска сервера: {e}")
            return False

    def _run_server(self):
        """Запуск asyncore loop в отдельном потоке"""
        try:
            asyncore.loop()
        except Exception as e:
            self.logger.error(f"Ошибка сервера: {e}")
            self.is_running = False

    def stop_server(self):
        """Остановка SMTP сервера"""
        if not self.is_running:
            return
        
        try:
            if self.server:
                self.server.close()
            asyncore.close_all()
            self.is_running = False
            self.logger.info("SMTP сервер остановлен")
        except Exception as e:
            self.logger.error(f"Ошибка остановки сервера: {e}")

class TelegramSMTPServer(smtpd.SMTPServer):
    def __init__(self, localaddr, remoteaddr, token, chat_id, logger):
        super().__init__(localaddr, remoteaddr, decode_data=False)
        self.token = token
        self.chat_id = chat_id
        self.logger = logger

    def smtp_AUTH(self, arg):
        """Обработка AUTH команды - принимаем любую аутентификацию"""
        try:
            self.logger.info("Получена команда AUTH, принимаем любые данные")
            
            if arg.startswith('PLAIN'):
                # AUTH PLAIN аутентификация
                return '334 '
            elif arg.startswith('LOGIN'):
                # AUTH LOGIN аутентификация  
                return '334 VXNlcm5hbWU6'  # "Username:" в base64
            else:
                # Неизвестный тип - тоже принимаем
                return '334 '
                
        except Exception as e:
            self.logger.error(f"Ошибка AUTH: {e}")
            return '535 Authentication failed'

    def smtp_HELO(self, arg):
        """Обработка HELO команды"""
        self.logger.info(f"HELO от {arg}")
        return '250 Hello'

    def smtp_EHLO(self, arg):
        """Обработка EHLO команды"""
        self.logger.info(f"EHLO от {arg}")
        response = ['250-Hello', '250-AUTH PLAIN LOGIN', '250 8BITMIME']
        return '\n'.join(response)

    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        """Обработка входящего email"""
        self.logger.info(f"Получено письмо от {mailfrom} для {rcpttos}")
        
        try:
            if isinstance(data, bytes):
                msg = email.message_from_bytes(data)
            else:
                msg = email.message_from_string(data)
            
            subject = self.decode_mime_words(msg.get('Subject', 'Без темы'))
            sender = self.decode_mime_words(msg.get('From', mailfrom))
            body = self.extract_body(msg)
            
            self.send_to_telegram(subject, sender, body)
            
        except Exception as e:
            self.logger.error(f"Ошибка обработки письма: {e}")

    def collect_incoming_data(self, data):
        """Переопределяем для обработки AUTH данных"""
        try:
            if hasattr(self, '_auth_stage'):
                # Обрабатываем данные аутентификации
                if self._auth_stage == 'username':
                    self.logger.info("Получен username для AUTH")
                    self._auth_stage = 'password'
                    self.push('334 UGFzc3dvcmQ6')  # "Password:" в base64
                    return
                elif self._auth_stage == 'password':
                    self.logger.info("Получен password для AUTH, аутентификация принята")
                    self.push('235 Authentication successful')
                    delattr(self, '_auth_stage')
                    return
            
            # Обычная обработка данных
            super().collect_incoming_data(data)
            
        except Exception as e:
            self.logger.error(f"Ошибка collect_incoming_data: {e}")
            super().collect_incoming_data(data)

    def found_terminator(self):
        """Переопределяем для обработки команд"""
        try:
            line = self._emptystring.join(self._buffer).decode('utf-8', errors='ignore')
            self._buffer = []
            
            # Обработка AUTH LOGIN по шагам
            if hasattr(self, '_auth_stage'):
                if self._auth_stage == 'start':
                    self.logger.info("AUTH LOGIN: запрос username")
                    self._auth_stage = 'username'
                    self.push('334 VXNlcm5hbWU6')  # "Username:" в base64
                    return
                elif self._auth_stage == 'username':
                    self.logger.info(f"AUTH LOGIN: получен username")
                    self._auth_stage = 'password'  
                    self.push('334 UGFzc3dvcmQ6')  # "Password:" в base64
                    return
                elif self._auth_stage == 'password':
                    self.logger.info("AUTH LOGIN: получен password, аутентификация успешна")
                    self.push('235 Authentication successful')
                    delattr(self, '_auth_stage')
                    return
            
            # Проверяем AUTH команды
            if line.upper().startswith('AUTH LOGIN'):
                self.logger.info("Начинаем AUTH LOGIN")
                self._auth_stage = 'start'
                self.push('334 VXNlcm5hbWU6')  # "Username:" в base64
                return
            elif line.upper().startswith('AUTH PLAIN'):
                self.logger.info("AUTH PLAIN - принимаем любые данные")
                self.push('235 Authentication successful')
                return
            
            # Обычная обработка команд
            super().found_terminator()
            
        except Exception as e:
            self.logger.error(f"Ошибка found_terminator: {e}")
            super().found_terminator()

    def decode_mime_words(self, s):
        """Декодирование MIME заголовков"""
        if not s:
            return s
        
        try:
            decoded_fragments = decode_header(s)
            decoded_string = ''
            
            for fragment, charset in decoded_fragments:
                if isinstance(fragment, bytes):
                    if charset:
                        decoded_string += fragment.decode(charset, errors='ignore')
                    else:
                        decoded_string += fragment.decode('utf-8', errors='ignore')
                else:
                    decoded_string += fragment
                    
            return decoded_string
        except:
            return str(s)

    def extract_body(self, msg):
        """Извлечение текста письма"""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            body = payload.decode(charset, errors='ignore')
                        else:
                            body = str(payload)
                        break
                    except:
                        body = str(part.get_payload())
                        break
        else:
            charset = msg.get_content_charset() or 'utf-8'
            try:
                payload = msg.get_payload(decode=True)
                if isinstance(payload, bytes):
                    body = payload.decode(charset, errors='ignore')
                else:
                    body = str(payload)
            except:
                body = str(msg.get_payload())
        
        return body.strip()

    def send_to_telegram(self, subject, sender, body):
        """Отправка сообщения в Telegram"""
        try:
            message = f"📧 *Отчет о продажах*\n\n"
            message += f"*От:* {sender}\n"
            message += f"*Тема:* {subject}\n"
            message += f"*Время:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            message += f"{'='*30}\n\n"
            
            if len(body) > 3500:
                body = body[:3500] + "\n\n... [сообщение обрезано]"
            
            message += body
            
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, data=payload, timeout=10)
            
            if response.status_code == 200:
                self.logger.info("✅ Сообщение отправлено в Telegram")
            else:
                self.logger.error(f"❌ Ошибка Telegram API: {response.text}")
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки в Telegram: {e}")

class SMTPBridgeGUI:
    def __init__(self):
        self.bridge = SMTPTelegramBridge()
        self.create_gui()
        
        if self.bridge.config.get("auto_start", False):
            self.start_server()

    def create_gui(self):
        """Создание GUI"""
        self.root = tk.Tk()
        self.root.title("SMTP-Telegram мост с AUTH")
        self.root.geometry("600x500")
        
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.create_settings_tab(notebook)
        self.create_logs_tab(notebook)
        
        self.status_var = tk.StringVar()
        self.status_var.set("Остановлено")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def create_settings_tab(self, notebook):
        """Вкладка настроек"""
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="Настройки")
        
        # Инструкция
        info_frame = ttk.LabelFrame(settings_frame, text="Настройки кассовой программы")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        info_text = tk.Text(info_frame, height=4, wrap=tk.WORD)
        info_text.pack(fill=tk.X, padx=5, pady=5)
        info_text.insert(tk.END, """В кассовой программе укажите:
SMTP сервер: localhost, Порт: 2525
Логин: user (любой), Пароль: pass (любой)
Шифрование: отключено""")
        info_text.config(state=tk.DISABLED, bg='#f0f0f0')
        
        telegram_frame = ttk.LabelFrame(settings_frame, text="Настройки Telegram")
        telegram_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(telegram_frame, text="Bot Token:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.token_var = tk.StringVar(value=self.bridge.config["telegram_token"])
        token_entry = ttk.Entry(telegram_frame, textvariable=self.token_var, width=50, show="*")
        token_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W+tk.E)
        
        ttk.Label(telegram_frame, text="Chat ID:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.chat_id_var = tk.StringVar(value=self.bridge.config["telegram_chat_id"])
        chat_id_entry = ttk.Entry(telegram_frame, textvariable=self.chat_id_var, width=50)
        chat_id_entry.grid(row=1, column=1, padx=5, pady=2, sticky=tk.W+tk.E)
        
        telegram_frame.columnconfigure(1, weight=1)
        
        smtp_frame = ttk.LabelFrame(settings_frame, text="SMTP Сервер")
        smtp_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(smtp_frame, text="Хост:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.host_var = tk.StringVar(value=self.bridge.config["smtp_host"])
        ttk.Entry(smtp_frame, textvariable=self.host_var, width=20).grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        ttk.Label(smtp_frame, text="Порт:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.port_var = tk.StringVar(value=str(self.bridge.config["smtp_port"]))
        ttk.Entry(smtp_frame, textvariable=self.port_var, width=10).grid(row=0, column=3, padx=5, pady=2, sticky=tk.W)
        
        extra_frame = ttk.LabelFrame(settings_frame, text="Дополнительно")
        extra_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.auto_start_var = tk.BooleanVar(value=self.bridge.config.get("auto_start", False))
        ttk.Checkbutton(extra_frame, text="Автозапуск сервера", variable=self.auto_start_var).pack(anchor=tk.W, padx=5, pady=2)
        
        buttons_frame = ttk.Frame(settings_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=10)
        
        self.start_btn = ttk.Button(buttons_frame, text="Запустить", command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(buttons_frame, text="Остановить", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(buttons_frame, text="Сохранить", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Тест Telegram", command=self.test_telegram).pack(side=tk.LEFT, padx=5)

    def create_logs_tab(self, notebook):
        """Вкладка логов"""
        logs_frame = ttk.Frame(notebook)
        notebook.add(logs_frame, text="Логи")
        
        self.log_text = scrolledtext.ScrolledText(logs_frame, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        log_buttons_frame = ttk.Frame(logs_frame)
        log_buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(log_buttons_frame, text="Очистить", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(log_buttons_frame, text="Обновить", command=self.refresh_logs).pack(side=tk.LEFT, padx=5)
        
        self.refresh_logs()

    def start_server(self):
        """Запуск сервера"""
        if self.bridge.start_server():
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_var.set(f"Запущено на {self.bridge.config['smtp_host']}:{self.bridge.config['smtp_port']} (с AUTH)")
            messagebox.showinfo("Успех", "SMTP сервер с аутентификацией запущен!")
        else:
            messagebox.showerror("Ошибка", "Не удалось запустить сервер.\nПроверьте настройки Telegram.")

    def stop_server(self):
        """Остановка сервера"""
        self.bridge.stop_server()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("Остановлено")

    def save_settings(self):
        """Сохранение настроек"""
        try:
            self.bridge.config["telegram_token"] = self.token_var.get().strip()
            self.bridge.config["telegram_chat_id"] = self.chat_id_var.get().strip()
            self.bridge.config["smtp_host"] = self.host_var.get().strip()
            self.bridge.config["smtp_port"] = int(self.port_var.get())
            self.bridge.config["auto_start"] = self.auto_start_var.get()
            
            self.bridge.save_config()
            messagebox.showinfo("Успех", "Настройки сохранены!")
            
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректный порт!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка сохранения: {e}")

    def test_telegram(self):
        """Тест отправки в Telegram"""
        token = self.token_var.get().strip()
        chat_id = self.chat_id_var.get().strip()
        
        if not token or not chat_id:
            messagebox.showerror("Ошибка", "Укажите Token и Chat ID!")
            return
        
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': f"🧪 Тестовое сообщение\n\nВремя: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\nSMTP-Telegram мост работает!"
            }
            
            response = requests.post(url, data=payload, timeout=10)
            
            if response.status_code == 200:
                messagebox.showinfo("Успех", "Тестовое сообщение отправлено!")
            else:
                messagebox.showerror("Ошибка", f"Ошибка Telegram API:\n{response.text}")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка подключения:\n{e}")

    def clear_logs(self):
        """Очистка логов"""
        self.log_text.delete(1.0, tk.END)

    def refresh_logs(self):
        """Обновление логов"""
        try:
            if os.path.exists('smtp_bridge.log'):
                with open('smtp_bridge.log', 'r', encoding='utf-8') as f:
                    logs = f.read()
                    self.log_text.delete(1.0, tk.END)
                    self.log_text.insert(tk.END, logs)
                    self.log_text.see(tk.END)
        except Exception as e:
            self.log_text.insert(tk.END, f"Ошибка чтения логов: {e}\n")

    def run(self):
        """Запуск приложения"""
        self.root.mainloop()

if __name__ == "__main__":
    app = SMTPBridgeGUI()
    app.run()
