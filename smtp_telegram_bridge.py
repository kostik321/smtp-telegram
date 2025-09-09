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
                    data = sock.recv(4096)  # Увеличен буфер
                    
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
                    
                    # Обработка SMTP команд (без изменений)
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
                            import base64
                            username = base64.b64decode(command).decode('utf-8', errors='ignore')
                            self.logger.info(f"Username: {username}")
                        except:
                            self.logger.info(f"Username (raw): {command}")
                        auth_stage = "password"
                        self.send_response(sock, "334 UGFzc3dvcmQ6")
                        
                    elif auth_stage == "password":
                        try:
                            import base64
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
