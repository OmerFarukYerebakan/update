import tkinter as tk
import serial
import serial.tools.list_ports
import threading
import time
import numpy as np
import pyautogui
import win32api
from ultralytics import YOLO
import keyboard
import cv2

# Arduino ismi için başlangıçta giriş kutusu
def get_arduino_name():
    input_window = tk.Tk()
    input_window.title("Arduino Setup")
    input_window.geometry("400x150")
    input_window.configure(bg="#f0f0f0")
    input_window.resizable(False, False)
    
    # Pencereyi ortala
    input_window.eval('tk::PlaceWindow . center')
    
    tk.Label(input_window, text="Enter Arduino Name:", 
             font=("Arial", 12, "bold"), bg="#f0f0f0").pack(pady=20)
    
    name_var = tk.StringVar(value="Arduino Leonardo")
    name_entry = tk.Entry(input_window, textvariable=name_var, 
                         font=("Arial", 11), width=30)
    name_entry.pack(pady=10)
    name_entry.select_range(0, tk.END)
    name_entry.focus()
    
    result = []
    
    def save_and_close():
        result.append(name_var.get().strip())
        input_window.destroy()
    
    tk.Button(input_window, text="OK", command=save_and_close,
              bg="#2196F3", fg="white", font=("Arial", 10, "bold"),
              width=10).pack(pady=10)
    
    input_window.bind('<Return>', lambda event: save_and_close())
    input_window.mainloop()
    
    return result[0] if result else "Arduino Leonardo"

# Arduino ismini al
circut_name = get_arduino_name()

# YOLO ve mouse kontrol ayarları
MODEL_W, MODEL_H = 640, 384
SCREEN_W, SCREEN_H = 1920, 1080
CONF_THRESHOLD = 0.35
MAX_DURATION = 0.1
STEP_DT = 0.005
MAX_SPEED = 18

# Global değişkenler
arduino = None
running = False
paused = False
model = None

def find_arduino():
    global arduino
    while arduino is None:
        ports = serial.tools.list_ports.comports()
        for p in ports:
            if circut_name in p.description or "ATmega32U4" in p.description or "USB Serial Device" in p.description:
                try:
                    arduino = serial.Serial(p.device, 115200, timeout=1)
                    time.sleep(2)
                    status.set(f"✅ Arduino Connected: {p.device}")
                    show_control_ui()
                    return
                except Exception as e:
                    print(f"Connection Error: {e}")
        time.sleep(1)
    
    # Arduino bulunamazsa manuel port seçimi
    status.set("❌ Cannot Find Arduino")
    show_manual_port_ui()

def show_manual_port_ui():
    manual_frame = tk.Frame(root, bg="#f0f0f0")
    manual_frame.pack(pady=10)
    
    tk.Label(manual_frame, text="Select Port:", 
             font=("Arial", 10), bg="#f0f0f0").pack()
    
    port_var = tk.StringVar(value="COM9")
    port_entry = tk.Entry(manual_frame, textvariable=port_var, 
                         font=("Arial", 10), width=10)
    port_entry.pack(pady=5)
    
    def connect_manual():
        global arduino
        try:
            port = port_var.get().strip()
            arduino = serial.Serial(port, 115200, timeout=1)
            time.sleep(2)
            manual_frame.pack_forget()
            status.set(f"✅ Manuel Connection: {port}")
            show_control_ui()
        except Exception as e:
            status.set(f"❌ Connection Error: {e}")
    
    tk.Button(manual_frame, text="Connect", command=connect_manual,
              bg="#2196F3", fg="white").pack()

def show_control_ui():
    status.set("System Ready - Loading YOLO...")
    load_model_btn.pack(pady=5)
    status_label.pack(pady=10)
    toggle_btn.pack(pady=5)
    pause_btn.pack(pady=5)
    
    # Model otomatik yüklensin
    load_yolo_model()

def load_yolo_model():
    global model
    try:
        status_label.config(text="🔄 Model Loading...")
        model = YOLO("yolov8n-pose.pt")
        status_label.config(text="✅ Model Loaded Successfully!")
        load_model_btn.pack_forget()
        toggle_btn.config(state=tk.NORMAL)
        pause_btn.config(state=tk.NORMAL)
    except Exception as e:
        status_label.config(text=f"❌ Model Loading Error: {e}")

def toggle_system():
    global running
    running = not running
    if running:
        try:
            arduino.write(b"START\n")
            toggle_btn.config(text="Stop System", bg="red", fg="white")
            status_label.config(text="▶️ System Started")
            # Ayrı bir thread'de hedef takibi başlat
            threading.Thread(target=target_tracking_loop, daemon=True).start()
        except Exception as e:
            status_label.config(text=f"❌ Critical Error: {e}")
            running = False
    else:
        try:
            arduino.write(b"STOP\n")
        except:
            pass
        toggle_btn.config(text="Sistemi Başlat", bg="green", fg="white")
        status_label.config(text="⏸ System Stopped")

def toggle_pause():
    global paused
    paused = not paused
    if paused:
        pause_btn.config(text="Resume", bg="orange")
        status_label.config(text="⏸ Paused")
    else:
        pause_btn.config(text="Pause", bg="yellow")
        status_label.config(text="▶️ Working...")

def target_tracking_loop():
    global running, paused
    
    while running:
        # Duraklatma kontrolü
        if keyboard.is_pressed('t'):
            paused = not paused
            status_label.config(text="⏸ Paused" if paused else "▶️ Resumed")
            time.sleep(0.5)
            continue
        
        if paused:
            time.sleep(0.05)
            continue
        
        if model is None:
            time.sleep(0.1)
            continue
        
        try:
            # Ekran görüntüsü al
            screenshot = pyautogui.screenshot(region=(0, 0, SCREEN_W, SCREEN_H))
            img = np.array(screenshot)
            img_small = cv2.resize(img, (MODEL_W, MODEL_H))
            
            # YOLO ile poz tespiti
            results = model(img_small, verbose=False)[0]
            
            if results.keypoints is None or len(results.keypoints) == 0:
                continue
            
            mouse_x, mouse_y = win32api.GetCursorPos()
            scale_x = SCREEN_W / MODEL_W
            scale_y = SCREEN_H / MODEL_H
            
            min_dist = float('inf')
            target_pos = None
            
            # Her kişi için burun noktasını bul
            for person_kps in results.keypoints:
                nose = person_kps.data[0]
                if hasattr(nose, 'cpu'):
                    nose = nose.cpu().numpy()
                if isinstance(nose, np.ndarray) and nose.ndim > 1:
                    nose = nose[0]
                if len(nose) < 3:
                    continue
                if nose[2] < CONF_THRESHOLD:
                    continue
                
                head_x = int(nose[0] * scale_x)
                head_y = int(nose[1] * scale_y) - 15
                dist = np.hypot(mouse_x - head_x, mouse_y - head_y)
                
                if dist < min_dist:
                    min_dist = dist
                    target_pos = (head_x, head_y)
            
            if target_pos is None:
                continue
            
            # Fareyi hedefe yönlendir
            start_time = time.perf_counter()
            while True:
                mouse_x, mouse_y = win32api.GetCursorPos()
                dx = target_pos[0] - mouse_x
                dy = target_pos[1] - mouse_y
                distance = np.hypot(dx, dy)
                elapsed = time.perf_counter() - start_time
                remaining = MAX_DURATION - elapsed
                
                if distance < 3 or remaining <= 0:
                    break
                
                required_speed = distance / max(1, (remaining / STEP_DT))
                speed = min(required_speed, MAX_SPEED)
                dir_x = dx / distance
                dir_y = dy / distance
                
                move_x = int(dir_x * speed)
                move_y = int(dir_y * speed)
                
                # Küçük rastgelelik ekle
                move_x += np.random.randint(-1, 2)
                move_y += np.random.randint(-1, 2)
                
                # Arduino'ya hareket komutu gönder
                if arduino:
                    arduino.write(f"{move_x},{move_y}\n".encode())
                
                time.sleep(STEP_DT)
            
            # Hedefe ulaşıldığında tıklama yap
            if distance < 4 and arduino:
                arduino.write(b"CLICK\n")
                print("💥 Shooted Target!")
            
            time.sleep(0.005)
            
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(0.1)

# GUI oluşturma
root = tk.Tk()
root.title("ArduZero")
root.geometry("400x350")
root.configure(bg="#f0f0f0")

# Başlık
title_label = tk.Label(root, text="🎯 Welcome To ArduZero", 
                      font=("Arial", 16, "bold"), bg="#f0f0f0", fg="#333")
title_label.pack(pady=10)

# Durum etiketi
status = tk.StringVar(value="Looking For Arduino...")
status_label_main = tk.Label(root, textvariable=status, 
                           font=("Arial", 11), bg="#f0f0f0", fg="#555")
status_label_main.pack(pady=10)

# Kontrol UI elemanları
status_label = tk.Label(root, text="Preparing...", 
                       font=("Arial", 10), bg="#f0f0f0", fg="#333")

load_model_btn = tk.Button(root, text="Download YOLO Model", 
                          command=load_yolo_model, bg="#2196F3", fg="white",
                          font=("Arial", 10, "bold"), width=20, height=1)

toggle_btn = tk.Button(root, text="Start System", command=toggle_system,
                      bg="green", fg="white", font=("Arial", 10, "bold"),
                      width=20, height=1, state=tk.DISABLED)

pause_btn = tk.Button(root, text="Pause", command=toggle_pause,
                     bg="yellow", fg="black", font=("Arial", 10, "bold"),
                     width=20, height=1, state=tk.DISABLED)

# Klavye kısayolları için bilgi
shortcut_label = tk.Label(root, text="Press 'T' to Toggle Pause/Resume", 
                         font=("Arial", 8), bg="#f0f0f0", fg="#777")
shortcut_label.pack(side=tk.BOTTOM, pady=5)

# Arduino bağlantısını başlat
threading.Thread(target=find_arduino, daemon=True).start()

# Pencereyi ortala
root.eval('tk::PlaceWindow . center')

root.mainloop()
