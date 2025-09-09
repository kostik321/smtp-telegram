#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import ssl
import email
import requests
from datetime import datetime
import json
import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

CONFIG_FILE = "smtp_config.json"

class SimpleSSLSMTPServer:
    def __init__(self, host='localhost', port=465, token='', chat_id='', logger=None):
        self.host = host
        self.port = port
        self.token = token
        self.chat_id = chat_id
        self.logger = logger or logging.getLogger(__name__)
        self.running = False
        self.server_socket = None
        
    def start(self):
        """Запуск SSL SMTP сервера"""
        try:
            # Создание самоподписанного сертификата
            self.create_self_signed_cert()
            
            # Создание сокета
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            
            self.running = True
            self.logger.info(f"SSL SMTP сервер запущен на {self.host}:{self.port}")
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    self.logger.info(f"Подключение от {address}")
                    
                    # Обработка клиента в отдельном потоке
                    client_thread = threading.Thread(
                        target=self.handle_client, 
                        args=(client_socket,),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.error:
                    break
                    
        except Exception as e:
            self.logger.error(f"Ошибка запуска SSL сервера: {e}")
            
    def create_self_signed_cert(self):
        """Создание самоподписанного сертификата"""
        try:
            import ssl
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            import datetime
            
            # Генерация приватного ключа
            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            
            # Создание сертификата
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
            ])
            
            cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.datetime.utcnow()
            ).not_valid_after(
                datetime.datetime.utcnow() + datetime.timedelta(days=365)
            ).sign(key, hashes.SHA256())
            
            # Сохранение файлов
            with open("server.crt", "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            
            with open("server.key", "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
                
            self.logger.info("Самоподписанный сертификат создан")
            
        except ImportError:
            self.logger.warning("Библиотека cryptography не найдена, используем упрощенный режим")
            # Создаем пустые файлы для совместимости
            with open("server.crt", "w") as f:
                f.write("")
            with open("server.key", "w") as f:
                f.write("")
        
    def handle_client(self, client_socket):
        """Обработка клиента"""
        try:
            # Попытка SSL handshake (если возможно)
            if os.path.exists("server.crt") and os.path.getsize("server.crt") > 0:
                try:
                    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    context.load_cert_chain("server.crt", "server.key")
                    
                    ssl_socket = context.wrap_socket(client_socket, server_side=True)
                    self.logger.info("SSL соединение установлено")
                except Exception as e:
                    self.logger.warning(f"SSL handshake не удался, работаем без шифрования: {e}")
                    ssl_socket = client_socket
            else:
                ssl_socket = client_socket
            
            # SMTP протокол
            self.smtp_session(ssl_socket)
            
        except Exception as e:
            self.logger.error(f"Ошибка обработки клиента: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def smtp_session(self, sock):
        """SMTP сессия"""
        try:
            # Приветствие
            self.send_response(sock, "220 localhost ESMTP Ready")
            
            email_data = ""
            in_data_mode = False
            auth_stage = None
            
            while True:
                try:
                    data = sock.recv(1024).decode('utf-8', errors='ignore').strip()
                    if not data:
                        break
                        
                    self.logger.info(f"Получена команда: {data}")
                    
                    if in_data_mode:
                        if data == ".":
                            # Конец данных письма
                            in_data_mode = False
                            self.send_response(sock, "250 Message accepted")
                            self.process_email(email_data)
                            email_data = ""
                        else:
                            email_data += data + "\n"
                        continue
                    
                    cmd = data.upper().split()[0] if data else ""
                    
                    if cmd == "HELO" or cmd == "EHLO":
                        if cmd == "EHLO":
                            response = "250-localhost\n250-AUTH LOGIN PLAIN\n250 8BITMIME"
                        else:
                            response = "250 localhost"
                        self.send_response(sock, response)
                        
                    elif cmd == "AUTH":
                        auth_type = data.split()[1].upper() if len(data.split()) > 1 else "LOGIN"
                        if auth_type == "LOGIN":
                            auth_stage = "username"
                            self.send_response(sock, "334 VXNlcm5hbWU6")  # "Username:" в base64
                        elif auth_type == "PLAIN":
                            self.send_response(sock, "235 Authentication successful")
                        else:
                            self.send_response(sock, "235 Authentication successful")
                            
                    elif auth_stage == "username":
                        auth_stage = "password"
                        self.send_response(sock, "334 UGFzc3dvcmQ6")  # "Password:" в base64
                        
                    elif auth_stage == "password":
                        auth_stage = None
                        self.send_response(sock, "235 Authentication successful")
                        
                    elif cmd == "MAIL":
                        self.send_response(sock, "250 Sender OK")
                        
                    elif cmd == "RCPT":
                        self.send_response(sock, "250 Recipient OK")
                        
                    elif cmd == "DATA":
                        self.send_response(sock, "354 Start mail input")
                        in_data_mode = True
                        
                    elif cmd == "QUIT":
                        self.send_response(sock, "221 Bye")
                        break
                        
                    elif cmd == "STARTTLS":
                        self.send_response(sock, "220 Ready to start TLS")
                        # Здесь должен быть TLS handshake
                        
                    else:
                        self.send_response(sock, "250 OK")
                        
                except socket.error:
                    break
                    
        except Exception as e:
            self.logger.error(f"Ошибка SMTP сессии: {e}")
    
    def send_response(self, sock, response):
        """Отправка ответа клиенту"""
        try:
            sock.send((response + "\r\n").encode('utf-8'))
        except:
            pass
    
    def process_email(self, email_data):
        """Обработка полученного письма"""
        try:
            self.logger.info("Обработка полученного письма")
            
            # Парсинг email
            msg = email.message_from_string(email_data)
            subject = msg.get('Subject', 'Без темы')
            sender = msg.get('From', 'Неизвестный отправитель')
            
            # Извлечение тела письма
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
            else:
                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            
            # Отправка в Telegram
            self.send_to_telegram(subject, sender, body)
            
        except Exception as e:
            self.logger.error(f"Ошибка обработки письма: {e}")
    
    def send_to_telegram(self, subject, sender, body):
        """Отправка в Telegram"""
        try:
            message = f"📧 *Отчет о продажах*\n\n"
            message += f"*От:* {sender}\n"
            message += f"*Тема:* {subject}\n"
            message += f"*Время:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            message += f"{'='*30}\n\n"
            
            if len(body) > 3500:
                body = body[:3500] + "\n\n... [обрезано]"
            
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
                self.logger.error(f"❌ Ошибка Telegram: {response.text}")
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка отправки в Telegram: {e}")
    
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
                logging.FileHandler('smtp_ssl.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        self.create_gui()
    
    def load_config(self):
        """Загрузка конфигурации"""
        default = {
            "telegram_token": "",
            "telegram_chat_id": "",
            "smtp_host": "localhost", 
            "smtp_port": 465
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
        self.root.title("SMTP-Telegram мост с SSL")
        self.root.geometry("650x550")
        
        # Информация
        info_frame = ttk.LabelFrame(self.root, text="SSL SMTP Сервер")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        info_text = tk.Text(info_frame, height=3, wrap=tk.WORD)
        info_text.pack(fill=tk.X, padx=5, pady=5)
        info_text.insert(tk.END, "Поддерживает SSL/TLS подключения на порту 465.\n" + 
                                "В кассе: localhost:465, логин/пароль любые, SSL включен")
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
        ttk.Label(settings_frame, text="Порт SSL:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.port_var = tk.StringVar(value=str(self.config["smtp_port"]))
        ttk.Entry(settings_frame, textvariable=self.port_var, width=10).grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)
        
        settings_frame.columnconfigure(1, weight=1)
        
        # Кнопки
        buttons_frame = ttk.Frame(self.root)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_btn = ttk.Button(buttons_frame, text="Запустить SSL", command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(buttons_frame, text="Остановить", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(buttons_frame, text="Сохранить", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Тест Telegram", command=self.test_telegram).pack(side=tk.LEFT, padx=5)
        
        # Логи
        logs_frame = ttk.LabelFrame(self.root, text="Логи")
        logs_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(logs_frame, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Статус
        self.status_var = tk.StringVar()
        self.status_var.set("Остановлено")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Загрузка логов
        self.refresh_logs()
    
    def start_server(self):
        """Запуск сервера"""
        if not self.config["telegram_token"] or not self.config["telegram_chat_id"]:
            messagebox.showerror("Ошибка", "Укажите Token и Chat ID!")
            return
        
        try:
            port = int(self.port_var.get())
            self.server = SimpleSSLSMTPServer(
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
            self.status_var.set(f"SSL SMTP запущен на localhost:{port}")
            
            messagebox.showinfo("Успех", f"SSL SMTP сервер запущен на порту {port}!")
            
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
                'text': f"🔒 SSL SMTP-Telegram тест\n\nВремя: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            }
            
            response = requests.post(url, data=payload, timeout=10)
            
            if response.status_code == 200:
                messagebox.showinfo("Успех", "Тестовое сообщение отправлено!")
            else:
                messagebox.showerror("Ошибка", f"Ошибка API: {response.text}")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка подключения: {e}")
    
    def refresh_logs(self):
        """Обновление логов"""
        try:
            if os.path.exists('smtp_ssl.log'):
                with open('smtp_ssl.log', 'r', encoding='utf-8') as f:
                    logs = f.read()
                    self.log_text.delete(1.0, tk.END)
                    self.log_text.insert(tk.END, logs)
                    self.log_text.see(tk.END)
        except:
            pass
        
        # Автообновление каждые 2 секунды
        self.root.after(2000, self.refresh_logs)
    
    def run(self):
        """Запуск приложения"""
        self.root.mainloop()

if __name__ == "__main__":
    app = SMTPBridgeApp()
    app.run()
