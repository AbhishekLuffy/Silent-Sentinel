import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import pyaudio
import wave
import os
import datetime
import speech_recognition as sr

# Import alert and utility functions
from sms_alert import send_sms_alert
from email_alert import send_email_alert
from audio_evidence import record_evidence_audio
from location_utils import get_location_link

# --- Constants ---
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
RECORD_SECONDS = 5
OUTPUT_DIR = "audio_clips"

os.makedirs(OUTPUT_DIR, exist_ok=True)
stop_event = threading.Event()

# --- Main Monitoring Logic ---
def monitoring_loop(secret_phrase, app_instance):
    """
    The main logic for listening, transcribing, and alerting.
    This function runs in a separate thread and communicates with the GUI
    through thread-safe callbacks in the app_instance.
    """
    audio = pyaudio.PyAudio()
    try:
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    except OSError as e:
        app_instance.update_status(f"🛑 Error: Mic not found", "red")
        messagebox.showerror("Microphone Error", f"Could not open microphone: {e}")
        return

    while not stop_event.is_set():
        app_instance.update_status("🟢 Listening...", "green")
        frames = [stream.read(CHUNK, exception_on_overflow=False) for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)) if not stop_event.is_set()]

        if stop_event.is_set(): break

        # Save audio and transcribe
        filename = os.path.join(OUTPUT_DIR, f"clip_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(audio.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))

        r = sr.Recognizer()
        with sr.AudioFile(filename) as source:
            try:
                text = r.recognize_google(r.record(source)).lower()
                app_instance.update_results(f'"{text}"', None)
                if secret_phrase in text:
                    app_instance.update_status("✅ Triggered! Alerts Sent", "orange")
                    messagebox.showinfo("Alert Triggered", "Secret phrase detected! Sending alerts.")
                    location_link = get_location_link()
                    app_instance.update_results(f'"{text}"', location_link)
                    # Trigger alerts in a separate thread to avoid blocking
                    threading.Thread(target=trigger_alerts, args=(location_link,)).start()
                    time.sleep(3) # Show triggered status for a moment
            except (sr.UnknownValueError, sr.RequestError) as e:
                app_instance.update_results(f"[Audio not understood]", None)
                print(f"Transcription Error: {e}")

    stream.stop_stream()
    stream.close()
    audio.terminate()

def trigger_alerts(location_link):
    """Function to send all alerts."""
    send_sms_alert(location_link)
    send_email_alert(location_link)
    record_evidence_audio()

# --- GUI Application ---
class SentinelApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Silent Sentinel")
        self.root.geometry("450x350")
        self.root.resizable(False, False)
        
        # --- Style Configuration for Dark Theme ---
        BG_COLOR = "#2E2E2E"
        FG_COLOR = "#EAEAEA"
        HEADER_COLOR = "#FFFFFF"
        BUTTON_BG = "#3E3E3E"
        BUTTON_FG = "#EAEAEA"
        BUTTON_ACTIVE_BG = "#4E4E4E"
        ENTRY_BG = "#3C3C3C"
        LINK_COLOR = "#4DA6FF"

        self.root.configure(bg=BG_COLOR)
        style = ttk.Style(self.root)
        style.theme_use('clam')

        # Configure all widgets for the dark theme
        style.configure(".", background=BG_COLOR, foreground=FG_COLOR, font=("Helvetica", 11), borderwidth=0)
        style.configure("TFrame", background=BG_COLOR)
        style.configure("TLabel", background=BG_COLOR, foreground=FG_COLOR, font=("Helvetica", 12))
        style.configure("Header.TLabel", background=BG_COLOR, foreground=HEADER_COLOR, font=("Helvetica", 16, "bold"))
        
        # Configure Entry widget
        style.configure("TEntry", fieldbackground=ENTRY_BG, foreground=FG_COLOR, insertcolor=FG_COLOR, borderwidth=1, padding=5)
        style.map("TEntry", bordercolor=[('focus', LINK_COLOR)])

        # Configure buttons
        style.configure("TButton", background=BUTTON_BG, foreground=BUTTON_FG, font=("Helvetica", 11), padding=5, borderwidth=0)
        style.map("TButton",
                  background=[('active', BUTTON_ACTIVE_BG), ('disabled', '#3A3A3A')],
                  foreground=[('disabled', '#7A7A7A')])
        
        # --- Main Frame ---
        main_frame = ttk.Frame(self.root, padding="15 15 15 15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Header ---
        ttk.Label(main_frame, text="🔐 Silent Sentinel", style="Header.TLabel").pack(pady=(0, 10))
        ttk.Label(main_frame, text="Emergency Alert System", font=("Helvetica", 10)).pack(pady=(0, 20))

        # --- Secret Phrase Input ---
        phrase_frame = ttk.Frame(main_frame)
        phrase_frame.pack(fill=tk.X, pady=5)
        ttk.Label(phrase_frame, text="Secret Phrase:").pack(side=tk.LEFT)
        self.secret_phrase_entry = ttk.Entry(phrase_frame, font=("Helvetica", 11))
        self.secret_phrase_entry.insert(0, "help me lotus")
        self.secret_phrase_entry.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        # --- Controls ---
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(pady=20)
        self.start_button = ttk.Button(control_frame, text="🎙️ Start Monitoring", command=self.start_monitoring)
        self.start_button.pack(side=tk.LEFT, padx=10)
        self.stop_button = ttk.Button(control_frame, text="⛔ Stop Monitoring", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=10)

        # --- Status & Results ---
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=10)
        self.status_label = ttk.Label(status_frame, text="🛑 Monitoring Stopped", font=("Helvetica", 12, "bold"), foreground="red")
        self.status_label.pack()
        
        self.transcription_label = ttk.Label(status_frame, text="Last Transcription: --", wraplength=400)
        self.transcription_label.pack(pady=5)
        
        self.location_label = ttk.Label(status_frame, text="Location Link: --", foreground=LINK_COLOR, cursor="hand2")
        self.location_label.pack()

    def update_status(self, message, color):
        self.root.after(0, lambda: self.status_label.config(text=message, foreground=color))

    def update_results(self, transcription, location_link):
        self.root.after(0, lambda: self.transcription_label.config(text=f"Last Transcription: {transcription}"))
        if location_link:
            self.root.after(0, lambda: self.location_label.config(text=f"Location Link: {location_link}"))

    def start_monitoring(self):
        secret_phrase = self.secret_phrase_entry.get().strip().lower()
        if not secret_phrase:
            messagebox.showwarning("Warning", "Secret phrase cannot be empty.")
            return

        stop_event.clear()
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.secret_phrase_entry.config(state=tk.DISABLED)
        messagebox.showinfo("Monitoring Started", "Silent Sentinel is now listening.")
        
        self.monitoring_thread = threading.Thread(target=monitoring_loop, args=(secret_phrase, self))
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()

    def stop_monitoring(self):
        stop_event.set()
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.secret_phrase_entry.config(state=tk.NORMAL)
        self.update_status("🛑 Monitoring Stopped", "red")
        self.update_results("--", "--")

if __name__ == "__main__":
    root = tk.Tk()
    app = SentinelApp(root)
    root.mainloop() 