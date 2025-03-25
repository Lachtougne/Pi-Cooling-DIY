import paramiko
import customtkinter as ctk
import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.ttk as ttk
import time
import datetime
import matplotlib
from collections import deque, defaultdict
import socket
import logging
import os
import json
import csv
import concurrent.futures
import re
import matplotlib.colors as mcolors
import random

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    filename="dashboard.log",
    filemode="a"
)

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

CONFIG_FILE = "config.json"

def smooth_transition(current, target, alpha=0.2, seuil=20):
    if abs(target - current) > seuil:
        return target
    return current + alpha * (target - current)

def animate_button_color_lr(button, start_color, end_color, steps=20, delay=20):
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0,2,4))
    def rgb_to_hex(rgb):
        return "#%02x%02x%02x" % rgb
    start_rgb = hex_to_rgb(start_color)
    end_rgb = hex_to_rgb(end_color)
    width = button.winfo_width()
    height = button.winfo_height()
    if width <= 1 or height <= 1:
        button.after(100, lambda: animate_button_color_lr(button, start_color, end_color, steps, delay))
        return
    canvas = tk.Canvas(button, width=width, height=height, highlightthickness=0, bd=0)
    canvas.place(x=0, y=0)
    def step(i):
        if i > steps:
            canvas.destroy()
            button.configure(fg_color=end_color)
            return
        new_width = int(width * i / steps)
        canvas.delete("all")
        canvas.create_rectangle(0, 0, new_width, height, fill=end_color, outline="")
        canvas.create_rectangle(new_width, 0, width, height, fill=start_color, outline="")
        button.after(delay, lambda: step(i+1))
    step(0)

def apply_char_spacing(text, spacing):
    if spacing <= 0:
        return text
    spacer = " " * spacing
    return spacer.join(list(text))

def get_color_for_usage(usage):
    if usage < 10:
        return "#0000FF"
    elif usage < 50:
        return "#00FF00"
    elif usage < 80:
        return "#FFA500"
    else:
        return "#FF0000"

def get_color_for_temp(temp):
    if temp < 40:
        return "#0000FF"
    elif temp < 60:
        return "#00FF00"
    elif temp < 70:
        return "#FFA500"
    else:
        return "#FF0000"

def compute_gradient_color(fraction):
    stops = [(0,0,255), (0,255,0), (255,165,0), (255,0,0)]
    if fraction <= 0:
        return "#0000ff"
    if fraction >= 1:
        return "#ff0000"
    total_intervals = len(stops) - 1
    scaled = fraction * total_intervals
    idx = int(scaled)
    t = scaled - idx
    start = stops[idx]
    end = stops[idx+1]
    r = int(start[0] + t*(end[0]-start[0]))
    g = int(start[1] + t*(end[1]-start[1]))
    b = int(start[2] + t*(end[2]-start[2]))
    return f"#{r:02x}{g:02x}{b:02x}"

def load_config():
    default_config = {
        "refresh_interval": 1000,
        "cpu_alert_threshold": 90.0,
        "temp_alert_threshold": 80.0,
        "net_interface": "wlan0",
        "font_size": 18,
        "enable_history": True,
        "bar_width": 200,
        "bar_height": 20,
        "cpu_alert_color": "#FF0000",
        "temp_alert_color": "#FFA500",
        "window_width": 940,
        "window_height": 380,
        "font_color": "White",
        "row_spacing": 5,
        "col_spacing": 10,
        "char_spacing": 0,
        "enable_animations": False,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            logging.info("Configuration chargée depuis config.json")
            return config
        except Exception as e:
            logging.error(f"Erreur lors du chargement de la config : {e}")
    return default_config

def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        logging.info("Configuration sauvegardée dans config.json")
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde de la config : {e}")

def get_recalbox_ip():
    try:
        ip = socket.gethostbyname("recalbox")
        if ip.startswith("192.168"):
            logging.info(f"Recalbox détecté via DNS à l'adresse : {ip}")
            print(f"✅ Recalbox détecté à l'adresse : {ip}")
            return ip
    except socket.gaierror:
        logging.warning("Impossible de résoudre 'recalbox' via DNS. Passage au scan...")
    possible_ips = [f"192.168.1.{i}" for i in range(2,255)]
    def scan_ip(ip):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(ip, port=22, username="root", password="recalboxroot", timeout=2)
            client.close()
            return ip
        except Exception:
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(scan_ip, ip): ip for ip in possible_ips}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                logging.info(f"Recalbox détecté par scan à l'adresse : {result}")
                print(f"✅ Recalbox détecté à l'adresse : {result}")
                return result
    logging.error("Recalbox introuvable sur le réseau.")
    print("❌ Recalbox introuvable sur le réseau.")
    return None

class SSHManager:
    def __init__(self, hostname, port, username, password):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.connect()

    def connect(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(self.hostname, self.port, self.username, self.password)
            logging.info(f"Connexion SSH établie avec {self.hostname}")
        except Exception as e:
            logging.error(f"[Erreur SSH] Impossible de se connecter à {self.hostname} : {e}")
            self.client = None

    def execute_command(self, command):
        if self.client is None:
            self.connect()
        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            output = stdout.read().decode().strip()
            return output
        except Exception as e:
            logging.error(f"[Erreur SSH] Commande échouée '{command}' : {e}")
            return "N/A"

    def close(self):
        if self.client:
            self.client.close()
            logging.info(f"Connexion SSH fermée pour {self.hostname}")
            self.client = None

def fetch_all_stats(ssh_manager):
    commands = [
        "grep '^cpu ' /proc/stat",
        "grep '^cpu[0-3] ' /proc/stat",
        "free -m | grep Mem:",
        "vcgencmd measure_temp | grep -o '[0-9]*\\.[0-9]*'",
        "ps aux | grep 'retroarch' | grep -Eo '([a-zA-Z0-9_]+)_libretro' | head -n 1",
        "ps aux | grep 'retroarch' | grep -v 'grep' | awk '{for(i=11;i<=NF;i++) printf \"%s \", $i; print \"\"}'"
    ]
    combined_command = " && ".join(commands)
    output = ssh_manager.execute_command(combined_command)
    if output and output != "N/A":
        lines = output.splitlines()
        return {
            "cpu": lines[0] if len(lines) > 0 else "",
            "cores": lines[1:5] if len(lines) > 4 else [""] * 4,
            "mem": lines[5] if len(lines) > 5 else "",
            "temp": lines[6] if len(lines) > 6 else "0.0",
            "emulator": lines[7] if len(lines) > 7 else "Aucun",
            "game": lines[8] if len(lines) > 8 else ""
        }
    return None

class AnimatedCTkButton(ctk.CTkButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configure(fg_color="#0000FF")
    def animate(self, event):
        self.configure(fg_color="#0000FF")

class App(ctk.CTk):
    def __init__(self, ssh_manager):
        super().__init__()
        self.ssh_manager = ssh_manager
        self.config = load_config()
        self.state('zoomed')
        self.after(100, lambda: self.state('zoomed'))
        self.minsize(940, 450)
        self.title("Dashboard SSH Recalbox")
        if not self.state() == 'zoomed':
            window_width = self.config.get("window_width", 940)
            window_height = self.config.get("window_height", 450)
            self.geometry(f"{window_width}x{window_height}")
        self.bg_color = "#121212"
        self.fg_color = "#e0e0e0"
        self.prev_cpu_stat = None
        self.cpu_load_history = deque(maxlen=60)
        self.cpu_temp_history = deque(maxlen=60)
        self.ram_usage_history = deque(maxlen=60)
        self.imbalance_history = deque(maxlen=60)
        self.prev_core_stats = [None] * 4
        self.core_histories = [deque(maxlen=60) for _ in range(4)]
        self.last_core_usage = [0, 0, 0, 0]
        self.displayed_vertical_usage = {}
        self.session_data = deque(maxlen=3600)
        self.session_start_time = time.time()
        self.current_game = ""
        self.last_emulator = "Aucun"
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.net_zero_counter = 0
        self.net_zero_threshold = 3
        self.create_hidden_button()
        self.create_tabview()
        self.displayed_cpu_usage = 0.0
        self.displayed_ram_usage = 0.0
        self.displayed_cpu_temp = 0.0
        self.displayed_imbalance = 0.0
        self.displayed_core_usage = [0.0, 0.0, 0.0, 0.0]
        self.core_imbalance = 0.0
        self.imbalance_window_size = 10
        self.core_usage_window = deque(maxlen=self.imbalance_window_size)
        self.core_killer_alert = False
        self.update_all_stats()

    def create_hidden_button(self):
        self.hidden_button = ctk.CTkButton(self, text="Hidden", command=lambda: None, fg_color="#0000FF")
        self.hidden_button.place_forget()

    def get_cell_bg(self, i):
        if i in [5,6,7,8,9,15,16,17,18,19]:
            return "#1c1c1c"
        elif i in [0,1,3,4,10,11,13,14]:
            return "#232323"
        else:
            return "#121212"

    def create_graph_cell(self, master, fig_attr, ax_attr, canvas_attr, line_attr, color, figsize=(3, 2)):
        setattr(self, fig_attr, Figure(figsize=figsize, dpi=100, facecolor=self.bg_color))
        ax = getattr(self, fig_attr).add_subplot(111, facecolor=self.bg_color)
        setattr(self, ax_attr, ax)
        ax.tick_params(axis="x", colors=self.fg_color)
        ax.tick_params(axis="y", colors=self.fg_color)
        ax.set_xticklabels([])
        line, = ax.plot([], [], color=color)
        setattr(self, line_attr, line)
        canvas = FigureCanvasTkAgg(getattr(self, fig_attr), master=master)
        setattr(self, canvas_attr, canvas)
        canvas.get_tk_widget().pack(expand=True, fill="both")
        canvas.get_tk_widget().config(highlightthickness=0, bd=0)

    def create_tabview(self):
        self.tabview = ctk.CTkTabview(self, width=800)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=self.config["col_spacing"],
                          pady=self.config["row_spacing"])
        self.tabview.add("Dashboard")
        self.tabview.add("Résumé")
        try:
            segmented_button = self.tabview._segmented_button
            for child in segmented_button.winfo_children():
                child.configure(fg_color="#0000FF")
                child.unbind("<Button-1>")
        except Exception as e:
            logging.warning(f"Erreur lors de la configuration des onglets : {e}")

        dashboard_frame = ctk.CTkFrame(self.tabview.tab("Dashboard"), fg_color=self.bg_color)
        dashboard_frame.pack(expand=True, fill="both")
        rows, cols = 5, 5
        for r in range(rows):
            dashboard_frame.grid_rowconfigure(r, weight=1, uniform="row")
        for c in range(cols):
            dashboard_frame.grid_columnconfigure(c, weight=1, uniform="col")
        for i in range(25):
            if i == 24:
                continue
            r = i // cols
            c = i % cols
            cell_bg = self.get_cell_bg(i)
            cell = ctk.CTkFrame(dashboard_frame, fg_color=cell_bg, border_width=0)
            if i == 23:
                cell.grid(row=r, column=c, columnspan=2, padx=self.config["col_spacing"],
                          pady=self.config["row_spacing"], sticky="nsew")
                self.merged_label = ctk.CTkLabel(cell, text="Jeu en cours : ?", text_color=self.fg_color,
                                                 font=("Arial", 18), fg_color=cell_bg)
                self.merged_label.pack(expand=True)
            else:
                cell.grid(row=r, column=c, padx=self.config["col_spacing"],
                          pady=self.config["row_spacing"], sticky="nsew")
                if i == 0:
                    self.create_graph_cell(cell, "cpu_load_fig", "cpu_load_ax", "cpu_load_canvas", "cpu_load_line", "purple")
                elif i == 1:
                    self.create_graph_cell(cell, "core1_fig", "core1_ax", "core1_canvas", "core1_line", "lime")
                elif i == 2:
                    ctk.CTkLabel(cell, text="", text_color=self.fg_color,
                                 font=("Arial", self.config.get("font_size", 18)),
                                 fg_color=cell_bg).pack(expand=True)
                elif i == 3:
                    self.create_graph_cell(cell, "core2_fig", "core2_ax", "core2_canvas", "core2_line", "lime")
                elif i == 4:
                    self.create_graph_cell(cell, "ram_usage_fig", "ram_usage_ax", "ram_usage_canvas", "ram_usage_line", "blue")
                elif i == 5:
                    frame_value = ctk.CTkFrame(cell, fg_color=cell_bg, border_width=0)
                    frame_value.pack(expand=True)
                    self.cpu_load_value_label = ctk.CTkLabel(frame_value, text="0.0%", text_color=self.fg_color,
                                                             font=("Arial", 38), fg_color=cell_bg)
                    self.cpu_load_value_label.pack()
                    ctk.CTkLabel(frame_value, text="CPU", text_color=self.fg_color,
                                 font=("Arial", 12), fg_color=cell_bg).pack()
                elif i == 6:
                    frame_value = ctk.CTkFrame(cell, fg_color=cell_bg, border_width=0)
                    frame_value.pack(expand=True)
                    self.core1_value_label = ctk.CTkLabel(frame_value, text="0.0%", text_color=self.fg_color,
                                                          font=("Arial", 38), fg_color=cell_bg)
                    self.core1_value_label.pack()
                    ctk.CTkLabel(frame_value, text="Core 1", text_color=self.fg_color,
                                 font=("Arial", 12), fg_color=cell_bg).pack()
                elif i == 7:
                    vertical_frame = ctk.CTkFrame(cell, fg_color=cell_bg, corner_radius=0)
                    vertical_frame.pack(expand=True, fill="both")
                    self.core_vertical_canvases_1 = []
                    for lbl in ["C1", "C2"]:
                        subframe = ctk.CTkFrame(vertical_frame, fg_color=cell_bg, width=50, height=100)
                        subframe.pack(side="left", expand=True, padx=5, pady=5)
                        canvas = tk.Canvas(subframe, width=30, height=100, bg=cell_bg, highlightthickness=0)
                        canvas.pack(padx=2, pady=2)
                        self.core_vertical_canvases_1.append(canvas)
                        ctk.CTkLabel(subframe, text=lbl, font=("Arial", 14), text_color=self.fg_color,
                                     fg_color=cell_bg).pack(side="bottom", pady=2)
                elif i == 8:
                    frame_value = ctk.CTkFrame(cell, fg_color=cell_bg, border_width=0)
                    frame_value.pack(expand=True)
                    self.core2_value_label = ctk.CTkLabel(frame_value, text="0.0%", text_color=self.fg_color,
                                                          font=("Arial", 38), fg_color=cell_bg)
                    self.core2_value_label.pack()
                    ctk.CTkLabel(frame_value, text="Core 2", text_color=self.fg_color,
                                 font=("Arial", 12), fg_color=cell_bg).pack()
                elif i == 9:
                    frame_value = ctk.CTkFrame(cell, fg_color=cell_bg, border_width=0)
                    frame_value.pack(expand=True)
                    self.ram_usage_value_label = ctk.CTkLabel(frame_value, text="0.0%", text_color=self.fg_color,
                                                              font=("Arial", 38), fg_color=cell_bg)
                    self.ram_usage_value_label.pack()
                    ctk.CTkLabel(frame_value, text="RAM", text_color=self.fg_color,
                                 font=("Arial", 12), fg_color=cell_bg).pack()
                elif i == 10:
                    self.create_graph_cell(cell, "imbalance_fig", "imbalance_ax", "imbalance_canvas", "imbalance_line", "red")
                elif i == 11:
                    self.create_graph_cell(cell, "core3_fig", "core3_ax", "core3_canvas", "core3_line", "lime")
                elif i == 12:
                    self.core_killer_label = ctk.CTkLabel(cell, text="", text_color="#FF0000",
                                                          font=("Arial", 18, "bold"), fg_color=cell_bg)
                    self.core_killer_label.pack(expand=True)
                elif i == 13:
                    self.create_graph_cell(cell, "core4_fig", "core4_ax", "core4_canvas", "core4_line", "lime")
                elif i == 14:
                    self.create_graph_cell(cell, "cpu_temp_fig", "cpu_temp_ax", "cpu_temp_canvas", "cpu_temp_line", "red")
                elif i == 15:
                    frame_value = ctk.CTkFrame(cell, fg_color=cell_bg, border_width=0)
                    frame_value.pack(expand=True)
                    self.imbalance_value_label = ctk.CTkLabel(frame_value, text="0%", text_color=self.fg_color,
                                                             font=("Arial", 38), fg_color=cell_bg)
                    self.imbalance_value_label.pack()
                    ctk.CTkLabel(frame_value, text="Imbalance", text_color=self.fg_color,
                                 font=("Arial", 12), fg_color=cell_bg).pack()
                elif i == 16:
                    frame_value = ctk.CTkFrame(cell, fg_color=cell_bg, border_width=0)
                    frame_value.pack(expand=True)
                    self.core3_value_label = ctk.CTkLabel(frame_value, text="0.0%", text_color=self.fg_color,
                                                          font=("Arial", 38), fg_color=cell_bg)
                    self.core3_value_label.pack()
                    ctk.CTkLabel(frame_value, text="Core 3", text_color=self.fg_color,
                                 font=("Arial", 12), fg_color=cell_bg).pack()
                elif i == 17:
                    vertical_frame = ctk.CTkFrame(cell, fg_color=cell_bg, corner_radius=0)
                    vertical_frame.pack(expand=True, fill="both")
                    self.core_vertical_canvases_2 = []
                    for lbl in ["C3", "C4"]:
                        subframe = ctk.CTkFrame(vertical_frame, fg_color=cell_bg, width=50, height=100)
                        subframe.pack(side="left", expand=True, padx=5, pady=5)
                        canvas = tk.Canvas(subframe, width=30, height=100, bg=cell_bg, highlightthickness=0)
                        canvas.pack(padx=2, pady=2)
                        self.core_vertical_canvases_2.append(canvas)
                        ctk.CTkLabel(subframe, text=lbl, font=("Arial", 14), text_color=self.fg_color,
                                     fg_color=cell_bg).pack(side="bottom", pady=2)
                elif i == 18:
                    frame_value = ctk.CTkFrame(cell, fg_color=cell_bg, border_width=0)
                    frame_value.pack(expand=True)
                    self.core4_value_label = ctk.CTkLabel(frame_value, text="0.0%", text_color=self.fg_color,
                                                          font=("Arial", 38), fg_color=cell_bg)
                    self.core4_value_label.pack()
                    ctk.CTkLabel(frame_value, text="Core 4", text_color=self.fg_color,
                                 font=("Arial", 12), fg_color=cell_bg).pack()
                elif i == 19:
                    frame_value = ctk.CTkFrame(cell, fg_color=cell_bg, border_width=0)
                    frame_value.pack(expand=True)
                    self.cpu_temp_value_label = ctk.CTkLabel(frame_value, text="0.0°C", text_color=self.fg_color,
                                                             font=("Arial", 38), fg_color=cell_bg)
                    self.cpu_temp_value_label.pack()
                    ctk.CTkLabel(frame_value, text="Temp CPU", text_color=self.fg_color,
                                 font=("Arial", 12), fg_color=cell_bg).pack()
                elif i == 20:
                    self.emulator_label = ctk.CTkLabel(cell, text=f"{self.last_emulator}", text_color=self.fg_color,
                                                       font=("Arial", 18), fg_color=cell_bg)
                    self.emulator_label.pack(expand=True)
                else:
                    ctk.CTkLabel(cell, text="", text_color=self.fg_color,
                                 font=("Arial", self.config.get("font_size", 18)),
                                 fg_color=cell_bg).pack(expand=True)

    def clear_history(self):
        if messagebox.askyesno("Confirmation", "Voulez-vous vraiment effacer l'historique ?"):
            filename = "historique_centralise.csv"
            if os.path.exists(filename):
                os.remove(filename)
                logging.info("Historique effacé.")
                self.update_summary_tab()
            else:
                logging.info("Aucun historique à effacer.")

    def update_all_stats(self):
        stats = fetch_all_stats(self.ssh_manager)
        if stats:
            self.update_cpu_load(stats["cpu"])
            self.update_ram_usage(stats["mem"])
            self.update_cpu_temp_usage(stats["temp"])
            self.update_imbalance_usage()
            for i, core_data in enumerate(stats["cores"]):
                self.update_core_usage(i, core_data)
            self.update_game(stats["game"])
            self.update_emulator(stats["emulator"])
            self.net_zero_counter = 0
        else:
            logging.warning("Aucune donnée reçue, tentative de reconnexion si nécessaire.")
            self.net_zero_counter += 1
            if self.net_zero_counter >= self.net_zero_threshold:
                self.reconnect_ssh()
        self.update_core_vertical_bars()
        self.update_misc()
        self.after(self.config.get("refresh_interval", 1000), self.update_all_stats)

    def update_cpu_load(self, output):
        if output:
            parts = output.split()[1:]
            try:
                values = list(map(int, parts))
                total = sum(values)
                idle = values[3] + values[4] if len(values) >= 5 else values[3]
                if self.prev_cpu_stat is not None:
                    prev_total, prev_idle = self.prev_cpu_stat
                    total_diff = total - prev_total
                    idle_diff = idle - prev_idle
                    computed_usage = (total_diff - idle_diff) / total_diff * 100 if total_diff > 0 else 0.0
                else:
                    computed_usage = 0.0
                self.prev_cpu_stat = (total, idle)
                color = get_color_for_usage(computed_usage)
                self.displayed_cpu_usage = smooth_transition(self.displayed_cpu_usage, computed_usage, 0.2)
                self.cpu_load_value_label.configure(text=f"{self.displayed_cpu_usage:.1f}%", text_color=color)
                self.cpu_load_history.append(computed_usage)
                if hasattr(self, "cpu_load_ax"):
                    x_data = range(len(self.cpu_load_history))
                    self.cpu_load_line.set_data(x_data, list(self.cpu_load_history))
                    self.cpu_load_ax.set_xlim(0, max(59, len(self.cpu_load_history) - 1))
                    max_val = max(self.cpu_load_history, default=100) * 1.1
                    self.cpu_load_ax.set_ylim(0, max_val)
                    self.cpu_load_canvas.draw()
            except Exception as e:
                logging.error(f"Erreur lors du calcul de la charge CPU : {e}")

    def update_ram_usage(self, output):
        try:
            parts = output.split()
            if len(parts) < 3:
                raise ValueError("Données RAM incomplètes")
            total = float(parts[1])
            used = float(parts[2])
            computed_usage = used / total * 100 if total != 0 else 0.0
        except (IndexError, ValueError, TypeError) as e:
            logging.error(f"Erreur lors de la lecture de la RAM : {e}")
            computed_usage = 0.0
        self.displayed_ram_usage = smooth_transition(self.displayed_ram_usage, computed_usage, 0.2)
        self.ram_usage_value_label.configure(text=f"{self.displayed_ram_usage:.1f}%", text_color=get_color_for_usage(self.displayed_ram_usage))
        self.ram_usage_history.append(computed_usage)
        if hasattr(self, "ram_usage_ax"):
            x_data = range(len(self.ram_usage_history))
            self.ram_usage_line.set_data(x_data, list(self.ram_usage_history))
            self.ram_usage_ax.set_xlim(0, max(59, len(self.ram_usage_history) - 1))
            max_val = max(self.ram_usage_history, default=100) * 1.1
            self.ram_usage_ax.set_ylim(0, max_val)
            self.ram_usage_canvas.draw()

    def update_cpu_temp_usage(self, output):
        try:
            computed_temp = float(output)
        except (ValueError, TypeError) as e:
            logging.error(f"Erreur lors de la lecture de la température CPU : {e}")
            computed_temp = 0.0
        temp_color = get_color_for_temp(computed_temp)
        self.displayed_cpu_temp = smooth_transition(self.displayed_cpu_temp, computed_temp, 0.2)
        if hasattr(self, "cpu_temp_value_label"):
            self.cpu_temp_value_label.configure(text=f"{self.displayed_cpu_temp:.1f}°C", text_color=temp_color)
        self.cpu_temp_history.append(computed_temp)
        if hasattr(self, "cpu_temp_ax"):
            x_data = range(len(self.cpu_temp_history))
            self.cpu_temp_line.set_data(x_data, list(self.cpu_temp_history))
            self.cpu_temp_ax.set_xlim(0, max(59, len(self.cpu_temp_history) - 1))
            max_val = max(self.cpu_temp_history, default=100) * 1.1
            self.cpu_temp_ax.set_ylim(0, max_val)
            self.cpu_temp_canvas.draw()

    def update_imbalance_usage(self):
        self.imbalance_history.append(self.core_imbalance)
        if hasattr(self, "imbalance_ax"):
            x_data = range(len(self.imbalance_history))
            self.imbalance_line.set_data(x_data, list(self.imbalance_history))
            self.imbalance_ax.set_xlim(0, max(59, len(self.imbalance_history) - 1))
            max_val = max(self.imbalance_history, default=100) * 1.1
            self.imbalance_ax.set_ylim(0, max_val)
            self.imbalance_canvas.draw()

    def update_core_usage(self, core_num, output):
        if output:
            parts = output.split()[1:]
            try:
                values = list(map(int, parts))
                total = sum(values)
                idle = values[3] + values[4] if len(values) >= 5 else values[3]
                if self.prev_core_stats[core_num] is not None:
                    prev_total, prev_idle = self.prev_core_stats[core_num]
                    total_diff = total - prev_total
                    idle_diff = idle - prev_idle
                    computed_usage = (total_diff - idle_diff) / total_diff * 100 if total_diff > 0 else 0.0
                else:
                    computed_usage = 0.0
                self.prev_core_stats[core_num] = (total, idle)
                color = get_color_for_usage(computed_usage)
                self.displayed_core_usage[core_num] = smooth_transition(self.displayed_core_usage[core_num], computed_usage, 0.2)
                core_labels = [self.core1_value_label, self.core2_value_label, self.core3_value_label, self.core4_value_label]
                core_lines = [self.core1_line, self.core2_line, self.core3_line, self.core4_line]
                core_canvases = [self.core1_canvas, self.core2_canvas, self.core3_canvas, self.core4_canvas]
                core_axes = [self.core1_ax, self.core2_ax, self.core3_ax, self.core4_ax]
                core_labels[core_num].configure(text=f"{self.displayed_core_usage[core_num]:.1f}%", text_color=color)
                self.core_histories[core_num].append(computed_usage)
                self.last_core_usage[core_num] = computed_usage
                if core_lines[core_num]:
                    x_data = range(len(self.core_histories[core_num]))
                    core_lines[core_num].set_data(x_data, list(self.core_histories[core_num]))
                    core_axes[core_num].set_xlim(0, max(59, len(self.core_histories[core_num]) - 1))
                    max_val = max(self.core_histories[core_num], default=100) * 1.1
                    core_axes[core_num].set_ylim(0, max_val)
                    core_canvases[core_num].draw()
            except Exception as e:
                logging.error(f"Erreur lors du calcul de la charge Core{core_num + 1} : {e}")

    def animate_vertical_bar(self, canvas, start, end, steps=10, delay=30):
        if hasattr(canvas, "animation_id"):
            canvas.after_cancel(canvas.animation_id)
        def ease_out(t):
            return 1 - (1 - t) ** 2
        def step(i):
            if i <= steps:
                fraction = i / steps
                eased = ease_out(fraction)
                current_usage = start + (end - start) * eased
                self.draw_vertical_bar(canvas, current_usage)
                self.displayed_vertical_usage[canvas] = current_usage
                canvas.animation_id = canvas.after(delay, lambda: step(i+1))
            else:
                self.draw_vertical_bar(canvas, end)
                self.displayed_vertical_usage[canvas] = end
                if hasattr(canvas, "animation_id"):
                    delattr(canvas, "animation_id")
        step(0)

    def draw_vertical_bar(self, canvas, usage):
        canvas_height = int(canvas['height'])
        canvas_width = int(canvas['width'])
        fill_height = int((usage / 100) * canvas_height)
        if usage > 0 and fill_height < 10:
            fill_height = 10
        canvas.delete("all")
        grad_color = compute_gradient_color(usage / 100)
        canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill=self.bg_color, outline="")
        canvas.create_rectangle(0, canvas_height - fill_height, canvas_width, canvas_height, fill=grad_color, outline="")

    def update_core_vertical_bars(self):
        if self.core_vertical_canvases_1:
            for idx, canvas in enumerate(self.core_vertical_canvases_1):
                target = self.last_core_usage[idx]
                current = self.displayed_vertical_usage.get(canvas, 0)
                if self.config.get("enable_animations", False):
                    self.animate_vertical_bar(canvas, current, target, steps=10, delay=30)
                else:
                    self.draw_vertical_bar(canvas, target)
                    self.displayed_vertical_usage[canvas] = target
        if self.core_vertical_canvases_2:
            for idx, canvas in enumerate(self.core_vertical_canvases_2):
                target = self.last_core_usage[idx+2]
                current = self.displayed_vertical_usage.get(canvas, 0)
                if self.config.get("enable_animations", False):
                    self.animate_vertical_bar(canvas, current, target, steps=10, delay=30)
                else:
                    self.draw_vertical_bar(canvas, target)
                    self.displayed_vertical_usage[canvas] = target

    def update_misc(self):
        test_output = self.ssh_manager.execute_command("echo test")
        if test_output == "N/A" and self.net_zero_counter >= self.net_zero_threshold:
            logging.info(f"Test de connexion échoué (compteur = {self.net_zero_counter})")
        sample = {
            "timestamp": time.time(),
            "cpu_usage": self.displayed_cpu_usage,
            "ram_usage": self.displayed_ram_usage,
            "cpu_temp": self.displayed_cpu_temp,
            "core1": self.displayed_core_usage[0],
            "core2": self.displayed_core_usage[1],
            "core3": self.displayed_core_usage[2],
            "core4": self.displayed_core_usage[3],
            "core_imbalance": self.core_imbalance
        }
        self.core_usage_window.append([sample["core1"], sample["core2"], sample["core3"], sample["core4"]])
        if len(self.core_usage_window) >= self.imbalance_window_size:
            max_cores = [max(cores) for cores in self.core_usage_window]
            min_cores = [min(cores) for cores in self.core_usage_window]
            avg_max = sum(max_cores) / len(max_cores)
            avg_min = sum(min_cores) / len(min_cores)
            self.core_imbalance = avg_max - avg_min
            color = get_color_for_usage(self.core_imbalance)
            self.imbalance_value_label.configure(text=f"{self.core_imbalance:.1f}%", text_color=color)
            max_core_usage = max(self.last_core_usage)
            if max_core_usage > 80 and self.core_imbalance > 50 and not self.core_killer_alert:
                self.core_killer_label.configure(text="TUEUR DE CORE")
                self.core_killer_alert = True
                logging.info(f"Alerte : Tueur de Core détecté ! Max usage : {max_core_usage:.1f}%, Imbalance : {self.core_imbalance:.1f}%")
            if not hasattr(self, 'ignore_data_until') or sample["timestamp"] > self.ignore_data_until:
                logging.info(f"Rolling Imbalance (20s window): {self.core_imbalance:.1f}%")
        if not hasattr(self, 'ignore_data_until') or sample["timestamp"] > self.ignore_data_until:
            self.session_data.append(sample)

    def reconnect_ssh(self):
        logging.info("Tentative de reconnexion SSH...")
        self.ssh_manager.close()
        new_hostname = get_recalbox_ip()
        if new_hostname:
            self.ssh_manager = SSHManager(new_hostname, self.ssh_manager.port, self.ssh_manager.username, self.ssh_manager.password)
            if self.ssh_manager.client:
                logging.info(f"Reconnexion réussie avec l'IP : {new_hostname}")
                print(f"✅ Reconnexion réussie avec l'IP : {new_hostname}")
            else:
                logging.error("Reconnexion échouée malgré la nouvelle IP.")
                print("❌ Reconnexion échouée malgré la nouvelle IP.")
        else:
            logging.error("Nouvelle IP introuvable sur le réseau.")
            print("❌ Impossible de retrouver une nouvelle IP sur le réseau.")
        self.net_zero_counter = 0

    def update_game(self, new_game):
        if new_game:
            game_name = new_game.split('/')[-1].split('.')[0]
            game_name = re.sub(r'\([^)]*\)', '', game_name)
            game_name = re.sub(r'\[[^]]*\]', '', game_name)
            game_name = game_name.strip()
            new_game = game_name if game_name else ""
        if new_game != self.current_game and self.current_game:
            self.export_current_session()
            self.session_data = deque(maxlen=3600)
            self.session_start_time = time.time()
            self.ignore_data_until = self.session_start_time + 5
            self.core_usage_window.clear()
            self.imbalance_history = []
            self.core_killer_alert = False
            self.core_killer_label.configure(text="")
            self.update_summary_tab()
        self.current_game = new_game
        self.merged_label.configure(text=f"{new_game}")

    def update_emulator(self, new_emulator):
        if new_emulator != "Aucun":
            self.last_emulator = new_emulator.replace("_libretro", "")
        display_emulator = self.last_emulator if new_emulator == "Aucun" else new_emulator.replace("_libretro", "")
        self.emulator_label.configure(text=f"{display_emulator}")

    def export_current_session(self):
        if not self.session_data:
            return
        session_end = time.time()
        def agg(metric):
            values = [d[metric] for d in self.session_data]
            avg = sum(values)/len(values) if values else 0
            return avg, min(values) if values else 0, max(values) if values else 0
        
        cpu_stats = agg("cpu_usage")
        ram_stats = agg("ram_usage")
        cpu_temp_stats = agg("cpu_temp")
        core1_stats = agg("core1")
        core2_stats = agg("core2")
        core3_stats = agg("core3")
        core4_stats = agg("core4")
        core_imbalance_stats = agg("core_imbalance")
        core_imbalance = core_imbalance_stats[0]
        
        filename = "historique_centralise.csv"
        file_exists = os.path.exists(filename)
        with open(filename, mode="a", newline="") as csvfile:
            fieldnames = ["game", "emulator", "session_start", "session_end",
                          "avg_cpu", "min_cpu", "max_cpu",
                          "avg_ram", "min_ram", "max_ram",
                          "avg_cpu_temp", "min_cpu_temp", "max_cpu_temp",
                          "avg_core1", "min_core1", "max_core1",
                          "avg_core2", "min_core2", "max_core2",
                          "avg_core3", "min_core3", "max_core3",
                          "avg_core4", "min_core4", "max_core4",
                          "core_imbalance", "core_killer"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                "game": self.current_game,
                "emulator": self.last_emulator,
                "session_start": datetime.datetime.fromtimestamp(self.session_start_time).strftime("%Y-%m-%d %H:%M:%S"),
                "session_end": datetime.datetime.fromtimestamp(session_end).strftime("%Y-%m-%d %H:%M:%S"),
                "avg_cpu": f"{cpu_stats[0]:.1f}",
                "min_cpu": f"{cpu_stats[1]:.1f}",
                "max_cpu": f"{cpu_stats[2]:.1f}",
                "avg_ram": f"{ram_stats[0]:.1f}",
                "min_ram": f"{ram_stats[1]:.1f}",
                "max_ram": f"{ram_stats[2]:.1f}",
                "avg_cpu_temp": f"{cpu_temp_stats[0]:.1f}",
                "min_cpu_temp": f"{cpu_temp_stats[1]:.1f}",
                "max_cpu_temp": f"{cpu_temp_stats[2]:.1f}",
                "avg_core1": f"{core1_stats[0]:.1f}",
                "min_core1": f"{core1_stats[1]:.1f}",
                "max_core1": f"{core1_stats[2]:.1f}",
                "avg_core2": f"{core2_stats[0]:.1f}",
                "min_core2": f"{core2_stats[1]:.1f}",
                "max_core2": f"{core2_stats[2]:.1f}",
                "avg_core3": f"{core3_stats[0]:.1f}",
                "min_core3": f"{core3_stats[1]:.1f}",
                "max_core3": f"{core3_stats[2]:.1f}",
                "avg_core4": f"{core4_stats[0]:.1f}",
                "min_core4": f"{core4_stats[1]:.1f}",
                "max_core4": f"{core4_stats[2]:.1f}",
                "core_imbalance": f"{core_imbalance:.1f}",
                "core_killer": "Oui" if self.core_killer_alert else "Non"
            })
        logging.info(f"Session de {self.current_game} exportée dans {filename}")

    def sort_summary(self, column, key_func=None):
        if not hasattr(self, "summary_tree"):
            return
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_reverse = False
        self.sort_column = column
        
        items = [(self.summary_tree.set(item, column), item) for item in self.summary_tree.get_children()]
        if key_func:
            items.sort(key=lambda x: key_func(x[0]), reverse=self.sort_reverse)
        else:
            items.sort(reverse=self.sort_reverse)
        
        for index, (_, item) in enumerate(items):
            self.summary_tree.move(item, '', index)

    def update_summary_tab(self):
        try:
            summary_frame = self.tabview.tab("Résumé")
        except Exception:
            return
        if not hasattr(self, "summary_tree"):
            container = ctk.CTkFrame(summary_frame, fg_color="#121212")
            container.pack(fill="both", expand=True, padx=10, pady=10)
            
            sidebar = ctk.CTkFrame(container, fg_color="#1a1a1a", width=150)
            sidebar.pack(side="left", fill="y", padx=(0, 10), pady=0)
            
            self.summary_button = AnimatedCTkButton(
                master=sidebar,
                text="Rafraîchir",
                command=self.show_summary,
                fg_color="#0000FF",
                width=120,
                height=40
            )
            self.summary_button.pack(pady=10)

            self.compare_button = AnimatedCTkButton(
                master=sidebar,
                text="Comparaison",
                command=self.show_comparison,
                fg_color="#0000FF",
                width=120,
                height=40
            )
            self.compare_button.pack(pady=10)

            self.clear_history_button = AnimatedCTkButton(
                master=sidebar,
                text="Effacer Historique",
                command=self.clear_history,
                fg_color="#FF0000",
                width=120,
                height=40
            )
            self.clear_history_button.pack(pady=10)
            
            main_content = ctk.CTkFrame(container, fg_color="#121212")
            main_content.pack(side="right", fill="both", expand=True)
            
            sort_frame = ctk.CTkFrame(main_content, fg_color="#121212")
            sort_frame.pack(fill="x", pady=5)
            
            sort_options = [
                ("Jeu", "game", None),
                ("Emulateur", "emulator", None),
                ("CPU Avg", "CPU (A/M/X)", lambda x: float(x.split('/')[0])),
                ("RAM Avg", "RAM (A/M/X)", lambda x: float(x.split('/')[0])),
                ("CPU Temp", "CPU Temp (A)", lambda x: float(x[:-2])),
                ("Core Imb", "Core Imbalance", lambda x: float(x)),
                ("Tueur", "Core Killer", None)
            ]
            self.sort_column = "game"
            self.sort_reverse = False
            
            for i, (label, col, key_func) in enumerate(sort_options):
                btn = ctk.CTkButton(sort_frame, text=label, fg_color="#0000FF",
                                   command=lambda c=col, kf=key_func: self.sort_summary(c, kf))
                btn.pack(side="left", padx=5, pady=5)
            
            tree_frame = ctk.CTkFrame(main_content, fg_color="#121212")
            tree_frame.pack(fill="both", expand=True)
            
            columns = ("game", "emulator", "session_start", "session_end",
                      "CPU (A/M/X)", "RAM (A/M/X)", "CPU Temp (A)", "Core Imbalance", "Core Killer")
            self.summary_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15, selectmode="extended")
            self.summary_tree.heading("game", text="Jeu")
            self.summary_tree.heading("emulator", text="Emulateur")
            self.summary_tree.heading("session_start", text="Début")
            self.summary_tree.heading("session_end", text="Fin")
            self.summary_tree.heading("CPU (A/M/X)", text="CPU (A/M/X)")
            self.summary_tree.heading("RAM (A/M/X)", text="RAM (A/M/X)")
            self.summary_tree.heading("CPU Temp (A)", text="CPU Temp (A)")
            self.summary_tree.heading("Core Imbalance", text="Core Imbalance")
            self.summary_tree.heading("Core Killer", text="Tueur de Core")
            self.summary_tree.column("game", width=100, anchor="center")
            self.summary_tree.column("emulator", width=100, anchor="center")
            self.summary_tree.column("session_start", width=120, anchor="center")
            self.summary_tree.column("session_end", width=120, anchor="center")
            self.summary_tree.column("CPU (A/M/X)", width=120, anchor="center")
            self.summary_tree.column("RAM (A/M/X)", width=120, anchor="center")
            self.summary_tree.column("CPU Temp (A)", width=100, anchor="center")
            self.summary_tree.column("Core Imbalance", width=100, anchor="center")
            self.summary_tree.column("Core Killer", width=80, anchor="center")
            self.summary_tree.pack(side="left", fill="both", expand=True)
            
            vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.summary_tree.yview)
            vsb.pack(side="right", fill="y")
            self.summary_tree.configure(yscrollcommand=vsb.set)
            
            style = ttk.Style()
            style.theme_use("default")
            style.configure("Treeview", background="#121212", foreground="white",
                            fieldbackground="#121212", rowheight=25)
            style.map("Treeview", background=[("selected", "#2a2a2a")])
            self.summary_tree.tag_configure("killer", foreground="#FF0000", font=("Arial", 12, "bold"))

        for item in self.summary_tree.get_children():
            self.summary_tree.delete(item)
        
        filename = "historique_centralise.csv"
        if os.path.exists(filename):
            with open(filename, mode="r", newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    try:
                        cpu_str = f"{row['avg_cpu']}/{row['min_cpu']}/{row['max_cpu']}"
                        ram_str = f"{row['avg_ram']}/{row['min_ram']}/{row['max_ram']}"
                        cpu_temp_str = f"{row['avg_cpu_temp']}°C"
                        core_imbalance_str = row.get('core_imbalance', "0.0")
                        core_killer_str = "KILLER" if row.get('core_killer', "Non") == "Oui" else "Non"
                        tags = ("killer",) if core_killer_str == "KILLER" else ()
                        self.summary_tree.insert("", "end", values=(
                            row["game"], row["emulator"], row["session_start"], row["session_end"],
                            cpu_str, ram_str, cpu_temp_str, core_imbalance_str, core_killer_str
                        ), tags=tags)
                    except Exception as e:
                        logging.error(f"Erreur lors du chargement d'une ligne du CSV : {e}")
                        continue
        else:
            logging.info("Aucun fichier historique_centralise.csv trouvé.")

    def show_summary(self):
        self.update_summary_tab()

    def show_comparison(self):
        selected = self.summary_tree.selection()
        if len(selected) < 1:
            messagebox.showinfo("Info", "Veuillez sélectionner au moins deux jeux pour comparer.")
            return
        if len(selected) > 20:
            messagebox.showinfo("Info", "Veuillez sélectionner un maximum de 10 jeux pour comparer.")
            return
        selected_items = [self.summary_tree.item(item)["values"] for item in selected]

        comparison_window = ctk.CTkToplevel(self)
        comparison_window.title("Comparaison des Jeux")
        comparison_window.state('zoomed')
        comparison_window.configure(fg_color=self.bg_color)
        comparison_frame = ctk.CTkFrame(comparison_window, fg_color=self.bg_color)
        comparison_frame.pack(fill="both", expand=True, padx=10, pady=10)

        game_names_full = [item[0] for item in selected_items]
        emulators = [item[1] for item in selected_items]
        core_killers = [item[8] == "KILLER" for item in selected_items]
        colors = list(mcolors.TABLEAU_COLORS.values())[:len(game_names_full)]
        if len(colors) < len(game_names_full):
            colors += ["#" + ''.join([random.choice('0123456789ABCDEF') for _ in range(6)]) 
                       for _ in range(len(game_names_full) - len(colors))]
        game_color_map = dict(zip(game_names_full, colors))

        legend_frame = ctk.CTkFrame(comparison_frame, fg_color=self.bg_color)
        legend_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        game_names = []
        for i, name in enumerate(game_names_full):
            words = name.split()[:2]
            short_name = " ".join(words)
            if len(short_name) > 12:
                short_name = short_name[:9] + "..."
            game_names.append(short_name)
        
        game_initials = [''.join(word[0] for word in name.split()[:2]).upper() for name in game_names_full]

        metrics = [
            ("CPU Min (%)", lambda x: float(x[4].split('/')[1]), 0, 1),
            ("CPU Moyen (%)", lambda x: float(x[4].split('/')[0]), 1, 1),
            ("CPU Max (%)", lambda x: float(x[4].split('/')[2]), 2, 1),
            ("RAM Min (%)", lambda x: float(x[5].split('/')[1]), 0, 2),
            ("RAM Moyen (%)", lambda x: float(x[5].split('/')[0]), 1, 2),
            ("RAM Max (%)", lambda x: float(x[5].split('/')[2]), 2, 2),
            ("Temp CPU Moyenne (°C)", lambda x: float(x[6][:-2]), 0, 3),
            ("Core Imbalance (%)", lambda x: float(x[7]), 2, 3),
        ]
        metric_data = {metric[0]: [metric[1](item) for item in selected_items] for metric in metrics}

        scores = {}
        for i, game in enumerate(game_names_full):
            cpu_avg = metric_data["CPU Moyen (%)"][i]
            ram_avg = metric_data["RAM Moyen (%)"][i]
            temp_cpu = metric_data["Temp CPU Moyenne (°C)"][i]
            core_imbalance = metric_data["Core Imbalance (%)"][i]
            score = (cpu_avg + ram_avg + temp_cpu + core_imbalance) / 4
            note = 100 - score
            scores[game] = note

        for i, (game, emu) in enumerate(zip(game_names_full, emulators)):
            killer_text = " KILLER" if core_killers[i] else ""
            label_text = f"{game} ({emu}) - {scores[game]:.1f}"
            row = 0 if i < 5 else 1
            col = i if i < 5 else i - 5
            label = ctk.CTkLabel(legend_frame, text=label_text, text_color=game_color_map[game], font=("Arial", 8))
            label.grid(row=row, column=col, padx=(5, 0), sticky="w")
            if core_killers[i]:
                killer_label = ctk.CTkLabel(legend_frame, text=killer_text, text_color="#FF0000", font=("Arial", 8, "bold"))
                killer_label.grid(row=row, column=col, padx=(0, 5), sticky="e")

        for r in range(2):
            legend_frame.grid_rowconfigure(r, weight=1)
        for c in range(5):
            legend_frame.grid_columnconfigure(c, weight=1)

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_3 = sorted_scores[:3]
        flop_3 = sorted_scores[-3:][::-1]

        for metric_name, _, col, row in metrics:
            fig = Figure(figsize=(3.5, 2.5), dpi=100, facecolor=self.bg_color)
            ax = fig.add_subplot(111, facecolor=self.bg_color)

            bars = ax.bar(range(len(game_names)), metric_data[metric_name], 
                          color=[game_color_map[name] for name in game_names_full], edgecolor="white")
            ax.set_title(metric_name, color=self.fg_color, fontsize=12)
            ax.set_xticks(range(len(game_names)))
            ax.set_xticklabels([])
            ax.tick_params(axis="y", colors=self.fg_color)

            max_val = max(metric_data[metric_name]) * 1.2 if max(metric_data[metric_name]) > 0 else 100
            threshold = max_val * 0.3
            min_absolute = 10

            for i, (bar, full_name, short_name, initials) in enumerate(zip(bars, game_names_full, game_names, game_initials)):
                height = bar.get_height()
                if height > threshold:
                    ax.text(bar.get_x() + bar.get_width() / 2, height / 2, short_name, 
                            ha="center", va="center", rotation=90, color="white", fontsize=8)
                elif height > min_absolute:
                    ax.text(bar.get_x() + bar.get_width() / 2, height / 2, initials, 
                            ha="center", va="center", rotation=90, color="white", fontsize=6)

            ax.set_ylim(0, max_val)
            for j, val in enumerate(metric_data[metric_name]):
                ax.text(j, val + max_val * 0.05, f"{val:.1f}", ha="center", va="bottom", color=self.fg_color, fontsize=8)

            canvas = FigureCanvasTkAgg(fig, master=comparison_frame)
            canvas.draw()
            canvas.get_tk_widget().grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

        fig_ranking = Figure(figsize=(3.5, 2.5), dpi=100, facecolor=self.bg_color)
        ax_ranking = fig_ranking.add_subplot(111, facecolor=self.bg_color)
        ax_ranking.axis('off')

        def truncate_name(game, emu, max_len=50):
            full_text = f"{game} ({emu})"
            if len(full_text) > max_len:
                return full_text[:max_len-3] + "..."
            return full_text

        y_pos = 1.0
        ax_ranking.text(0.95, y_pos, "Score/100", ha="right", va="top", color=self.fg_color, fontsize=7)
        y_pos -= 0.10
        ax_ranking.text(0.05, y_pos, "Top Score:", ha="left", va="top", color=self.fg_color, fontsize=7)
        y_pos -= 0.10
        for i, (game, note) in enumerate(top_3, 1):
            emu = emulators[game_names_full.index(game)]
            is_killer = core_killers[game_names_full.index(game)]
            truncated_name = truncate_name(game, emu)
            ax_ranking.text(0.05, y_pos, f"{i}. ", ha="left", va="top", color=self.fg_color, fontsize=7)
            ax_ranking.text(0.10, y_pos, truncated_name, ha="left", va="top", color=game_color_map[game], fontsize=7)
            ax_ranking.text(0.85, y_pos, f"- {note:.1f}", ha="right", va="top", color=self.fg_color, fontsize=7)
            if is_killer:
                ax_ranking.text(0.95, y_pos, "KILLER", ha="right", va="top", color="#FF0000", fontsize=7, fontweight="bold")
            y_pos -= 0.10
        ax_ranking.text(0.05, y_pos, "Flop Score:", ha="left", va="top", color=self.fg_color, fontsize=7)
        y_pos -= 0.10
        for i, (game, note) in enumerate(flop_3, 1):
            emu = emulators[game_names_full.index(game)]
            is_killer = core_killers[game_names_full.index(game)]
            truncated_name = truncate_name(game, emu)
            ax_ranking.text(0.05, y_pos, f"{i}. ", ha="left", va="top", color=self.fg_color, fontsize=7)
            ax_ranking.text(0.10, y_pos, truncated_name, ha="left", va="top", color=game_color_map[game], fontsize=7)
            ax_ranking.text(0.85, y_pos, f"- {note:.1f}", ha="right", va="top", color=self.fg_color, fontsize=7)
            if is_killer:
                ax_ranking.text(0.95, y_pos, "KILLER", ha="right", va="top", color="#FF0000", fontsize=7, fontweight="bold")
            y_pos -= 0.10

        canvas_ranking = FigureCanvasTkAgg(fig_ranking, master=comparison_frame)
        canvas_ranking.draw()
        canvas_ranking.get_tk_widget().grid(row=3, column=1, padx=5, pady=5, sticky="nsew")

        for r in range(4):
            comparison_frame.grid_rowconfigure(r, weight=1)
        for c in range(3):
            comparison_frame.grid_columnconfigure(c, weight=1)

        comparison_window.grab_set()

def main():
    port = 22
    username = "root"
    password = "recalboxroot"
    hostname = get_recalbox_ip()
    if not hostname:
        tk.messagebox.showerror("Erreur", "Impossible de trouver Recalbox sur le réseau.")
        return
    ssh_manager = SSHManager(hostname, port, username, password)
    if not ssh_manager.client:
        tk.messagebox.showerror("Erreur", "Connexion SSH échouée.")
        return
    app = App(ssh_manager)
    app.mainloop()
    ssh_manager.close()

if __name__ == "__main__":
    main()