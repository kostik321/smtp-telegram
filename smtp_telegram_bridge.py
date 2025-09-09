#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import email
import requests
from datetime import datetime
import json
import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import base64
import re

CONFIG_FILE = "smtp_config.json"

class FakeSSLSMTPServer:
    def __init__(self, host='localhost', port=25, token='', chat_id='', logger=None):
        self.host = host
        self.port = port
        self.token = token
        self.chat_id = chat_id
        self.logger = logger or logging.getLogger(__name__)
        self.running = False
        self.server_socket = None
        
    def start(self):
        """Запуск SMTP сервера"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            
            self.running = True
            self.logger.info(f"SMTP сервер запущен на {self.host}:{self.port}")
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    self.logger.info(f"Подключение от {address}")
                    
                    client_thread = threading.Thread(
                        target=self.handle_client, 
                        args=(client_socket,),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.error:
                    if self.running:
                        self.logger.error("Ошибка сокета")
                    break
                    
        except Exception as e:
            self.logger.error(f"Ошибка запуска сервера: {e}")
            
    def handle_client(self, client_socket):
        """Обработка клиента"""
        try:
            self.smtp_session(client_socket)
        except Exception as e:
            self.logger.error(f"Ошибка обработки клиента: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def smtp_session(self, sock):
        """SMTP сессия с исправленной обработкой DATA"""
        try:
            import time
            time.sleep(0.1)
            
            self.send_response(sock, "220 localhost ESMTP Ready")
            
            email_data = ""
            in_data_mode = False
            auth_stage = None
            mail_from = ""
            rcpt_to = []
            
            while True:
                try:
                    sock.settimeout(30)
                    data = sock.recv(4096)  # Увеличенный буфер
                    
                    if not data:
                        break
                    
                    try:
                        command = data.decode('utf-8', errors='ignore').strip()
                    except:
                        command = str(data, errors='ignore').strip()
                    
                    if not command:
                        continue
                        
                    self.logger.info(f"Получена команда: {command}")
                    
                    if in_data_mode:
                        # Обработка данных письма построчно
                        lines = command.split('\n')
                        for line in lines:
                            line = line.strip('\r')
                            if line == ".":
                                # Конец данных письма
                                in_data_mode = False
                                self.logger.info("Получен терминатор данных '.'")
                                try:
                                    self.send_response(sock, "250 2.0.0 Message accepted for delivery")
                                    self.process_email(email_data, mail_from, rcpt_to)
                                    email_data = ""
                                    mail_from = ""
                                    rcpt_to = []
                                    self.logger.info("Письмо успешно обработано")
                                except Exception as e:
                                    self.logger.error(f"Ошибка обработки письма: {e}")
                                    self.send_response(sock, "450 4.0.0 Temporary failure")
                                break
                            else:
                                email_data += line + "\n"
                        continue
                    
                    # Обработка SMTP команд
                    cmd_parts = command.split()
                    cmd = cmd_parts[0].upper() if cmd_parts else ""
                    
                    if cmd == "HELO":
                        hostname = cmd_parts[1] if len(cmd_parts) > 1 else "unknown"
                        self.send_response(sock, f"250 localhost Hello {hostname}")
                        
                    elif cmd == "EHLO":
                        hostname = cmd_parts[1] if len(cmd_parts) > 1 else "unknown"
                        responses = [
                            f"250-localhost Hello {hostname}",
                            "250-AUTH LOGIN PLAIN",
                            "250-8BITMIME", 
                            "250-SIZE 52428800",
                            "250 HELP"
                        ]
                        self.send_response(sock, "\r\n".join(responses))
                        
                    elif cmd == "AUTH":
                        auth_type = cmd_parts[1].upper() if len(cmd_parts) > 1 else "LOGIN"
                        self.logger.info(f"Аутентификация: {auth_type}")
                        
                        if auth_type == "LOGIN":
                            auth_stage = "username"
                            self.send_response(sock, "334 VXNlcm5hbWU6")
                        elif auth_type == "PLAIN":
                            if len(cmd_parts) > 2:
                                self.send_response(sock, "235 2.7.0 Authentication successful")
                            else:
                                self.send_response(sock, "334 ")
                        else:
                            self.send_response(sock, "235 2.7.0 Authentication successful")
                            
                    elif auth_stage == "username":
                        try:
                            username = base64.b64decode(command).decode('utf-8', errors='ignore')
                            self.logger.info(f"Username: {username}")
                        except:
                            self.logger.info(f"Username (raw): {command}")
                        auth_stage = "password"
                        self.send_response(sock, "334 UGFzc3dvcmQ6")
                        
                    elif auth_stage == "password":
                        try:
                            password = base64.b64decode(command).decode('utf-8', errors='ignore')
                            self.logger.info(f"Password: {password}")
                        except:
                            self.logger.info(f"Password (raw): {command}")
                        auth_stage = None
                        self.send_response(sock, "235 2.7.0 Authentication successful")
                        
                    elif cmd == "MAIL":
                        if "FROM:" in command.upper():
                            mail_from = command.split("FROM:", 1)[1].strip().strip("<>")
                            self.logger.info(f"Mail from: {mail_from}")
                        self.send_response(sock, "250 2.1.0 Ok")
                        
                    elif cmd == "RCPT":
                        if "TO:" in command.upper():
                            rcpt = command.split("TO:", 1)[1].strip().strip("<>")
                            rcpt_to.append(rcpt)
                            self.logger.info(f"Recipient: {rcpt}")
                        self.send_response(sock, "250 2.1.5 Ok")
                        
                    elif cmd == "DATA":
                        self.send_response(sock, "354 End data with <CR><LF>.<CR><LF>")
                        in_data_mode = True
                        email_data = ""
                        self.logger.info("Переход в режим получения данных письма")
                        
                    elif cmd == "QUIT":
                        self.send_response(sock, "221 2.0.0 Bye")
                        break
                        
                    elif cmd == "RSET":
                        email_data = ""
                        mail_from = ""
                        rcpt_to = []
                        in_data_mode = False
                        auth_stage = None
                        self.send_response(sock, "250 2.0.0 Ok")
                        
                    elif cmd == "NOOP":
                        self.send_response(sock, "250 2.0.0 Ok")
                        
                    elif cmd == "HELP":
                        self.send_response(sock, "214 2.0.0 Help available")
                        
                    else:
                        self.logger.info(f"Неизвестная команда: {command}")
                        self.send_response(sock, "250 2.0.0 Ok")
                        
                except socket.timeout:
                    self.logger.info("Тайм-аут соединения")
                    break
                except socket.error as e:
                    self.logger.info(f"Ошибка сокета: {e}")
                    break
                except Exception as e:
                    self.logger.error(f"Ошибка обработки команды: {e}")
                    try:
                        self.send_response(sock, "500 5.0.0 Command error")
                    except:
                        pass
                    
        except Exception as e:
            self.logger.error(f"Критическая ошибка SMTP сессии: {e}")
    
    def send_response(self, sock, response):
        """Отправка ответа клиенту"""
        try:
            full_response = response + "\r\n"
            sock.send(full_response.encode('utf-8'))
            self.logger.debug(f"Ответ: {response}")
        except Exception as e:
            self.logger.error(f"Ошибка отправки ответа: {e}")
    
    def process_email(self, email_data, mail_from, rcpt_to):
        """Обработка полученного письма"""
        try:
            self.logger.info(f"Обрабатываем письмо от {mail_from} для {rcpt_to}")
            
            if not email_data.strip():
                self.logger.warning("Пустые данные письма")
                return
            
            try:
                msg = email.message_from_string(email_data)
                subject = self.decode_header(msg.get('Subject', 'Без темы'))
                sender = self.decode_header(msg.get('From', mail_from or 'Неизвестный отправитель'))
                
                # Извлечение тела письма с обработкой кодировок
                body = self.extract_body(msg)
                
                self.logger.info(f"Тема: {subject}")
                self.logger.info(f"От: {sender}")
                self.logger.info(f"Размер тела: {len(body)} символов")
                
                # Отправка в Telegram с разбивкой на части
                self.send_to_telegram(subject, sender, body)
                
            except Exception as e:
                self.logger.error(f"Ошибка парсинга email: {e}")
                self.send_to_telegram("Сырые данные письма", mail_from or "unknown", email_data[:3000])
            
        except Exception as e:
            self.logger.error(f"Ошибка обработки письма: {e}")
    
    def decode_header(self, header_value):
        """Декодирование заголовков email"""
        if not header_value:
            return ""
        
        try:
            from email.header import decode_header
            decoded = decode_header(header_value)
            result = ""
            
            for part, encoding in decoded:
                if isinstance(part, bytes):
                    if encoding:
                        result += part.decode(encoding, errors='ignore')
                    else:
                        result += part.decode('utf-8', errors='ignore')
                else:
                    result += str(part)
            
            return result
        except Exception as e:
            self.logger.error(f"Ошибка декодирования заголовка: {e}")
            return str(header_value)
    
    def extract_body(self, msg):
        """Извлечение тела письма с обработкой HTML и кодировок"""
        try:
            body_text = ""
            
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type in ["text/plain", "text/html"]:
                        charset = part.get_content_charset() or 'utf-8'
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            # Попробуем разные кодировки для российских касс
                            for encoding in [charset, 'windows-1251', 'utf-8', 'cp1251']:
                                try:
                                    body_text = payload.decode(encoding, errors='ignore')
                                    break
                                except:
                                    continue
                        else:
                            body_text = str(payload)
                        break
            else:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if isinstance(payload, bytes):
                    # Попробуем разные кодировки
                    for encoding in [charset, 'windows-1251', 'utf-8', 'cp1251']:
                        try:
                            body_text = payload.decode(encoding, errors='ignore')
                            break
                        except:
                            continue
                else:
                    body_text = str(payload)
            
            # Очистка HTML тегов
            body_text = self.clean_html(body_text)
            
            return body_text if body_text.strip() else "Пустое содержимое письма"
            
        except Exception as e:
            self.logger.error(f"Ошибка извлечения тела письма: {e}")
        
        return "Не удалось извлечь содержимое письма"
    
    def clean_html(self, html_text):
        """Очистка HTML тегов и форматирование"""
        if not html_text:
            return ""
        
        # Замена HTML таблиц на читаемый формат
        html_text = re.sub(r'<caption[^>]*>(.*?)</caption>', r'\n**\1**\n', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<tr[^>]*>', '\n', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</tr>', '', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<td[^>]*>', ' ', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</td>', ' |', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<th[^>]*>', ' **', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</th>', '** |', html_text, flags=re.IGNORECASE)
        
        # Замена заголовков
        html_text = re.sub(r'<h[1-6][^>]*>', '\n**', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</h[1-6]>', '**\n', html_text, flags=re.IGNORECASE)
        
        # Замена параграфов
        html_text = re.sub(r'<p[^>]*>', '\n', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</p>', '\n', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<br[^>]*/?>', '\n', html_text, flags=re.IGNORECASE)
        
        # Замена жирного текста
        html_text = re.sub(r'<b[^>]*>', '**', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</b>', '**', html_text, flags=re.IGNORECASE)
        
        # Замена цветного текста
        html_text = re.sub(r'<font[^>]*color[^>]*>', '*', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</font>', '*', html_text, flags=re.IGNORECASE)
        
        # Удаление всех остальных HTML тегов
        html_text = re.sub(r'<[^>]+>', '', html_text)
        
        # Декодирование HTML entities
        html_text = html_text.replace('&nbsp;', ' ')
        html_text = html_text.replace('&amp;', '&')
        html_text = html_text.replace('&lt;', '<')
        html_text = html_text.replace('&gt;', '>')
        html_text = html_text.replace('&quot;', '"')
        
        # Очистка лишних символов
        html_text = re.sub(r' +', ' ', html_text)  # Множественные пробелы
        html_text = re.sub(r'\n\s*\n', '\n', html_text)  # Пустые строки
        html_text = re.sub(r' *\| *\|', ' |', html_text)  # Двойные разделители
        
        return html_text.strip()
    
    def send_to_telegram(self, subject, sender, body):
        """Отправка в Telegram с разбивкой на части"""
        try:
            # Очистка HTML тегов
            clean_body = self.clean_html(body)
            
            header = "📧 *Отчет о продажах*\n\n"
            header += f"*От:* {sender}\n"
            header += f"*Тема:* {subject}\n"
            header += f"*Время:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            header += "=" * 30 + "\n\n"
            
            # Максимальная длина для одного сообщения (оставляем место для заголовка)
            max_length = 3500
            header_length = len(header)
            available_length = max_length - header_length
            
            if len(clean_body) <= available_length:
                # Отправляем одним сообщением
                message = header + clean_body
                self.send_telegram_message(message, 1, 1)
            else:
                # Разбиваем на части
                parts = self.split_message(clean_body, available_length)
                
                # Отправляем первую часть с заголовком
                first_message = header + parts[0]
                if len(parts) > 1:
                    first_message += f"\n\n*[Часть 1 из {len(parts)}]*"
                
                self.send_telegram_message(first_message, 1, len(parts))
                
                # Отправляем остальные части
                for i, part in enumerate(parts[1:], 2):
                    part_message = f"*[Часть {i} из {len(parts)}]*\n\n{part}"
                    self.send_telegram_message(part_message, i, len(parts))
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки в Telegram: {e}")
    
    def split_message(self, text, max_length):
        """Разбивка длинного текста на части"""
        if len(text) <= max_length:
            return [text]
        
        parts = []
        current_part = ""
        
        # Разбиваем по строкам
        lines = text.split('\n')
        
        for line in lines:
            # Если добавление строки превысит лимит
            if len(current_part) + len(line) + 1 > max_length:
                if current_part:
                    parts.append(current_part.strip())
                    current_part = line
                else:
                    # Строка слишком длинная, разбиваем её
                    while len(line) > max_length:
                        parts.append(line[:max_length].strip())
                        line = line[max_length:]
                    current_part = line
            else:
                if current_part:
                    current_part += '\n' + line
                else:
                    current_part = line
        
        # Добавляем последнюю часть
        if current_part:
            parts.append(current_part.strip())
        
        return parts
    
    def send_telegram_message(self, message, part_num, total_parts):
        """Отправка одного сообщения в Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, data=payload, timeout=10)
            
            if response.status_code == 200:
                self.logger.info(f"✅ Часть {part_num}/{total_parts} отправлена в Telegram")
            else:
                self.logger.error(f"❌ Ошибка Telegram API (часть {part_num}): {response.text}")
                
            # Небольшая задержка между сообщениями
            if part_num < total_parts:
                import time
                time.sleep(0.5)
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки части {part_num} в Telegram: {e}")
    
    def stop(self):
        """Остановка сервера"""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

class SMTPBridgeApp:
    def __init__(self):
        self.config = self.load_config()
        self.server = None
        self.server_thread = None
        
        # Логирование
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('smtp_bridge.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        self.create_gui()
        
        # Системный трей
        self.tray_icon = None
        
        # Автозапуск если настроен
        if self.config.get("auto_start", True):
            self.root.after(1000, self.auto_start_server)
    
    def load_config(self):
        """Загрузка конфигурации"""
        default = {
            "telegram_token": "",
            "telegram_chat_id": "",
            "smtp_host": "localhost", 
            "smtp_port": 25,
            "auto_start": True
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    for key, value in default.items():
                        if key not in config:
                            config[key] = value
                    return config
            except:
                pass
        return default
    
    def save_config(self):
        """Сохранение конфигурации"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Ошибка сохранения: {e}")
    
    def create_gui(self):
        """Создание интерфейса"""
        self.root = tk.Tk()
        self.root.title("SMTP-Telegram мост с разбивкой сообщений")
        self.root.geometry("750x700")
        
        # Обработка закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Информация
        info_frame = ttk.LabelFrame(self.root, text="SMTP-Telegram мост с разбивкой сообщений")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        info_text = tk.Text(info_frame, height=4, wrap=tk.WORD)
        info_text.pack(fill=tk.X, padx=5, pady=5)
        info_text.insert(tk.END, 
            "Принимает письма от касс через SMTP и отправляет в Telegram.\n"
            "Длинные отчеты автоматически разбиваются на несколько сообщений.\n"
            "HTML теги очищаются, кодировка windows-1251 поддерживается.\n"
            "В кассе: localhost:25, логин/пароль любые или пустые"
        )
        info_text.config(state=tk.DISABLED, bg='#f0f0f0')
        
        # Настройки  
        settings_frame = ttk.LabelFrame(self.root, text="Настройки")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Token
        ttk.Label(settings_frame, text="Bot Token:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.token_var = tk.StringVar(value=self.config["telegram_token"])
        ttk.Entry(settings_frame, textvariable=self.token_var, width=50, show="*").grid(row=0, column=1, padx=5, pady=2, sticky=tk.W+tk.E)
        
        # Chat ID
        ttk.Label(settings_frame, text="Chat ID:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.chat_id_var = tk.StringVar(value=self.config["telegram_chat_id"])
        ttk.Entry(settings_frame, textvariable=self.chat_id_var, width=50).grid(row=1, column=1, padx=5, pady=2, sticky=tk.W+tk.E)
        
        # Порт
        ttk.Label(settings_frame, text="Порт:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.port_var = tk.StringVar(value=str(self.config["smtp_port"]))
        port_entry = ttk.Entry(settings_frame, textvariable=self.port_var, width=10)
        port_entry.grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
        
        ttk.Label(settings_frame, text="(25-стандартный SMTP, 587-STARTTLS)").grid(row=2, column=2, sticky=tk.W, padx=5, pady=2)
        
        # Автозапуск
        auto_frame = ttk.Frame(settings_frame)
        auto_frame.grid(row=3, column=0, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=5)
        
        self.auto_start_var = tk.BooleanVar(value=self.config.get("auto_start", True))
        ttk.Checkbutton(auto_frame, text="Автозапуск сервера при открытии программы", 
                       variable=self.auto_start_var).pack(anchor=tk.W)
        
        settings_frame.columnconfigure(1, weight=1)
        
        # Кнопки управления
        buttons_frame = ttk.Frame(self.root)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_btn = ttk.Button(buttons_frame, text="Запустить SMTP", command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(buttons_frame, text="Остановить", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(buttons_frame, text="Сохранить", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Тест Telegram", command=self.test_telegram).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Очистить логи", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Копировать все логи", command=self.copy_all_logs).pack(side=tk.LEFT, padx=5)
        
        # Кнопки работы с трей и автозагрузкой
        tray_buttons_frame = ttk.Frame(self.root)
        tray_buttons_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(tray_buttons_frame, text="Свернуть в трей", command=self.minimize_to_tray).pack(side=tk.LEFT, padx=5)
        ttk.Button(tray_buttons_frame, text="Добавить в автозагрузку", command=self.add_to_startup).pack(side=tk.LEFT, padx=5)
        ttk.Button(tray_buttons_frame, text="Убрать из автозагрузки", command=self.remove_from_startup).pack(side=tk.LEFT, padx=5)
        
        # Логи
        logs_frame = ttk.LabelFrame(self.root, text="Логи работы")
        logs_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(logs_frame, height=20, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Статус
        self.status_var = tk.StringVar()
        self.status_var.set("Остановлено")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Автообновление логов
        self.refresh_logs()
    
    def start_server(self):
        """Запуск сервера"""
        if not self.config["telegram_token"] or not self.config["telegram_chat_id"]:
            messagebox.showerror("Ошибка", "Укажите Token и Chat ID!")
            return
        
        try:
            port = int(self.port_var.get())
            
            self.server = FakeSSLSMTPServer(
                host=self.config["smtp_host"],
                port=port,
                token=self.config["telegram_token"],
                chat_id=self.config["telegram_chat_id"],
                logger=self.logger
            )
            
            self.server_thread = threading.Thread(target=self.server.start, daemon=True)
            self.server_thread.start()
            
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_var.set(f"SMTP сервер запущен на localhost:{port}")
            
            messagebox.showinfo("Успех", f"SMTP сервер запущен на порту {port}!\nДлинные отчеты будут разбиваться на части автоматически.")
            
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректный порт!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запустить сервер: {e}")
            self.logger.error(f"Ошибка запуска: {e}")
    
    def stop_server(self):
        """Остановка сервера"""
        if self.server:
            self.server.stop()
        
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("Остановлено")
    
    def save_settings(self):
        """Сохранение настроек"""
        try:
            self.config["telegram_token"] = self.token_var.get().strip()
            self.config["telegram_chat_id"] = self.chat_id_var.get().strip()
            self.config["smtp_port"] = int(self.port_var.get())
            self.config["auto_start"] = self.auto_start_var.get()
            
            self.save_config()
            messagebox.showinfo("Успех", "Настройки сохранены!")
            
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректный порт!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка сохранения: {e}")
    
    def test_telegram(self):
        """Тест Telegram"""
        token = self.token_var.get().strip()
        chat_id = self.chat_id_var.get().strip()
        
        if not token or not chat_id:
            messagebox.showerror("Ошибка", "Укажите Token и Chat ID!")
            return
        
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': f"🧪 Тестовое сообщение\n\nВремя: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\nSMTP-Telegram мост готов к работе!\nДлинные отчеты будут разбиваться на части."
            }
            
            response = requests.post(url, data=payload, timeout=10)
            
            if response.status_code == 200:
                messagebox.showinfo("Успех", "Тестовое сообщение отправлено!")
            else:
                messagebox.showerror("Ошибка", f"Ошибка API: {response.text}")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка подключения: {e}")
    
    def clear_logs(self):
        """Полная очистка логов"""
        try:
            # Очистка окна логов
            self.log_text.delete(1.0, tk.END)
            
            # Удаление файла логов
            if os.path.exists('smtp_bridge.log'):
                os.remove('smtp_bridge.log')
                
            # Создание нового пустого лога
            with open('smtp_bridge.log', 'w', encoding='utf-8') as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Логи очищены\n")
            
            self.log_text.insert(tk.END, f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Логи очищены\n")
            messagebox.showinfo("Успех", "Логи полностью очищены!")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка очистки логов: {e}")
    
    def copy_all_logs(self):
        """Копирование всех логов в буфер обмена"""
        try:
            logs_content = ""
            
            # Получаем логи из файла (более полная версия)
            if os.path.exists('smtp_bridge.log'):
                with open('smtp_bridge.log', 'r', encoding='utf-8') as f:
                    logs_content = f.read()
            
            # Если файла нет, берем из окна
            if not logs_content:
                logs_content = self.log_text.get(1.0, tk.END)
            
            if logs_content.strip():
                # Копируем в буфер обмена
                self.root.clipboard_clear()
                self.root.clipboard_append(logs_content)
                self.root.update()  # Обязательно для Windows
                
                lines_count = len(logs_content.split('\n'))
                messagebox.showinfo("Успех", f"Все логи скопированы в буфер обмена!\nСтрок: {lines_count}")
            else:
                messagebox.showwarning("Предупреждение", "Логи пусты, нечего копировать")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка копирования логов: {e}")
    
    def minimize_to_tray(self):
        """Сворачивание в системный трей"""
        try:
            import pystray
            from PIL import Image, ImageDraw
            
            if self.tray_icon:
                return
                
            # Создание иконки для трея
            image = Image.new('RGB', (64, 64), color=(0, 100, 200))
            draw = ImageDraw.Draw(image)
            draw.rectangle([16, 16, 48, 48], fill=(255, 255, 255))
            draw.text((24, 28), "S", fill=(0, 0, 0), anchor="mm")
            
            # Создание меню
            menu = pystray.Menu(
                pystray.MenuItem("Показать окно", self.show_from_tray),
                pystray.MenuItem("Остановить сервер", self.stop_server_tray),
                pystray.MenuItem("Перезапустить сервер", self.restart_server_tray),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Выход", self.quit_from_tray)
            )
            
            # Создание иконки трея
            self.tray_icon = pystray.Icon(
                "smtp_bridge", 
                image, 
                "SMTP-Telegram мост", 
                menu
            )
            
            # Скрытие окна
            self.root.withdraw()
            
            # Запуск трея в отдельном потоке
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
            
            self.logger.info("Программа свернута в системный трей")
            
        except ImportError:
            messagebox.showerror("Ошибка", "Библиотека pystray не найдена!\nСистемный трей недоступен.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка сворачивания в трей: {e}")
    
    def show_from_tray(self, icon=None, item=None):
        """Показать окно из трея"""
        self.root.deiconify()
        self.root.lift()
    
    def stop_server_tray(self, icon=None, item=None):
        """Остановить сервер из трея"""
        self.stop_server()
    
    def restart_server_tray(self, icon=None, item=None):
        """Перезапустить сервер из трея"""
        self.stop_server()
        import time
        time.sleep(1)
        self.start_server()
    
    def quit_from_tray(self, icon=None, item=None):
        """Выход из трея"""
        if self.tray_icon:
            self.tray_icon.stop()
        self.stop_server()
        self.root.quit()
    
    def add_to_startup(self):
        """Добавление в автозагрузку Windows"""
        try:
            import winreg
            import sys
            
            # Путь к исполняемому файлу
            exe_path = sys.executable if hasattr(sys, 'frozen') else sys.argv[0]
            exe_path = os.path.abspath(exe_path)
            
            # Ключ реестра для автозагрузки
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            # Добавление записи
            winreg.SetValueEx(key, "SMTP-Telegram-Bridge", 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            
            messagebox.showinfo("Успех", "Программа добавлена в автозагрузку Windows!")
            self.logger.info("Программа добавлена в автозагрузку")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось добавить в автозагрузку: {e}")
            self.logger.error(f"Ошибка добавления в автозагрузку: {e}")
    
    def remove_from_startup(self):
        """Удаление из автозагрузки Windows"""
        try:
            import winreg
            
            # Ключ реестра для автозагрузки
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            try:
                # Удаление записи
                winreg.DeleteValue(key, "SMTP-Telegram-Bridge")
                messagebox.showinfo("Успех", "Программа удалена из автозагрузки Windows!")
                self.logger.info("Программа удалена из автозагрузки")
            except FileNotFoundError:
                messagebox.showinfo("Информация", "Программа не была в автозагрузке")
            
            winreg.CloseKey(key)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить из автозагрузки: {e}")
            self.logger.error(f"Ошибка удаления из автозагрузки: {e}")
    
    def on_closing(self):
        """Обработка закрытия окна"""
        result = messagebox.askyesnocancel(
            "Выход", 
            "Что вы хотите сделать?\n\n"
            "Да - Свернуть в трей (продолжить работу)\n"
            "Нет - Полностью закрыть программу\n"
            "Отмена - Остаться в окне"
        )
        
        if result is True:  # Да - свернуть в трей
            self.minimize_to_tray()
        elif result is False:  # Нет - закрыть
            if self.tray_icon:
                self.tray_icon.stop()
            self.stop_server()
            self.root.destroy()
    
    def auto_start_server(self):
        """Автоматический запуск сервера"""
        if not self.server and self.config.get("auto_start", False):
            if self.config["telegram_token"] and self.config["telegram_chat_id"]:
                self.logger.info("Автозапуск сервера...")
                self.start_server()
    
    def refresh_logs(self):
        """Автообновление логов"""
        try:
            if os.path.exists('smtp_bridge.log'):
                with open('smtp_bridge.log', 'r', encoding='utf-8') as f:
                    logs = f.readlines()
                    
                # Показываем только последние 100 строк
                recent_logs = logs[-100:] if len(logs) > 100 else logs
                
                current_content = self.log_text.get(1.0, tk.END)
                new_content = ''.join(recent_logs)
                
                if new_content != current_content.strip():
                    self.log_text.delete(1.0, tk.END)
                    self.log_text.insert(tk.END, new_content)
                    self.log_text.see(tk.END)
        except:
            pass
        
        # Обновляем каждые 2 секунды
        self.root.after(2000, self.refresh_logs)
    
    def run(self):
        """Запуск приложения"""
        self.root.mainloop()

if __name__ == "__main__":
    app = SMTPBridgeApp()
    app.run()
