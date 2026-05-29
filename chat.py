import sys
if sys.__stdout__ is None:
    class DummyStream:
        def fileno(self): return 1
        def write(self, text): pass
        def flush(self): pass
    sys.__stdout__ = DummyStream()
    sys.__stdin__ = DummyStream()
    sys.__stderr__ = DummyStream()

import os
import time
import random
import threading
import curses
import firebase_admin
import re
import ssl
import logging
import requests
import locale
import json

from cryptography.fernet import Fernet

try:
    locale.setlocale(locale.LC_ALL, '')
except Exception:
    pass

logging.basicConfig(filename="xrl_error.log", level=logging.ERROR, 
                    format="%(asctime)s - %(levelname)s - %(message)s")

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError: 
    pass
else: 
    ssl._create_default_https_context = _create_unverified_https_context

# =====================================================================
#    КОНФИГУРАЦИЯ И НАСТРОЙКИ
# =====================================================================
VERSION = "1.6.7"  

FIREBASE_WEB_API_KEY_1 = "AIzaSyCXdIbA64CrRWq8-RGDc_LcNVPD_5bJL84"
FIREBASE_WEB_API_KEY_2 = "AIzaSyAQzzGsmH4o3ZgFFZM017kw9zG0HRe7ZBg"  

KEY = b'uX7Y8Z9a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8=' 
cipher = Fernet(KEY)

URL_SERVER_1 = "https://server1-42f9f-default-rtdb.europe-west1.firebasedatabase.app"
URL_SERVER_2 = "https://xrl-chat-default-rtdb.europe-west1.firebasedatabase.app"
# =====================================================================

class XRLChat:
    def __init__(self):
        self.session = "Loading..."
        self.auth_token = None  
        self.nick = "thoned"
        self.running = True
        self.cache_file = "xrl_cache.txt"
        self.config_file = "xrl_config.txt"
        self.theme_file = "xrl_theme.json"
        self.news_file = "news.json"
        
        self.current_app_name = 'server1'
        self.current_url = URL_SERVER_1
        self.current_api_key = FIREBASE_WEB_API_KEY_1
        
        self.messages_dict = {}  
        self.groups_raw = {} 
        self.news_data = []
        self.current_path = "messages/chat"
        self.needs_update = True
        self.in_chat = False
        
        # Раздельные локи во избежание Deadlock при потере фокуса
        self.msg_lock = threading.Lock()
        self.group_lock = threading.Lock()

        self.theme = {
            "colors": {
                "text_background": 16,     
                "text_primary": 255,       
                "text_accent": 255,        
                "gradient": [255, 255, 255, 255, 255, 255, 255, 255] 
            },
            "ui": {
                "header_text": " [  F E N I X  //  C H A T  ] ",
                "separator_char": "=",
                "msg_prefix": "[{name}]: ",
                "input_prefix": " > ",
                "logo": [
                    r"    ______ ______ _   __ ____ _  __",
                    r"   / ____// ____// | / //  _// |/ /",
                    r"  / __/  / __/  /  |/ / / /  |   / ",
                    r" / /    / /___ / /|  /_/ /_ /   |  ",
                    r"/_/    /_____//_/ |_//____//_/|_|  "
                ]
            }
        }

        if not os.path.exists(self.cache_file): 
            open(self.cache_file, 'w', encoding="utf-8").close()
        
        self.load_settings()
        self.load_theme()
        self.load_news()
        self.load_msg_cache()

    def encrypt(self, text): 
        return cipher.encrypt(text.encode('utf-8')).decode('utf-8')
        
    def decrypt(self, token):
        try: 
            return cipher.decrypt(token.encode('utf-8')).decode('utf-8')
        except Exception: 
            return None

    def load_settings(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved_nick = f.read().strip()
                    if saved_nick:
                        self.nick = saved_nick
            except Exception as e:
                logging.error(f"Ошибка загрузки настроек: {e}")

    def save_settings(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(self.nick)
        except Exception as e:
            logging.error(f"Ошибка保存настроек: {e}")

    def load_theme(self):
        if os.path.exists(self.theme_file):
            try:
                with open(self.theme_file, "r", encoding="utf-8") as f:
                    user_theme = json.load(f)
                    if "colors" in user_theme:
                        self.theme["colors"].update(user_theme["colors"])
                    if "ui" in user_theme:
                        self.theme["ui"].update(user_theme["ui"])
            except Exception as e:
                logging.error(f"Ошибка чтения файла темы: {e}")
        else:
            try:
                clean_ui = dict(self.theme["ui"])
                clean_ui["logo"] = [line.replace("\\", "\\\\") for line in clean_ui["logo"]]
                
                json_payload = {
                    "colors": self.theme["colors"],
                    "ui": clean_ui
                }
                with open(self.theme_file, "w", encoding="utf-8") as f:
                    json.dump(json_payload, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logging.error(f"Не удалось создать дефолтный файл темы: {e}")

    def load_news(self):
        if os.path.exists(self.news_file):
            try:
                with open(self.news_file, "r", encoding="utf-8") as f:
                    self.news_data = json.load(f)
            except Exception as e:
                logging.error(f"Ошибка чтения файла новостей: {e}")
                self.news_data = [{"title": "Ошибка", "content": "Файл news.json поврежден."}]
        else:
            try:
                self.news_data = [] 
                with open(self.news_file, "w", encoding="utf-8") as f:
                    json.dump(self.news_data, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logging.error(f"Не удалось создать файл новостей: {e}")

    def authenticate_anonymously(self):
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={self.current_api_key}"
        payload = {"returnSecureToken": True}
        try:
            response = requests.post(url, json=payload, timeout=10)
            res_data = response.json()
            if response.status_code == 200 and "localId" in res_data:
                full_uid = res_data["localId"]
                self.auth_token = res_data["idToken"]  
                self.session = full_uid[:8] + "..."
                return True
            else:
                logging.error(f"Firebase Auth Error: {res_data.get('error', {}).get('message', 'Unknown error')}")
                return False
        except Exception as e:
            logging.error(f"Исключение при авторизации Auth: {e}")
            return False

    def load_msg_cache(self):
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                idx = 0
                for line in f:
                    dec = line.strip()
                    if "send-message" in dec: 
                        self.process_msg(f"local_cache_{idx}", dec)
                        idx += 1
        except Exception as e:
            logging.error(f"Ошибка загрузки кэша: {e}")

    def update_groups_data(self):
        try:
            url = f"{self.current_url}/messages/groups_list.json"
            params = {}
            if self.auth_token:
                params['auth'] = self.auth_token
                
            res = requests.get(url, params=params, timeout=4)
            if res.status_code == 200:
                data = res.json()
                new_groups = {}
                if data and isinstance(data, dict):
                    for k, v in data.items():
                        raw = v.get('payload') if isinstance(v, dict) else v
                        dec = self.decrypt(raw)
                        if dec: 
                            new_groups[k] = dec
                with self.group_lock:
                    self.groups_raw = new_groups
                self.needs_update = True
        except Exception as e:
            logging.error(f"Ошибка обновления групп через REST: {e}")

    def sync_chat_messages(self, path):
        if not self.in_chat:
            return
        try:
            url = f"{self.current_url}/{path}.json"
            params = {}
            if self.auth_token:
                params['auth'] = self.auth_token
                
            res = requests.get(url, params=params, timeout=3)
            if res.status_code == 200:
                snap = res.json()
                if snap and isinstance(snap, dict):
                    for k in snap:
                        # Быстрая проверка без лока, чтобы не вешать UI
                        if k in self.messages_dict:
                            continue
                        raw = snap[k].get('payload') if isinstance(snap[k], dict) else snap[k]
                        dec = self.decrypt(raw)
                        if dec and "send-message" in dec: 
                            self.process_msg(k, dec, save=True)
                self.needs_update = True
        except Exception as e:
            logging.error(f"Ошибка фонового обновления сообщений: {e}")

    def start_background_sync(self):
        def loop():
            while self.running:
                if self.in_chat:
                    self.sync_chat_messages(self.current_path)
                else:
                    self.update_groups_data()
                time.sleep(1.5)  
        threading.Thread(target=loop, daemon=True).start()

    def process_msg(self, msg_id, dec, save=False):
        match = re.search(r"send-message \((.*?)\) \((.*?)\) \((.*?)\) \>(.*)\<", dec)
        if not match:
            match = re.search(r"\(.*?\)\s\((.*?)\)\s\((.*?)\)\s>(.*)<", dec)
            
        if match:
            if len(match.groups()) == 4:
                _, ses, name, txt = match.groups()
            else:
                ses, name, txt = match.groups()
                
            prefix = self.theme["ui"]["msg_prefix"].format(name=name, session=ses)
            m = f"{prefix}{txt}"
            
            with self.msg_lock:
                self.messages_dict[msg_id] = m
                
            if save:
                try:
                    with open(self.cache_file, "a", encoding="utf-8") as f: 
                        f.write(dec + "\n")
                except Exception as e:
                    logging.error(f"Ошибка записи кэша: {e}")

    def draw_smooth_gradient(self, stdscr, y, x, text):
        grad_colors = self.theme["colors"]["gradient"]
        for idx, char in enumerate(text):
            color_pair_idx = 10 + (idx % len(grad_colors))
            try:
                stdscr.addstr(y, x + idx, char, curses.color_pair(color_pair_idx) | curses.A_BOLD)
            except:
                pass

    def draw_big_logo(self, stdscr):
        logo = self.theme["ui"]["logo"]
        for row_idx, line in enumerate(logo):
            try:
                stdscr.addstr(row_idx + 1, 2, line, curses.color_pair(1) | curses.A_BOLD)
            except:
                pass

    def draw_small_header(self, stdscr):
        self.draw_smooth_gradient(stdscr, 1, 2, self.theme["ui"]["header_text"])
        sep_char = self.theme["ui"]["separator_char"][:1]
        stdscr.addstr(2, 2, " " + sep_char*56 + " ", curses.color_pair(1)) 
        room = self.current_path.split('/')[-1]
        srv = "SRV-1" if self.current_app_name == "server1" else "SRV-2"
        stdscr.addstr(3, 2, f" session : {self.session} | room: {room} | {srv}", curses.color_pair(1))
        stdscr.addstr(4, 2, f" nick    : {self.nick}", curses.color_pair(1))

    def safe_input(self, stdscr, y, x, prompt):
        stdscr.timeout(-1)  
        curses.curs_set(1)
        input_str = ""
        while True:
            stdscr.move(y, x)
            stdscr.clrtoeol()
            stdscr.addstr(y, x, prompt, curses.color_pair(1)) 
            stdscr.addstr(y, x + len(prompt), input_str + "_ ", curses.color_pair(1))
            stdscr.refresh()
            try:
                ch = stdscr.get_wch()
            except:
                time.sleep(0.02) # Защита от флуда ошибками при потере фокуса окна
                stdscr.touchwin()  
                stdscr.redrawwin()
                continue

            if ch in [10, 13, '\n', '\r']:
                break
            elif ch in [8, 127, 263, '\b', '\x7f', curses.KEY_BACKSPACE, 'KEY_BACKSPACE']:
                input_str = input_str[:-1]
            elif ch == curses.KEY_RESIZE:
                stdscr.touchwin()
                continue
            elif isinstance(ch, str) and len(ch) == 1:
                if ord(ch) >= 32:
                    input_str += ch
                
        curses.curs_set(0)
        return input_str.strip()

    def open_chat(self, stdscr, path):
        self.in_chat = True
        self.current_path = path
        self.messages_dict = {}
        
        try:
            url = f"{self.current_url}/{path}.json"
            params = {}
            if self.auth_token:
                params['auth'] = self.auth_token
            res = requests.get(url, params=params, timeout=4)
            if res.status_code == 200:
                snap = res.json()
                if snap and isinstance(snap, dict):
                    for k in snap:
                        raw = snap[k].get('payload') if isinstance(snap[k], dict) else snap[k]
                        dec = self.decrypt(raw)
                        if dec: 
                            self.process_msg(k, dec)
            else:
                self.messages_dict["err"] = "!! ОШИБКА ДОСТУПА К БАЗЕ !!"
        except Exception as e:
            logging.error(f"Не удалось получить доступ к чату ({path}): {e}")
            self.messages_dict["err"] = "!! ОШИБКА СЕТИ !!"
            
        user_input = ""
        stdscr.timeout(100) 
        
        while self.in_chat:
            stdscr.bkgd(' ', curses.color_pair(1))
            stdscr.erase()
            self.draw_small_header(stdscr)
            stdscr.addstr(6, 2, f" --- ROOM: {path} (type '/exit') ---", curses.color_pair(1))
            
            with self.msg_lock:
                current_msgs = list(self.messages_dict.values())
            
            for i, msg in enumerate(current_msgs[-14:]):
                try:
                    stdscr.addstr(8 + i, 2, msg[:75], curses.color_pair(1))
                except:
                    pass
            
            try:
                in_pref = self.theme["ui"]["input_prefix"]
                full_input_line = f"{self.nick}{in_pref}{user_input}"
                stdscr.move(23, 2)
                stdscr.clrtoeol()
                stdscr.addstr(23, 2, full_input_line[:75] + "_", curses.color_pair(1) | curses.A_BOLD)
            except:
                pass
            
            stdscr.refresh()

            try:
                key = stdscr.get_wch()
            except:
                time.sleep(0.03) # Предотвращает зависание панели ввода при потере фокуса
                continue

            if key == curses.KEY_RESIZE:
                stdscr.touchwin()
                continue

            if key in [10, 13, '\n', '\r']:
                if user_input == "/exit": 
                    self.in_chat = False
                    break
                if user_input.strip():
                    pkt = f"send-message ({path}) ({self.session}) ({self.nick}) >{user_input}<"
                    
                    local_id = f"temp_{random.randint(1000,9999)}_{time.time()}"
                    self.process_msg(local_id, pkt, save=True)
                    
                    def send_worker(post_url, payload_pkt, auth_params, tmp_id):
                        try:
                            res = requests.post(post_url, json={'payload': self.encrypt(payload_pkt)}, params=auth_params, timeout=6)
                            if res.status_code == 200:
                                # Удаляем локальное эхо только после подтверждения сервером
                                # Используем msg_lock безопасно
                                threading.Timer(0.5, lambda: self.messages_dict.pop(tmp_id, None)).start()
                        except Exception as e:
                            logging.error(f"Ошибка асинхронной отправки: {e}")
                    
                    url = f"{self.current_url}/{path}.json"
                    params = {}
                    if self.auth_token:
                        params['auth'] = self.auth_token
                        
                    threading.Thread(target=send_worker, args=(url, pkt, params, local_id), daemon=True).start()
                    user_input = ""
            
            elif key in [8, 127, 263, '\b', '\x7f', curses.KEY_BACKSPACE, 'KEY_BACKSPACE']: 
                user_input = user_input[:-1]
                
            elif isinstance(key, str) and len(key) == 1: 
                if ord(key) >= 32:
                    user_input += key

        stdscr.timeout(-1) 
        self.in_chat = False

    def open_groups(self, stdscr):
        while True:
            parsed = []
            with self.group_lock:
                current_groups = dict(self.groups_raw)

            for db_key, dec in current_groups.items():
                m = re.search(r"create-group \((.*?)\) \((.*?)\) \((.*?)\)", dec)
                if m: 
                    parsed.append({'pw': m.group(1), 'id': m.group(2), 'name': m.group(3)})
            
            opts = ["+ Refresh", "+ Create", "+ Connect ID"] + [f"ID:{p['id']} | {p['name']}" for p in parsed] + ["Back"]
            idx = 0
            while True:
                stdscr.bkgd(' ', curses.color_pair(1))
                stdscr.erase()
                self.draw_small_header(stdscr)
                stdscr.addstr(6, 2, " [ GROUPS ] ", curses.color_pair(1))
                for i, opt in enumerate(opts):
                    style = curses.A_REVERSE if i == idx else curses.color_pair(1)
                    try:
                        stdscr.addstr(8 + i, 4, f" > {opt} ", style)
                    except:
                        pass
                stdscr.refresh()
                try:
                    key = stdscr.get_wch()
                except:
                    time.sleep(0.02)
                    stdscr.touchwin()
                    stdscr.redrawwin()
                    continue

                if key == curses.KEY_UP or key == 'k': 
                    if idx > 0: idx -= 1
                elif key == curses.KEY_DOWN or key == 'j': 
                    if idx < len(opts)-1: idx += 1
                elif key == curses.KEY_RESIZE:
                    stdscr.touchwin()
                    continue
                elif key in [10, 13, '\n', '\r']: 
                    break
                elif key in ['b', 'B']: 
                    idx = len(opts)-1
                    break

            res = opts[idx]
            if res == "+ Refresh": 
                self.update_groups_data()
                continue
            elif res == "+ Create":
                name = self.safe_input(stdscr, 18, 2, " Name: ")
                pw = self.safe_input(stdscr, 19, 2, " Pass: ")
                if name and pw:
                    gid = str(random.randint(1, 99999))
                    pkt = f"create-group ({pw}) ({gid}) ({name})"
                    try:
                        url = f"{self.current_url}/messages/groups_list.json"
                        params = {}
                        if self.auth_token:
                            params['auth'] = self.auth_token
                        requests.post(url, json={'payload': self.encrypt(pkt)}, params=params, timeout=5)
                        self.update_groups_data()
                    except Exception as e:
                        logging.error(f"Ошибка создания группы: {e}")
                break
            elif res == "+ Connect ID":
                target_id = self.safe_input(stdscr, 18, 2, " Enter ID: ")
                group = next((p for p in parsed if p['id'] == target_id), None)
                if group:
                    input_pw = self.safe_input(stdscr, 19, 2, " Enter Pass: ")
                    if input_pw == group['pw']: 
                        self.open_chat(stdscr, f"messages/groups/{target_id}")
                    else: 
                        stdscr.addstr(21, 2, "!! WRONG PASS !!", curses.color_pair(1))
                        stdscr.refresh()
                        time.sleep(1)
                else: 
                    stdscr.addstr(19, 2, "!! ID NOT FOUND !!", curses.color_pair(1))
                    stdscr.refresh()
                    time.sleep(1)
                break
            elif "ID:" in res:
                g = parsed[idx-3]
                pw = self.safe_input(stdscr, 18, 2, f" Pass for {g['name']}: ")
                if pw == g['pw']: 
                    self.open_chat(stdscr, f"messages/groups/{g['id']}")
                    break
                else: 
                    stdscr.addstr(20, 2, "!! WRONG !!", curses.color_pair(1))
                    stdscr.refresh()
                    time.sleep(1)
                    break
            elif res == "Back": 
                break

    def open_servers(self, stdscr):
        s_opts = ["Server 1 (42f9f)", "Server 2 (Default)", "Back"]
        s_idx = 0
        while True:
            stdscr.bkgd(' ', curses.color_pair(1))
            stdscr.erase()
            self.draw_small_header(stdscr)
            stdscr.addstr(6, 2, " [ SERVERS ] ", curses.color_pair(1))
            
            cur_srv = "Server 1" if self.current_app_name == 'server1' else "Server 2"
            stdscr.addstr(7, 4, f"Current Database: {cur_srv}", curses.color_pair(1))
            
            for i, o in enumerate(s_opts):
                style = curses.A_REVERSE if i == s_idx else curses.color_pair(1)
                stdscr.addstr(9+i, 4, f" > {o} ", style)
            stdscr.refresh()
            try:
                k = stdscr.get_wch()
            except:
                time.sleep(0.02)
                stdscr.touchwin()
                stdscr.redrawwin()
                continue

            if k == curses.KEY_UP or k == 'k': 
                if s_idx > 0: s_idx -= 1
            elif k == curses.KEY_DOWN or k == 'j': 
                if s_idx < len(s_opts)-1: s_idx += 1
            elif k == curses.KEY_RESIZE:
                stdscr.touchwin()
                continue
            elif k in [10, 13, '\n', '\r']:
                sel_opt = s_opts[s_idx]
                
                changed = False
                if sel_opt == "Server 1 (42f9f)" and self.current_app_name != 'server1':
                    self.current_app_name = 'server1'
                    self.current_url = URL_SERVER_1
                    self.current_api_key = FIREBASE_WEB_API_KEY_1
                    changed = True
                elif sel_opt == "Server 2 (Default)" and self.current_app_name != 'server2':
                    self.current_app_name = 'server2'
                    self.current_url = URL_SERVER_2
                    self.current_api_key = FIREBASE_WEB_API_KEY_2
                    changed = True
                
                if changed:
                    stdscr.erase()
                    self.draw_small_header(stdscr)
                    stdscr.addstr(10, 4, " Переавторизация на новом сервере... ", curses.A_REVERSE)
                    stdscr.refresh()
                    
                    if self.authenticate_anonymously():
                        with self.group_lock:
                            self.groups_raw = {}
                        self.update_groups_data()
                        stdscr.addstr(13, 4, " Успешно переключено! ", curses.color_pair(1) | curses.A_BOLD)
                    else:
                        stdscr.addstr(13, 4, " Ошибка авторизации на сервере! ", curses.A_REVERSE)
                    
                    stdscr.refresh()
                    time.sleep(1.5)
                    break
                elif sel_opt == "Back":
                    break
            elif k in ['b', 'B']: 
                break

    def view_news_item(self, stdscr, item):
        while True:
            stdscr.bkgd(' ', curses.color_pair(1))
            stdscr.erase()
            self.draw_small_header(stdscr)
            title = item.get("title", "Без названия")
            content = item.get("content", "")
            
            stdscr.addstr(6, 2, f" --- {title} --- ", curses.color_pair(1) | curses.A_BOLD)
            
            words = content.split(' ')
            lines = []
            current_line = ""
            for w in words:
                if len(current_line) + len(w) + 1 < 70:
                    current_line += w + " "
                else:
                    lines.append(current_line)
                    current_line = w + " "
            if current_line:
                lines.append(current_line)
                
            for i, l in enumerate(lines[:12]): 
                try:
                    stdscr.addstr(8+i, 4, l, curses.color_pair(1))
                except:
                    pass
                    
            stdscr.addstr(22, 4, "Нажмите любую клавишу для возврата...", curses.A_REVERSE)
            stdscr.refresh()
            try:
                stdscr.get_wch()
            except:
                pass
            break

    def open_news(self, stdscr):
        self.load_news() 
        n_idx = 0
        while True:
            stdscr.bkgd(' ', curses.color_pair(1))
            stdscr.erase()
            self.draw_small_header(stdscr)
            stdscr.addstr(6, 2, " [ NEWS ] ", curses.color_pair(1))
            
            if not self.news_data:
                stdscr.addstr(8, 4, "Нет доступных новостей.", curses.color_pair(1))
                opts = ["Back"]
            else:
                n_opts = [item.get("title", "Без названия") for item in self.news_data]
                opts = n_opts + ["Back"]

            for i, o in enumerate(opts):
                style = curses.A_REVERSE if i == n_idx else curses.color_pair(1)
                try:
                    display_text = f" > {o} "[:60]
                    stdscr.addstr(8+i, 4, display_text, style)
                except:
                    pass

            stdscr.refresh()
            try:
                k = stdscr.get_wch()
            except:
                time.sleep(0.02)
                stdscr.touchwin()
                stdscr.redrawwin()
                continue

            if k == curses.KEY_UP or k == 'k': 
                if n_idx > 0: n_idx -= 1
            elif k == curses.KEY_DOWN or k == 'j': 
                if n_idx < len(opts)-1: n_idx += 1
            elif k == curses.KEY_RESIZE:
                stdscr.touchwin()
                continue
            elif k in [10, 13, '\n', '\r']:
                if n_idx == len(opts) - 1: 
                    break
                else:
                    self.view_news_item(stdscr, self.news_data[n_idx])
            elif k in ['b', 'B']: 
                break

    def open_settings(self, stdscr):
        s_opts = ["Change Nick", "Reset Session", "Back"]
        s_idx = 0
        while True:
            stdscr.bkgd(' ', curses.color_pair(1))
            stdscr.erase()
            self.draw_small_header(stdscr)
            stdscr.addstr(6, 2, " [ SETTINGS ] ", curses.color_pair(1))
            for i, o in enumerate(s_opts):
                style = curses.A_REVERSE if i == s_idx else curses.color_pair(1)
                stdscr.addstr(8+i, 4, f" > {o} ", style)
            stdscr.refresh()
            try:
                k = stdscr.get_wch()
            except:
                time.sleep(0.02)
                stdscr.touchwin()
                stdscr.redrawwin()
                continue

            if k == curses.KEY_UP or k == 'k': 
                if s_idx > 0: s_idx -= 1
            elif k == curses.KEY_DOWN or k == 'j': 
                if s_idx < len(s_opts)-1: s_idx += 1
            elif k == curses.KEY_RESIZE:
                stdscr.touchwin()
                continue
            elif k in [10, 13, '\n', '\r']:
                sel_opt = s_opts[s_idx]
                if sel_opt == "Change Nick":
                    new_nick = self.safe_input(stdscr, 12, 4, " New Nick: ")
                    if new_nick:
                        self.nick = new_nick
                        self.save_settings()
                    break
                elif sel_opt == "Reset Session":
                    stdscr.erase()
                    self.draw_small_header(stdscr)
                    stdscr.addstr(10, 4, " Получение нового ID... ", curses.A_REVERSE)
                    stdscr.refresh()
                    
                    if self.authenticate_anonymously():
                        stdscr.addstr(12, 4, " Сессия успешно обновлена! ", curses.color_pair(1))
                    else:
                        stdscr.addstr(12, 4, " Ошибка сети! Сгенерирован временный ID... ", curses.color_pair(1))
                        self.session = f"{random.randint(1, 99999)}"
                        self.auth_token = None
                    
                    self.needs_update = True
                    stdscr.refresh()
                    time.sleep(1.5)
                    break
                elif sel_opt == "Back": 
                    break
            elif k in ['b', 'B']: 
                break

    def open_credits(self, stdscr):
        while True:
            stdscr.bkgd(' ', curses.color_pair(1))
            stdscr.erase()
            self.draw_small_header(stdscr)
            stdscr.addstr(8, 4, "--- FENIX-CHAT PROJECT ---", curses.color_pair(1) | curses.A_BOLD)
            stdscr.addstr(10, 6, "Creators      : xrl-def", curses.color_pair(1))
            stdscr.addstr(11, 6, "Creators      : fenix", curses.color_pair(1))
            stdscr.addstr(12, 6, "AI Assistant  : Gemini AI", curses.color_pair(1))
            stdscr.addstr(14, 6, f"Version       : {VERSION} (Custom Theme Engine)", curses.color_pair(1))
            stdscr.addstr(17, 4, "Press any key to return...", curses.A_REVERSE)
            stdscr.refresh()
            try:
                stdscr.get_wch()
            except:
                pass
            break

    def run(self, stdscr):
        curses.start_color()
        curses.use_default_colors()
        
        bg = self.theme["colors"]["text_background"]
        primary = self.theme["colors"]["text_primary"]
        accent = self.theme["colors"]["text_accent"]
        
        curses.init_pair(1, primary, bg) 
        curses.init_pair(2, accent, bg)   
        
        grad_colors = self.theme["colors"]["gradient"]
        for idx, color_code in enumerate(grad_colors):
            curses.init_pair(10 + idx, color_code, bg)
        
        stdscr.bkgd(' ', curses.color_pair(1))
        curses.curs_set(0)
        stdscr.keypad(True)
        
        stdscr.erase()
        self.draw_big_logo(stdscr)
        stdscr.addstr(7, 4, " Подключение к защищенной сети Firebase Auth... ", curses.A_REVERSE)
        stdscr.refresh()
        
        if not self.authenticate_anonymously():
            stdscr.addstr(9, 4, " ОШИБКА АВТОРИЗАЦИИ! Проверь Web API Key или сеть. ", curses.color_pair(1))
            stdscr.refresh()
            time.sleep(3)
            return

        self.start_background_sync()

        main_sel = 0
        main_opts = ["Chat", "Groups", "Servers", "News", "Settings", "Credits", "Exit"]
        
        while self.running:
            stdscr.erase()
            self.draw_big_logo(stdscr) 
            srv = "SRV-1" if self.current_app_name == "server1" else "SRV-2"
            
            stdscr.addstr(7, 4, f" session : {self.session} (Auth OK) | nick : {self.nick} | v{VERSION} | {srv}", curses.color_pair(1))
            
            for i, o in enumerate(main_opts):
                style = curses.A_REVERSE | curses.A_BOLD if i == main_sel else curses.color_pair(1)
                stdscr.addstr(8 + i, 6, f" [ {o} ] ", style)
            stdscr.refresh()
            try:
                k = stdscr.get_wch()
            except:
                time.sleep(0.02)
                stdscr.touchwin()
                stdscr.redrawwin()
                continue

            if (k == curses.KEY_UP or k == 'k') and main_sel > 0: 
                main_sel -= 1
            elif (k == curses.KEY_DOWN or k == 'j') and main_sel < len(main_opts)-1: 
                main_sel += 1
            elif k == curses.KEY_RESIZE:
                stdscr.touchwin()
                continue
            elif k in [10, 13, '\n', '\r']:
                if main_sel == 0: self.open_chat(stdscr, "messages/chat")
                elif main_sel == 1: self.open_groups(stdscr)
                elif main_sel == 2: self.open_servers(stdscr)
                elif main_sel == 3: self.open_news(stdscr)    
                elif main_sel == 4: self.open_settings(stdscr)
                elif main_sel == 5: self.open_credits(stdscr)
                elif main_sel == 6: 
                    self.running = False
                    break

if __name__ == "__main__":
    chat = XRLChat()
    curses.wrapper(chat.run)
