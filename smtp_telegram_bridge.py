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

CONFIG_FILE = "smtp_config.json"

class FakeSSLSMTPServer:
    def __init__(self, host='localhost', port=465, token='', chat_id='', logger=None):
        self.host = host
        self.port = port
        self.token = token
        self.chat_id = chat_id
        self.logger = logger or logging.getLogger(__name__)
        self.running = False
        self.server_socket = None
        
    def start(self):
        """Запуск поддельного SSL SMTP сервера"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            
            self.running = True
            self.logger.info(f"Fake SSL SMTP сервер запущен на {self.host}:{self.port}")
            
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
                    if self.running:
                        self.logger.error("Ошибка сокета")
                    break
                    
        except Exception as e:
            self.logger.error(f"Ошибка запуска сервера: {e}")
            
    def handle_client(self, client_socket):
        """Обработка клиента с простой эмуляцией SSL"""
        try:
            # Отправляем "успешный" SSL handshake ответ
            # Многие клиенты просто проверяют что соединение установлено
            self.logger.info("Эмулируем SSL handshake")
            
            # Простая эмуляция - отправляем данные как будто SSL установлен
            self.smtp_session(client_socket)
            
        except Exception as e:
            self.logger.error(f"Ошибка обработки клиента: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def smtp_session(self, sock):
        """SMTP сессия с обработкой команд"""
        try:
            # Даем время на "SSL handshake"
            import time
            time.sleep(0.1)
            
            # Отправляем приветствие SMTP
            self.send_response(sock, "220 localhost ESMTP SSL Ready")
            
            email_data = ""
            in_data_mode = False
            auth_stage = None
            mail_from = ""
            rcpt_to = []
            
            while True:
                try:
                    # Получаем данные с тайм-аутом
                    sock.settimeout(30)
                    data = sock.recv(1024)
                    
                    if not data:
                        break
                    
                    # Декодируем с обработкой ошибок
                    try:
                        command = data.decode('utf-8', errors='ignore').strip()
                    except:
                        command = str(data, errors='ignore').strip()
                    
                    if not command:
                        continue
                        
                    self.logger.info(f"Команда: {command}")
                    
                    if in_data_mode:
                        # Обработка данных письма построчно
                        lines = command.split('\n')
                        for line in lines:
                            line = line.strip('\r')
                            if line == ".":
                                # Конец данных письма
                                in_data_mode = False
                                self.logger.info("Получен терминатор данных")
                                try:
                                    self.send_response(sock, "250 2.0.0 Message accepted for delivery")
                                    self.process_email(email_data, mail_from, rcpt_to)
                                    email_data = ""
                                    mail_from = ""
                                    rcpt_to = []
                                    self.logger.info("Письмо обработано успешно")
                                except Exception as e:
                                    self.logger.error(f"Ошибка обработки письма: {e}")
                                    try:
                                        self.send_response(sock, "450 4.0.0 Temporary failure") 
                                    except:
                                        pass
                                break
                            else:
                                email_data += line + "\n"
                        continue
                    
                    # Обработка команд
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
                        self.logger.info(f"Начинаем аутентификацию: {auth_type}")
                        
                        if auth_type == "LOGIN":
                            auth_stage = "username"
                            self.send_response(sock, "334 VXNlcm5hbWU6")  # "Username:" в base64
                        elif auth_type == "PLAIN":
                            # Можем обработать PLAIN сразу или запросить данные
                            if len(cmd_parts) > 2:
                                # Данные уже переданы
                                self.logger.info("AUTH PLAIN с данными")
                                self.send_response(sock, "235 2.7.0 Authentication successful")
                            else:
                                self.send_response(sock, "334 ")
                        else:
                            self.send_response(sock, "235 2.7.0 Authentication successful")
                            
                    elif auth_stage == "username":
                        # Получили username в base64
                        try:
                            username = base64.b64decode(command).decode('utf-8', errors='ignore')
                            self.logger.info(f"Username: {username}")
                        except:
                            self.logger.info(f"Username (raw): {command}")
                        
                        auth_stage = "password"
                        self.send_response(sock, "334 UGFzc3dvcmQ6")  # "Password:" в base64
                        
                    elif auth_stage == "password":
                        # Получили password в base64
                        try:
                            password = base64.b64decode(command).decode('utf-8', errors='ignore')
                            self.logger.info(f"Password: {password}")
                        except:
                            self.logger.info(f"Password (raw): {command}")
                        
                        auth_stage = None
                        self.send_response(sock, "235 2.7.0 Authentication successful")
                        self.logger.info("Аутентификация успешна")
                        
                    elif cmd == "MAIL":
                        # MAIL FROM:<sender@example.com>
                        if "FROM:" in command.upper():
                            mail_from = command.split("FROM:", 1)[1].strip()
                            mail_from = mail_from.strip("<>")
                            self.logger.info(f"Mail from: {mail_from}")
                            self.send_response(sock, "250 2.1.0 Ok")
                        else:
                            self.send_response(sock, "250 2.1.0 Ok")
                        
                    elif cmd == "RCPT":
                        # RCPT TO:<recipient@example.com>  
                        if "TO:" in command.upper():
                            rcpt = command.split("TO:", 1)[1].strip()
                            rcpt = rcpt.strip("<>")
                            rcpt_to.append(rcpt)
                            self.logger.info(f"Recipient: {rcpt}")
                            self.send_response(sock, "250 2.1.5 Ok")
                        else:
                            self.send_response(sock, "250 2.1.5 Ok")
                        
                    elif cmd == "DATA":
                        self.send_response(sock, "354 End data with <CR><LF>.<CR><LF>")
                        in_data_mode = True
                        self.logger.info("Начинаем получение данных письма")
                        
                    elif cmd == "QUIT":
                        self.send_response(sock, "221 2.0.0 Bye")
                        break
                        
                    elif cmd == "RSET":
                        # Сброс состояния
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
                        # Неизвестная команда - все равно отвечаем OK
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
                    break
                    
        except Exception as e:
            self.logger.error(f"Ошибка SMTP сессии: {e}")
    
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
            
            # Парсинг email
            try:
                msg = email.message_from_string(email_data)
                subject = self.decode_header(msg.get('Subject', 'Без темы'))
                sender = self.decode_header(msg.get('From', mail_from or 'Неизвестный отправитель'))
                
                # Извлечение тела письма
                body = self.extract_body(msg)
                
                self.logger.info(f"Тема: {subject}")
                self.logger.info(f"От: {sender}")
                self.logger.info(f"Тело: {body[:100]}...")
                
                # Отправка в Telegram
                self.send_to_telegram(subject, sender, body)
                
            except Exception as e:
                self.logger.error(f"Ошибка парсинга email: {e}")
                # Отправляем сырые данные в Telegram
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
        """Извлечение тела письма"""
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain":
                        charset = part.get_content_charset() or 'utf-8'
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            return payload.decode(charset, errors='ignore')
                        return str(payload)
            else:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode(charset, errors='ignore')
                return str(payload)
        except Exception as e:
            self.logger.error(f"Ошибка извлечения тела письма: {e}")
        
        return "Не удалось извлечь содержимое письма"
    
    def send_to_telegram(self, subject, sender, body):
        """Отправка в Telegram"""
        try:
            message = "📧 *Отчет о продажах*\n\n"
            message += f"*От:* {sender}\n"
            message += f"*Тема:* {subject}\n"
            message += f"*Время:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            message += "=" * 30 + "\n\n"
            
            if len(body) > 3000:
                body = body[:3000] + "\n\n... [сообщение обрезано]"
            
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
                logging.FileHandler('smtp_fake_ssl.log', encoding='utf-8'),
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
        self.root.title("SMTP-Telegram мост (Fake SSL)")
        self.root.geometry("700x600")
        
        # Информация
        info_frame = ttk.LabelFrame(self.root, text="Эмуляция SSL SMTP Сервера")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        info_text = tk.Text(info_frame, height=4, wrap=tk.WORD)
        info_text.pack(fill=tk.X, padx=5, pady=5)
        info_text.insert(tk.END, 
            "Эмулирует SSL SMTP сервер для касс требующих SSL.\n"
            "В кассе: localhost:465 (или другой порт)\n"
            "Логин/пароль: любые, SSL: включен\n"
            "Сервер принимает подключения как SSL, но без настоящего TLS шифрования."
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
        
        ttk.Label(settings_frame, text="(465-SSL, 587-STARTTLS, 25-обычный)").grid(row=2, column=2, sticky=tk.W, padx=5, pady=2)
        
        settings_frame.columnconfigure(1, weight=1)
        
        # Кнопки
        buttons_frame = ttk.Frame(self.root)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_btn = ttk.Button(buttons_frame, text="Запустить Fake SSL", command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(buttons_frame, text="Остановить", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(buttons_frame, text="Сохранить", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Тест Telegram", command=self.test_telegram).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Очистить логи", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        
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
            self.status_var.set(f"Fake SSL SMTP запущен на localhost:{port}")
            
            messagebox.showinfo("Успех", f"Fake SSL SMTP сервер запущен на порту {port}!\n\nВ кассе укажите:\nSMTP: localhost:{port}\nSSL: включен")
            
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
                'text': f"🔒 Fake SSL SMTP-Telegram тест\n\nВремя: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\nГотов принимать отчеты!"
            }
            
            response = requests.post(url, data=payload, timeout=10)
            
            if response.status_code == 200:
                messagebox.showinfo("Успех", "Тестовое сообщение отправлено!")
            else:
                messagebox.showerror("Ошибка", f"Ошибка API: {response.text}")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка подключения: {e}")
    
    def clear_logs(self):
        """Очистка логов"""
        try:
            self.log_text.delete(1.0, tk.END)
            if os.path.exists('smtp_fake_ssl.log'):
                os.remove('smtp_fake_ssl.log')
        except:
            pass
    
    def refresh_logs(self):
        """Автообновление логов"""
        try:
            if os.path.exists('smtp_fake_ssl.log'):
                with open('smtp_fake_ssl.log', 'r', encoding='utf-8') as f:
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
