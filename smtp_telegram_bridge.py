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
            self.logger.info(f"SMTP сервер запущено на {self.host}:{self.port}")
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    self.logger.info(f"Підключення від {address}")
                    
                    client_thread = threading.Thread(
                        target=self.handle_client, 
                        args=(client_socket,),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.error:
                    if self.running:
                        self.logger.error("Помилка сокета")
                    break
                    
        except Exception as e:
            self.logger.error(f"Помилка запуску сервера: {e}")
            
    def handle_client(self, client_socket):
        """Обробка клієнта"""
        try:
            self.smtp_session(client_socket)
        except Exception as e:
            self.logger.error(f"Помилка обробки клієнта: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def smtp_session(self, sock):
        """SMTP сесія з виправленою обробкою DATA"""
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
                    data = sock.recv(4096)
                    
                    if not data:
                        break
                    
                    try:
                        command = data.decode('utf-8', errors='ignore').strip()
                    except:
                        command = str(data, errors='ignore').strip()
                    
                    if not command:
                        continue
                        
                    self.logger.info(f"Отримано команду: {command}")
                    
                    if in_data_mode:
                        lines = command.split('\n')
                        for line in lines:
                            line = line.strip('\r')
                            if line == ".":
                                in_data_mode = False
                                self.logger.info("Отримано термінатор даних '.'")
                                try:
                                    self.send_response(sock, "250 2.0.0 Повідомлення прийнято для доставки")
                                    self.process_email(email_data, mail_from, rcpt_to)
                                    email_data = ""
                                    mail_from = ""
                                    rcpt_to = []
                                    self.logger.info("Лист успішно оброблено")
                                except Exception as e:
                                    self.logger.error(f"Помилка обробки листа: {e}")
                                    self.send_response(sock, "450 4.0.0 Тимчасова помилка")
                                break
                            else:
                                email_data += line + "\n"
                        continue
                    
                    cmd_parts = command.split()
                    cmd = cmd_parts[0].upper() if cmd_parts else ""
                    
                    if cmd == "HELO":
                        hostname = cmd_parts[1] if len(cmd_parts) > 1 else "невідомий"
                        self.send_response(sock, f"250 localhost Привіт {hostname}")
                        
                    elif cmd == "EHLO":
                        hostname = cmd_parts[1] if len(cmd_parts) > 1 else "невідомий"
                        responses = [
                            f"250-localhost Привіт {hostname}",
                            "250-AUTH LOGIN PLAIN",
                            "250-8BITMIME", 
                            "250-SIZE 52428800",
                            "250 HELP"
                        ]
                        self.send_response(sock, "\r\n".join(responses))
                        
                    elif cmd == "AUTH":
                        auth_type = cmd_parts[1].upper() if len(cmd_parts) > 1 else "LOGIN"
                        self.logger.info(f"Автентифікація: {auth_type}")
                        
                        if auth_type == "LOGIN":
                            auth_stage = "username"
                            self.send_response(sock, "334 VXNlcm5hbWU6")
                        elif auth_type == "PLAIN":
                            if len(cmd_parts) > 2:
                                self.send_response(sock, "235 2.7.0 Автентифікація успішна")
                            else:
                                self.send_response(sock, "334 ")
                        else:
                            self.send_response(sock, "235 2.7.0 Автентифікація успішна")
                            
                    elif auth_stage == "username":
                        try:
                            username = base64.b64decode(command).decode('utf-8', errors='ignore')
                            self.logger.info(f"Користувач: {username}")
                        except:
                            self.logger.info(f"Користувач (необроблений): {command}")
                        auth_stage = "password"
                        self.send_response(sock, "334 UGFzc3dvcmQ6")
                        
                    elif auth_stage == "password":
                        try:
                            password = base64.b64decode(command).decode('utf-8', errors='ignore')
                            self.logger.info(f"Пароль: {password}")
                        except:
                            self.logger.info(f"Пароль (необроблений): {command}")
                        auth_stage = None
                        self.send_response(sock, "235 2.7.0 Автентифікація успішна")
                        
                    elif cmd == "MAIL":
                        if "FROM:" in command.upper():
                            mail_from = command.split("FROM:", 1)[1].strip().strip("<>")
                            self.logger.info(f"Лист від: {mail_from}")
                        self.send_response(sock, "250 2.1.0 Добре")
                        
                    elif cmd == "RCPT":
                        if "TO:" in command.upper():
                            rcpt = command.split("TO:", 1)[1].strip().strip("<>")
                            rcpt_to.append(rcpt)
                            self.logger.info(f"Отримувач: {rcpt}")
                        self.send_response(sock, "250 2.1.5 Добре")
                        
                    elif cmd == "DATA":
                        self.send_response(sock, "354 Закінчіть дані з <CR><LF>.<CR><LF>")
                        in_data_mode = True
                        email_data = ""
                        self.logger.info("Перехід в режим отримання даних листа")
                        
                    elif cmd == "QUIT":
                        self.send_response(sock, "221 2.0.0 До побачення")
                        break
                        
                    elif cmd == "RSET":
                        email_data = ""
                        mail_from = ""
                        rcpt_to = []
                        in_data_mode = False
                        auth_stage = None
                        self.send_response(sock, "250 2.0.0 Добре")
                        
                    elif cmd == "NOOP":
                        self.send_response(sock, "250 2.0.0 Добре")
                        
                    elif cmd == "HELP":
                        self.send_response(sock, "214 2.0.0 Допомога доступна")
                        
                    else:
                        self.logger.info(f"Невідома команда: {command}")
                        self.send_response(sock, "250 2.0.0 Добре")
                        
                except socket.timeout:
                    self.logger.info("Тайм-аут з'єднання")
                    break
                except socket.error as e:
                    self.logger.info(f"Помилка сокета: {e}")
                    break
                except Exception as e:
                    self.logger.error(f"Помилка обробки команди: {e}")
                    try:
                        self.send_response(sock, "500 5.0.0 Помилка команди")
                    except:
                        pass
                    
        except Exception as e:
            self.logger.error(f"Критична помилка SMTP сесії: {e}")
    
    def send_response(self, sock, response):
        """Відправка відповіді клієнту"""
        try:
            full_response = response + "\r\n"
            sock.send(full_response.encode('utf-8'))
            self.logger.debug(f"Відповідь: {response}")
        except Exception as e:
            self.logger.error(f"Помилка відправки відповіді: {e}")
    
    def process_email(self, email_data, mail_from, rcpt_to):
        """Обробка отриманого листа"""
        try:
            self.logger.info(f"Обробляємо лист від {mail_from} для {rcpt_to}")
            
            if not email_data.strip():
                self.logger.warning("Порожні дані листа")
                return
            
            try:
                msg = email.message_from_string(email_data)
                subject = self.decode_header(msg.get('Subject', 'Без теми'))
                sender = self.decode_header(msg.get('From', mail_from or 'Невідомий відправник'))
                
                body = self.extract_body(msg)
                
                self.logger.info(f"Тема: {subject}")
                self.logger.info(f"Від: {sender}")
                self.logger.info(f"Розмір тіла: {len(body)} символів")
                
                self.send_to_telegram(subject, sender, body)
                
            except Exception as e:
                self.logger.error(f"Помилка парсингу email: {e}")
                self.send_to_telegram("Необроблені дані листа", mail_from or "невідомо", email_data[:3000])
            
        except Exception as e:
            self.logger.error(f"Помилка обробки листа: {e}")
    
    def decode_header(self, header_value):
        """Декодування заголовків email"""
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
            self.logger.error(f"Помилка декодування заголовка: {e}")
            return str(header_value)
    
    def extract_body(self, msg):
        """Витягування тіла листа з обробкою HTML та кодувань"""
        try:
            body_text = ""
            
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type in ["text/plain", "text/html"]:
                        charset = part.get_content_charset() or 'utf-8'
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
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
                    for encoding in [charset, 'windows-1251', 'utf-8', 'cp1251']:
                        try:
                            body_text = payload.decode(encoding, errors='ignore')
                            break
                        except:
                            continue
                else:
                    body_text = str(payload)
            
            body_text = self.clean_html(body_text)
            
            return body_text if body_text.strip() else "Порожній вміст листа"
            
        except Exception as e:
            self.logger.error(f"Помилка витягування тіла листа: {e}")
        
        return "Не вдалося витягти вміст листа"
    
    def clean_html(self, html_text):
        """Очищення HTML тегів та форматування"""
        if not html_text:
            return ""
        
        # Заміна HTML таблиць на читабельний формат
        html_text = re.sub(r'<caption[^>]*>(.*?)</caption>', r'\n**\1**\n', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<tr[^>]*>', '\n', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</tr>', '', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<td[^>]*>', ' ', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</td>', ' |', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<th[^>]*>', ' **', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</th>', '** |', html_text, flags=re.IGNORECASE)
        
        # Заміна заголовків
        html_text = re.sub(r'<h[1-6][^>]*>', '\n**', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</h[1-6]>', '**\n', html_text, flags=re.IGNORECASE)
        
        # Заміна параграфів
        html_text = re.sub(r'<p[^>]*>', '\n', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</p>', '\n', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<br[^>]*/?>', '\n', html_text, flags=re.IGNORECASE)
        
        # Заміна жирного тексту
        html_text = re.sub(r'<b[^>]*>', '**', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</b>', '**', html_text, flags=re.IGNORECASE)
        
        # Заміна кольорового тексту
        html_text = re.sub(r'<font[^>]*color[^>]*>', '*', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</font>', '*', html_text, flags=re.IGNORECASE)
        
        # Видалення всіх інших HTML тегів
        html_text = re.sub(r'<[^>]+>', '', html_text)
        
        # Декодування HTML entities
        html_text = html_text.replace('&nbsp;', ' ')
        html_text = html_text.replace('&amp;', '&')
        html_text = html_text.replace('&lt;', '<')
        html_text = html_text.replace('&gt;', '>')
        html_text = html_text.replace('&quot;', '"')
        
        # Очищення зайвих символів та покращене форматування
        html_text = re.sub(r' +', ' ', html_text)
        html_text = re.sub(r'\n\s*\n', '\n', html_text)
        html_text = re.sub(r' *\| *\|', ' |', html_text)
        
        # Покращення форматування для SAMPO звітів
        formatted_text = self.format_sampo_report(html_text)
        
        return formatted_text.strip()
    
    def format_sampo_report(self, text):
        """Спеціальне форматування для звітів SAMPO"""
        # Перевіряємо чи це SAMPO звіт
        if 'SAMPO Reports' not in text:
            return text
            
        lines = text.split('\n')
        formatted_lines = []
        in_table = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Основна назва
            if line == 'SAMPO Reports':
                formatted_lines.append("🏪 **SAMPO REPORTS**")
                continue
            elif line == 'Отправка по команде пользователя.':
                formatted_lines.append("📤 Відправка по команді користувача")
                continue
                
            # Фільтр секція
            if line == 'Фильтр':
                formatted_lines.append("\n🔍 **ФІЛЬТР**")
                continue
            elif line.startswith('Организации:'):
                org_name = line.replace('Организации:', '').strip()
                formatted_lines.append(f"🏢 **Організація:** {org_name}")
                continue
            elif line.startswith('Склады:'):
                warehouse = line.replace('Склады:', '').strip()
                formatted_lines.append(f"🏪 **Склад:** {warehouse}")
                continue
                
            # Зведений звіт
            if line == 'Сводный отчет':
                formatted_lines.append(f"\n📊 **ЗВЕДЕНИЙ ЗВІТ**")
                continue
            elif line.startswith('Период:'):
                period = line.replace('Период:', '').strip()
                formatted_lines.append(f"🗓 **Період:** {period}")
                continue
                
            # Продажі секція
            if line == 'ПРОДАЖИ':
                formatted_lines.append(f"\n💰 **ПРОДАЖІ**")
                continue
            elif line == 'ВОЗВРАТЫ':
                formatted_lines.append(f"\n📉 **ПОВЕРНЕННЯ**")
                continue
                
            # Обробка рядків з даними (формат " Ключ | Значення |")
            if '|' in line and line.count('|') >= 2:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 3 and parts[0] and parts[1]:
                    key = parts[0]
                    value = parts[1]
                    
                    # Визначення типу даних для емодзі
                    if any(word in key.lower() for word in ['сумма', 'сума']):
                        formatted_lines.append(f"💵 **{key}:** `{value}`")
                    elif any(word in key.lower() for word in ['скидка', 'знижка']):
                        formatted_lines.append(f"🏷️ **{key}:** `{value}`")
                    elif any(word in key.lower() for word in ['прибыль', 'прибуток']):
                        formatted_lines.append(f"📈 **{key}:** `{value}`")
                    elif any(word in key.lower() for word in ['средний', 'середній']):
                        formatted_lines.append(f"🧾 **{key}:** `{value}`")
                    elif any(word in key.lower() for word in ['к-во', 'к-сть', 'чеков', 'чеків']):
                        formatted_lines.append(f"🧾 **{key}:** `{value}`")
                    elif any(word in key.lower() for word in ['убыток', 'збиток']):
                        formatted_lines.append(f"📉 **{key}:** `{value}`")
                    else:
                        formatted_lines.append(f"📊 **{key}:** `{value}`")
                    continue
                    
            # Звіт по товарах
            if line == 'Отчет по товарам':
                formatted_lines.append(f"\n🛒 **ЗВІТ ПО ТОВАРАХ**")
                continue
                
            # Заголовок таблиці товарів
            if '№' in line and 'Имя' in line and 'К-во' in line:
                formatted_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                formatted_lines.append("📋 **СПИСОК ТОВАРІВ:**")
                formatted_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                in_table = True
                continue
                
            # Рядки товарів у таблиці
            if in_table and '|' in line and line.strip().split('|')[0].strip().isdigit():
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 4:
                    try:
                        num = parts[0]
                        name = parts[1]
                        qty = parts[2]
                        cost = parts[3]
                        profit = parts[4] if len(parts) > 4 else "—"
                        
                        # Скорочуємо назву якщо дуже довга
                        if len(name) > 35:
                            name = name[:32] + "..."
                            
                        formatted_lines.append(f"\n`{num:>2}.` **{name}**")
                        formatted_lines.append(f"   📦 Кількість: `{qty}`")
                        formatted_lines.append(f"   💵 Вартість: `{cost}`")
                        formatted_lines.append(f"   📈 Прибуток: `{profit}`")
                        formatted_lines.append("   ────────────────────────────")
                        continue
                    except (IndexError, ValueError):
                        pass
                        
            # ВСЕГО рядок
            if line.strip().startswith('|') and 'ВСЕГО' in line:
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 3:
                    formatted_lines.append("\n" + "═" * 40)
                    formatted_lines.append(f"💰 **ВСЬОГО:** Сума: `{parts[1]}` | Прибуток: `{parts[2]}`")
                    formatted_lines.append("═" * 40)
                continue
                
            # Інші рядки без змін
            if line not in ['', ' ']:
                formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    def send_to_telegram(self, subject, sender, body):
        """Відправка в Telegram з розбиттям на частини"""
        try:
            # Логування для відстеження
            self.logger.info(f"Початковий текст містить: {len(body)} символів")
            self.logger.info(f"Перевірка на SAMPO: {'SAMPO Reports' in body}")
            
            # Логування перших 500 символів для аналізу структури
            self.logger.info(f"Початок тексту: {body[:500]}")
            
            clean_body = self.clean_html(body)
            
            self.logger.info(f"Після форматування: {len(clean_body)} символів")
            # Логування результату форматування
            self.logger.info(f"Форматований текст (перші 800 символів): {clean_body[:800]}")
            
            header = "📊 **ЗВІТ SAMPO**\n\n"
            header += f"👤 **Від:** {sender}\n"
            header += f"📧 **Тема:** {subject}\n"
            header += f"⏰ **Час:** {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            header += "═" * 40 + "\n\n"
            
            max_length = 3000
            header_length = len(header)
            available_length = max_length - header_length
            
            if len(clean_body) <= available_length:
                message = header + clean_body
                self.send_telegram_message(message, 1, 1)
            else:
                parts = self.split_message(clean_body, available_length)
                
                first_message = header + parts[0]
                if len(parts) > 1:
                    first_message += f"\n\n*[Частина 1 з {len(parts)}]*"
                
                self.send_telegram_message(first_message, 1, len(parts))
                
                for i, part in enumerate(parts[1:], 2):
                    part_message = f"*[Частина {i} з {len(parts)}]*\n\n{part}"
                    self.send_telegram_message(part_message, i, len(parts))
                
        except Exception as e:
            self.logger.error(f"❌ Помилка відправки в Telegram: {e}")
    
    def split_message(self, text, max_length):
        """Розбиття довгого тексту на частини"""
        if len(text) <= max_length:
            return [text]
        
        parts = []
        current_part = ""
        
        lines = text.split('\n')
        
        for line in lines:
            if len(current_part) + len(line) + 1 > max_length:
                if current_part:
                    parts.append(current_part.strip())
                    current_part = line
                else:
                    while len(line) > max_length:
                        parts.append(line[:max_length].strip())
                        line = line[max_length:]
                    current_part = line
            else:
                if current_part:
                    current_part += '\n' + line
                else:
                    current_part = line
        
        if current_part:
            parts.append(current_part.strip())
        
        return parts
    
    def send_telegram_message(self, message, part_num, total_parts):
        """Відправка одного повідомлення в Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, data=payload, timeout=10)
            
            if response.status_code == 200:
                self.logger.info(f"✅ Частина {part_num}/{total_parts} відправлена в Telegram")
            else:
                self.logger.error(f"❌ Помилка Telegram API (частина {part_num}): {response.text}")
                
            if part_num < total_parts:
                import time
                time.sleep(0.5)
                
        except Exception as e:
            self.logger.error(f"❌ Помилка відправки частини {part_num} в Telegram: {e}")
    
    def stop(self):
        """Зупинка сервера"""
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
        
        self.tray_icon = None
        
        # Автозапуск сервера через 2 секунди після запуску
        if self.config.get("auto_start", True):
            self.root.after(2000, self.auto_start_server)
    
    def load_config(self):
        """Завантаження конфігурації"""
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
        """Збереження конфігурації"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Помилка збереження: {e}")
    
    def create_gui(self):
        """Створення інтерфейсу"""
        self.root = tk.Tk()
        self.root.title("SMTP-Telegram міст для касових звітів SAMPO")
        self.root.geometry("800x400")
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Інформація
        info_frame = ttk.LabelFrame(self.root, text="SMTP-Telegram міст для касових звітів SAMPO")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        info_text = tk.Text(info_frame, height=5, wrap=tk.WORD)
        info_text.pack(fill=tk.X, padx=5, pady=5)
        info_text.insert(tk.END, 
            "Приймає звіти від касових апаратів SAMPO через SMTP та відправляє в Telegram.\n"
            "Довгі звіти автоматично розбиваються на кілька повідомлень для зручності читання.\n"
            "HTML теги очищаються, підтримується кодування windows-1251 для українських кас.\n"
            "Автоматично запускається на порту 25 при старті програми.\n"
            "В касі налаштуйте: localhost:25, логін/пароль будь-які або порожні"
        )
        info_text.config(state=tk.DISABLED, bg='#f0f0f0')
        
        # Налаштування  
        settings_frame = ttk.LabelFrame(self.root, text="Налаштування")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Token
        ttk.Label(settings_frame, text="Telegram Bot Token:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.token_var = tk.StringVar(value=self.config["telegram_token"])
        ttk.Entry(settings_frame, textvariable=self.token_var, width=50, show="*").grid(row=0, column=1, padx=5, pady=2, sticky=tk.W+tk.E)
        
        # Chat ID
        ttk.Label(settings_frame, text="Telegram Chat ID:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.chat_id_var = tk.StringVar(value=self.config["telegram_chat_id"])
        ttk.Entry(settings_frame, textvariable=self.chat_id_var, width=50).grid(row=1, column=1, padx=5, pady=2, sticky=tk.W+tk.E)
        
        # Порт
        ttk.Label(settings_frame, text="SMTP Порт:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.port_var = tk.StringVar(value=str(self.config["smtp_port"]))
        port_entry = ttk.Entry(settings_frame, textvariable=self.port_var, width=10)
        port_entry.grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
        
        ttk.Label(settings_frame, text="(25-стандартний SMTP, 587-STARTTLS)").grid(row=2, column=2, sticky=tk.W, padx=5, pady=2)
        
        # Автозапуск
        auto_frame = ttk.Frame(settings_frame)
        auto_frame.grid(row=3, column=0, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=5)
        
        self.auto_start_var = tk.BooleanVar(value=self.config.get("auto_start", True))
        ttk.Checkbutton(auto_frame, text="Автозапуск SMTP сервера при відкритті програми (рекомендовано)", 
                       variable=self.auto_start_var).pack(anchor=tk.W)
        
        settings_frame.columnconfigure(1, weight=1)
        
        # Кнопки управління
        buttons_frame = ttk.Frame(self.root)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_btn = ttk.Button(buttons_frame, text="Запустити SMTP", command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(buttons_frame, text="Зупинити", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(buttons_frame, text="Зберегти", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Тест Telegram", command=self.test_telegram).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Очистити логи", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Копіювати всі логи", command=self.copy_all_logs).pack(side=tk.LEFT, padx=5)
        
        # Кнопки роботи з трей та автозавантаженням
        tray_buttons_frame = ttk.Frame(self.root)
        tray_buttons_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(tray_buttons_frame, text="Згорнути в трей", command=self.minimize_to_tray).pack(side=tk.LEFT, padx=5)
        ttk.Button(tray_buttons_frame, text="Додати в автозавантаження", command=self.add_to_startup).pack(side=tk.LEFT, padx=5)
        ttk.Button(tray_buttons_frame, text="Прибрати з автозавантаження", command=self.remove_from_startup).pack(side=tk.LEFT, padx=5)
        
        # Логи
        logs_frame = ttk.LabelFrame(self.root, text=f"Логи роботи - {self.log_file_path}")
        logs_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(logs_frame, height=20, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Статус
        self.status_var = tk.StringVar()
        self.status_var.set("Зупинено - очікування автозапуску...")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Автооновлення логів
        self.refresh_logs()
    
    def start_server(self):
        """Запуск сервера"""
        if not self.config["telegram_token"] or not self.config["telegram_chat_id"]:
            messagebox.showerror("Помилка", "Вкажіть Token та Chat ID!")
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
            self.status_var.set(f"✅ SMTP сервер запущено на localhost:{port} - готовий до прийому звітів")
            
            messagebox.showinfo("Успіх", 
                f"SMTP сервер запущено на порту {port}!\n\n"
                f"Тепер каса SAMPO може відправляти звіти на localhost:{port}\n"
                f"Довгі звіти будуть автоматично розбиватися на частини для зручності читання в Telegram."
            )
            
        except ValueError:
            messagebox.showerror("Помилка", "Некоректний порт!")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося запустити сервер: {e}")
            self.logger.error(f"Помилка запуску: {e}")
    
    def stop_server(self):
        """Зупинка сервера"""
        if self.server:
            self.server.stop()
        
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("❌ Зупинено")
    
    def save_settings(self):
        """Збереження налаштувань"""
        try:
            self.config["telegram_token"] = self.token_var.get().strip()
            self.config["telegram_chat_id"] = self.chat_id_var.get().strip()
            self.config["smtp_port"] = int(self.port_var.get())
            self.config["auto_start"] = self.auto_start_var.get()
            
            self.save_config()
            messagebox.showinfo("Успіх", "Налаштування збережено!")
            
        except ValueError:
            messagebox.showerror("Помилка", "Некоректний порт!")
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка збереження: {e}")
    
    def test_telegram(self):
        """Тест Telegram"""
        token = self.token_var.get().strip()
        chat_id = self.chat_id_var.get().strip()
        
        if not token or not chat_id:
            messagebox.showerror("Помилка", "Вкажіть Token та Chat ID!")
            return
        
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': f"🧪 Тестове повідомлення від SAMPO Reports\n\n"
                       f"Час: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                       f"SMTP-Telegram міст готовий до роботи!\n"
                       f"Довгі звіти будуть розбиватися на частини автоматично.\n\n"
                       f"Організація: Фоп Вараксіна-Задорожна Валентина Вікторівна"
            }
            
            response = requests.post(url, data=payload, timeout=10)
            
            if response.status_code == 200:
                messagebox.showinfo("Успіх", "Тестове повідомлення відправлено!")
            else:
                messagebox.showerror("Помилка", f"Помилка API: {response.text}")
                
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка підключення: {e}")
    
    def clear_logs(self):
        """Повна очистка логів"""
        try:
            self.log_text.delete(1.0, tk.END)
            
            if os.path.exists('smtp_bridge.log'):
                os.remove('smtp_bridge.log')
                
            with open('smtp_bridge.log', 'w', encoding='utf-8') as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - INFO - Логи очищено\n")
            
            self.log_text.insert(tk.END, f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Логи очищено\n")
            messagebox.showinfo("Успіх", "Логи повністю очищено!")
            
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка очищення логів: {e}")
    
    def copy_all_logs(self):
        """Копіювання всіх логів у буфер обміну"""
        try:
            logs_content = ""
            
            if os.path.exists('smtp_bridge.log'):
                with open('smtp_bridge.log', 'r', encoding='utf-8') as f:
                    logs_content = f.read()
            
            if not logs_content:
                logs_content = self.log_text.get(1.0, tk.END)
            
            if logs_content.strip():
                self.root.clipboard_clear()
                self.root.clipboard_append(logs_content)
                self.root.update()
                
                lines_count = len(logs_content.split('\n'))
                messagebox.showinfo("Успіх", f"Всі логи скопійовано у буфер обміну!\nРядків: {lines_count}")
            else:
                messagebox.showwarning("Попередження", "Логи порожні, нічого копіювати")
                
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка копіювання логів: {e}")
    
    def minimize_to_tray(self):
        """Згортання в системний трей"""
        try:
            import pystray
            from PIL import Image, ImageDraw
            
            if self.tray_icon:
                return
                
            image = Image.new('RGB', (64, 64), color=(0, 100, 200))
            draw = ImageDraw.Draw(image)
            draw.rectangle([16, 16, 48, 48], fill=(255, 255, 255))
            draw.text((24, 28), "S", fill=(0, 0, 0), anchor="mm")
            
            menu = pystray.Menu(
                pystray.MenuItem("Показати вікно", self.show_from_tray),
                pystray.MenuItem("Зупинити сервер", self.stop_server_tray),
                pystray.MenuItem("Перезапустити сервер", self.restart_server_tray),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Вихід", self.quit_from_tray)
            )
            
            self.tray_icon = pystray.Icon(
                "smtp_bridge", 
                image, 
                "SMTP-Telegram міст SAMPO", 
                menu
            )
            
            self.root.withdraw()
            
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
            
            self.logger.info("Програма згорнута в системний трей")
            
        except ImportError:
            messagebox.showerror("Помилка", "Бібліотека pystray не знайдена!\nСистемний трей недоступний.")
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка згортання в трей: {e}")
    
    def silent_minimize_to_tray(self):
        """Тихе згортання в системний трей без повідомлень"""
        try:
            import pystray
            from PIL import Image, ImageDraw
            
            if self.tray_icon:
                return
                
            image = Image.new('RGB', (64, 64), color=(0, 100, 200))
            draw = ImageDraw.Draw(image)
            draw.rectangle([16, 16, 48, 48], fill=(255, 255, 255))
            draw.text((24, 28), "S", fill=(0, 0, 0), anchor="mm")
            
            menu = pystray.Menu(
                pystray.MenuItem("Показати вікно", self.show_from_tray),
                pystray.MenuItem("Зупинити сервер", self.stop_server_tray),
                pystray.MenuItem("Перезапустити сервер", self.restart_server_tray),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Вихід", self.quit_from_tray)
            )
            
            self.tray_icon = pystray.Icon(
                "smtp_bridge", 
                image, 
                "SMTP-Telegram міст SAMPO", 
                menu
            )
            
            self.root.withdraw()
            
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
            
            self.logger.info("Програма автоматично згорнута в системний трей")
            
        except:
            # Якщо не вдається згорнути в трей - просто продовжуємо без помилок
            pass
    
    def show_from_tray(self, icon=None, item=None):
        """Показати вікно з трею"""
        self.root.deiconify()
        self.root.lift()
    
    def stop_server_tray(self, icon=None, item=None):
        """Зупинити сервер з трею"""
        self.stop_server()
    
    def restart_server_tray(self, icon=None, item=None):
        """Перезапустити сервер з трею"""
        self.stop_server()
        import time
        time.sleep(1)
        self.start_server()
    
    def quit_from_tray(self, icon=None, item=None):
        """Вихід з трею"""
        if self.tray_icon:
            self.tray_icon.stop()
        self.stop_server()
        self.root.quit()
    
    def add_to_startup(self):
        """Додавання в автозавантаження Windows"""
        try:
            import winreg
            import sys
            
            exe_path = sys.executable if hasattr(sys, 'frozen') else sys.argv[0]
            exe_path = os.path.abspath(exe_path)
            
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            winreg.SetValueEx(key, "SMTP-Telegram-Bridge-SAMPO", 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            
            messagebox.showinfo("Успіх", "Програма додана в автозавантаження Windows!")
            self.logger.info("Програма додана в автозавантаження")
            
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося додати в автозавантаження: {e}")
            self.logger.error(f"Помилка додавання в автозавантаження: {e}")
    
    def remove_from_startup(self):
        """Видалення з автозавантаження Windows"""
        try:
            import winreg
            
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            try:
                winreg.DeleteValue(key, "SMTP-Telegram-Bridge-SAMPO")
                messagebox.showinfo("Успіх", "Програма видалена з автозавантаження Windows!")
                self.logger.info("Програма видалена з автозавантаження")
            except FileNotFoundError:
                messagebox.showinfo("Інформація", "Програма не була в автозавантаженні")
            
            winreg.CloseKey(key)
            
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося видалити з автозавантаження: {e}")
            self.logger.error(f"Помилка видалення з автозавантаження: {e}")
    
    def on_closing(self):
        """Обробка закриття вікна"""
        result = messagebox.askyesnocancel(
            "Вихід", 
            "Що ви хочете зробити?\n\n"
            "Так - Згорнути в трей (продовжити роботу)\n"
            "Ні - Повністю закрити програму\n"
            "Скасувати - Залишитися у вікні"
        )
        
        if result is True:
            self.minimize_to_tray()
        elif result is False:
            if self.tray_icon:
                self.tray_icon.stop()
            self.stop_server()
            self.root.destroy()
    
    def auto_start_server(self):
        """Автоматичний запуск сервера"""
        if not self.server and self.config.get("auto_start", True):
            if self.config["telegram_token"] and self.config["telegram_chat_id"]:
                self.logger.info("Автозапуск SMTP сервера...")
                self.start_server()
            else:
                self.status_var.set("❌ Автозапуск неможливий - не вказано Token або Chat ID")
                messagebox.showwarning("Попередження", 
                    "Автозапуск SMTP сервера неможливий!\n\n"
                    "Будь ласка, введіть Telegram Bot Token та Chat ID у налаштуваннях, "
                    "збережіть їх, а потім запустіть сервер вручну або перезапустіть програму."
                )
    
    def refresh_logs(self):
        """Автооновлення логів"""
        try:
            if os.path.exists('smtp_bridge.log'):
                with open('smtp_bridge.log', 'r', encoding='utf-8') as f:
                    logs = f.readlines()
                    
                recent_logs = logs[-100:] if len(logs) > 100 else logs
                
                current_content = self.log_text.get(1.0, tk.END)
                new_content = ''.join(recent_logs)
                
                if new_content != current_content.strip():
                    self.log_text.delete(1.0, tk.END)
                    self.log_text.insert(tk.END, new_content)
                    self.log_text.see(tk.END)
        except:
            pass
        
        self.root.after(2000, self.refresh_logs)
    
    def run(self):
        """Запуск застосунку"""
        self.root.mainloop()

if __name__ == "__main__":
    app = SMTPBridgeApp()
    app.run()
