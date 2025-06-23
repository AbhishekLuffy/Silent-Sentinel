import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.tableview import Tableview
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.icons import Icon
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk, ImageDraw
import threading
import time
import pyaudio
import wave
import os
import datetime
import speech_recognition as sr
from sms_alert import send_sms_alert
from email_alert import send_email_alert
from audio_evidence import record_evidence_audio
from location_utils import get_location_link
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from database_utils import (
    init_database, insert_audio_log, get_all_logs, register_admin, verify_admin,
    register_pending_admin, get_pending_admins, accept_pending_admin, delete_pending_admin
)
from flask import Flask, Response as FlaskResponse
import shutil
import webbrowser
import json

# --- Flask App for TwiML Voice Alert ---
flask_app = Flask(__name__)

@flask_app.route('/voice_alert', methods=['GET', 'POST'])
def voice_alert():
    response = VoiceResponse()
    response.say(
        "This is an emergency alert from Silent Sentinel. Help is needed at location: latitude 13.3223, longitude 75.774. "
        "An SMS and Email have already been sent to your mobile with full details. Please check them and respond immediately.",
        voice='alice', language='en-US')
    return Response(str(response), mimetype='text/xml')

# --- Flask route to serve geolocation page ---
@flask_app.route('/get_precise_location')
def get_precise_location_page():
    html = '''
    <!DOCTYPE html>
    <html><head><title>Get Precise Location</title></head>
    <body style="background:#222;color:#fff;font-family:sans-serif;text-align:center;padding-top:50px;">
    <h2>Allow Location Access</h2>
    <p>Click the button below and allow location access in your browser.</p>
    <button onclick="getLocation()" style="font-size:1.2em;padding:10px 30px;border-radius:8px;background:#007bff;color:#fff;border:none;">Get Location</button>
    <p id="status"></p>
    <script>
    function getLocation() {
      document.getElementById('status').innerText = 'Requesting location...';
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function(pos) {
          document.getElementById('status').innerText = 'Location received! Sending to app...';
          fetch('/submit_location', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({lat: pos.coords.latitude, lng: pos.coords.longitude})
          }).then(() => {
            document.getElementById('status').innerText = 'Location sent! You can close this tab.';
          });
        }, function(err) {
          document.getElementById('status').innerText = 'Error: ' + err.message;
        });
      } else {
        document.getElementById('status').innerText = 'Geolocation is not supported.';
      }
    }
    </script>
    </body></html>
    '''
    return FlaskResponse(html, mimetype='text/html')

# --- Flask route to receive coordinates ---
from flask import request

precise_location = {'lat': None, 'lng': None}

@flask_app.route('/submit_location', methods=['POST'])
def submit_location():
    data = request.get_json()
    precise_location['lat'] = data.get('lat')
    precise_location['lng'] = data.get('lng')
    return 'OK'

# --- Constants ---
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
RECORD_SECONDS = 5
OUTPUT_DIR = "audio_clips"

os.makedirs(OUTPUT_DIR, exist_ok=True)
stop_event = threading.Event()

# --- Twilio Phone Call Function ---
def make_call():
    """
    Makes a phone call using Twilio to play a custom emergency message when the secret phrase is detected.
    Uses the local Flask /voice_alert endpoint as the TwiML URL.
    """
    load_dotenv()
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_phone = os.getenv("TWILIO_PHONE") or os.getenv("TWILIO_PHONE_NUMBER")
    recipient_phone = os.getenv("RECIPIENT_PHONE_NUMBER")

    print(f"[DEBUG] TWILIO_ACCOUNT_SID: {account_sid}")
    print(f"[DEBUG] TWILIO_AUTH_TOKEN: {auth_token}")
    print(f"[DEBUG] TWILIO_PHONE: {twilio_phone}")
    print(f"[DEBUG] RECIPIENT_PHONE_NUMBER: {recipient_phone}")

    # For local testing, use your local server or ngrok URL
    # Example: url = "http://localhost:5000/voice_alert" or your ngrok URL
    url = os.getenv("VOICE_ALERT_URL", "http://localhost:5000/voice_alert")
    print(f"[DEBUG] Using TwiML URL: {url}")

    # Check if all required environment variables are set
    if not all([account_sid, auth_token, twilio_phone, recipient_phone]):
        print("❌ Error: Twilio environment variables not set. Cannot make phone call.")
        return

    try:
        client = Client(account_sid, auth_token)
        call = client.calls.create(
            url=url,
            from_=twilio_phone,
            to=recipient_phone
        )
        print(f"✅ Phone call initiated successfully! Call SID: {call.sid}")
        return call.sid
    except Exception as e:
        print(f"❌ Failed to make phone call: {e}")
        return None

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
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(OUTPUT_DIR, f"clip_{timestamp}.wav")
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(audio.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))

        print(f"Saved audio: {filename}")

        # Transcribe the audio and check for the secret phrase
        transcription = None
        r = sr.Recognizer()
        with sr.AudioFile(filename) as source:
            try:
                text = r.recognize_google(r.record(source)).lower()
                transcription = text
                app_instance.update_results(f'"{text}"', None)
                if secret_phrase in text:
                    app_instance.update_status("✅ Triggered! Waiting to send alerts...", "orange")
                    location_link = get_location_link()
                    app_instance.update_results(f'"{text}"', location_link)
                    
                    # Save to database
                    insert_audio_log(filename, location_link, transcription)
                    
                    # Show disable alert dialog and trigger alerts after 10 seconds if not cancelled
                    def on_timeout():
                        if not app_instance.alert_cancelled:
                            threading.Thread(target=trigger_alerts, args=(location_link,)).start()
                            app_instance.update_status("✅ Alerts Sent!", "orange")
                    app_instance.root.after(0, app_instance.show_disable_alert_dialog, on_timeout)
                    time.sleep(13)  # Wait for dialog and alerts to finish before next listen
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
    make_call()  # Make the emergency phone call
    record_evidence_audio()

# --- GUI Application ---
class SentinelApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Silent Sentinel")
        self.root.geometry("900x650")
        self.root.resizable(False, False)
        self.is_admin_logged_in = False
        self.admin_username = None
        self.is_main_admin_logged_in = False
        
        # Use a clean, professional dark theme
        style = tb.Style("superhero")
        self.root.configure(bg=style.colors.bg)

        # --- Simple Elegant Header ---
        header_frame = tb.Frame(self.root, bootstyle="dark")
        header_frame.pack(fill=X, pady=(0, 10))
        tb.Label(header_frame, text="Silent Sentinel", font=("Segoe UI", 28, "bold"), bootstyle="primary inverse").pack(side=LEFT, padx=(30, 20), pady=20)
        tb.Label(header_frame, text="Emergency Alert System", font=("Segoe UI", 14), bootstyle="secondary inverse").pack(side=LEFT, pady=20)

        # --- Notebook (Tabs) ---
        self.notebook = tb.Notebook(self.root, bootstyle="dark")
        self.notebook.pack(fill=BOTH, expand=True, padx=20, pady=10)

        # --- Home Tab ---
        self.home_frame = tb.Frame(self.notebook)
        self.notebook.add(self.home_frame, text="🏠 Home")
        self.build_home_tab()

        # --- Admin Tab ---
        self.admin_frame = tb.Frame(self.notebook)
        self.notebook.add(self.admin_frame, text="🔑 Admin")
        self.build_admin_tab()

        # --- Main Admin Tab ---
        self.main_admin_frame = tb.Frame(self.notebook)
        self.notebook.add(self.main_admin_frame, text="👑 Main Admin")
        self.build_main_admin_tab()

        # --- Database Tab (hidden until admin login) ---
        self.db_frame = tb.Frame(self.notebook)
        # self.notebook.add(self.db_frame, text="Database")  # Only add after login

    def build_home_tab(self):
        frame = self.home_frame
        for widget in frame.winfo_children(): widget.destroy()
        card = tb.Frame(frame, bootstyle="dark", padding=30)
        card.pack(pady=30, padx=30, fill=BOTH, expand=True)
        tb.Label(card, text="🔐 Silent Sentinel", font=("Segoe UI", 22, "bold"), bootstyle="primary inverse").pack(pady=(10, 10))
        tb.Label(card, text="Emergency Alert System", font=("Segoe UI", 13), bootstyle="secondary inverse").pack(pady=(0, 30))
        # Secret Phrase Input
        phrase_frame = tb.Frame(card)
        phrase_frame.pack(fill=X, pady=10, padx=20)
        tb.Label(phrase_frame, text="Secret Phrase:", font=("Segoe UI", 13)).pack(side=LEFT)
        self.secret_phrase_entry = tb.Entry(phrase_frame, font=("Segoe UI", 13), width=30)
        self.secret_phrase_entry.insert(0, "help me lotus")
        self.secret_phrase_entry.pack(side=LEFT, fill=X, expand=True, padx=10)
        # Precise Location Button
        loc_btn = tb.Button(card, text="📍 Get Precise Location", bootstyle="info-outline", width=24, command=self.open_precise_location_page)
        loc_btn.pack(pady=10)
        self.precise_location_label = tb.Label(card, text="Precise Location: Not set", font=("Segoe UI", 11), bootstyle="info")
        self.precise_location_label.pack(pady=(0, 10))
        # Controls
        control_frame = tb.Frame(card)
        control_frame.pack(pady=30)
        self.start_button = tb.Button(control_frame, text="🎙️ Start Monitoring", bootstyle="info", width=20, command=self.start_monitoring)
        self.start_button.pack(side=LEFT, padx=10)
        self.stop_button = tb.Button(control_frame, text="⛔ Stop Monitoring", bootstyle="secondary", width=20, command=self.stop_monitoring, state=DISABLED)
        self.stop_button.pack(side=LEFT, padx=10)
        # Status & Results
        status_frame = tb.Frame(card)
        status_frame.pack(fill=X, pady=20, padx=20)
        self.status_label = tb.Label(status_frame, text="🛑 Monitoring Stopped", font=("Segoe UI", 15, "bold"), bootstyle="danger")
        self.status_label.pack(anchor=W)
        self.transcription_label = tb.Label(status_frame, text="Last Transcription: --", font=("Segoe UI", 11), wraplength=700)
        self.transcription_label.pack(anchor=W, pady=5)
        self.location_label = tb.Label(status_frame, text="Location Link: --", font=("Segoe UI", 11, "underline"), bootstyle="info", cursor="hand2")
        self.location_label.pack(anchor=W)
        self.alert_cancelled = False

    def build_admin_tab(self):
        frame = self.admin_frame
        for widget in frame.winfo_children(): widget.destroy()
        self.admin_tabs = tb.Notebook(frame, bootstyle="dark")
        self.admin_tabs.pack(fill=BOTH, expand=True, pady=30, padx=30)
        # Register Tab
        reg_tab = tb.Frame(self.admin_tabs)
        self.admin_tabs.add(reg_tab, text="📝 Register")
        tb.Label(reg_tab, text="Register as Admin", font=("Helvetica", 18, "bold"), bootstyle="primary").pack(pady=20)
        # Username row
        reg_user_row = tb.Frame(reg_tab)
        reg_user_row.pack(anchor=W, padx=10, pady=5)
        tb.Label(reg_user_row, text="Username:", font=("Helvetica", 14)).pack(side=LEFT)
        self.reg_username = tb.Entry(reg_user_row, font=("Helvetica", 14), width=30)
        self.reg_username.pack(side=LEFT, padx=10)
        # Password row
        reg_pass_row = tb.Frame(reg_tab)
        reg_pass_row.pack(anchor=W, padx=10, pady=5)
        tb.Label(reg_pass_row, text="Password:", font=("Helvetica", 14)).pack(side=LEFT)
        self.reg_password = tb.Entry(reg_pass_row, show="*", font=("Helvetica", 14), width=30)
        self.reg_password.pack(side=LEFT, padx=10)
        tb.Button(reg_tab, text="Register", bootstyle="success", width=20, command=self.handle_register).pack(pady=20)
        # Login Tab
        login_tab = tb.Frame(self.admin_tabs)
        self.admin_tabs.add(login_tab, text="🔑 Login")
        tb.Label(login_tab, text="Admin Login", font=("Helvetica", 18, "bold"), bootstyle="primary").pack(pady=20)
        # Username row
        login_user_row = tb.Frame(login_tab)
        login_user_row.pack(anchor=W, padx=10, pady=5)
        tb.Label(login_user_row, text="Username:", font=("Helvetica", 14)).pack(side=LEFT)
        self.login_username = tb.Entry(login_user_row, font=("Helvetica", 14), width=30)
        self.login_username.pack(side=LEFT, padx=10)
        # Password row
        login_pass_row = tb.Frame(login_tab)
        login_pass_row.pack(anchor=W, padx=10, pady=5)
        tb.Label(login_pass_row, text="Password:", font=("Helvetica", 14)).pack(side=LEFT)
        self.login_password = tb.Entry(login_pass_row, show="*", font=("Helvetica", 14), width=30)
        self.login_password.pack(side=LEFT, padx=10)
        tb.Button(login_tab, text="Login", bootstyle="info", width=20, command=self.handle_login).pack(pady=20)
        # Status
        self.admin_status = tb.Label(frame, text="", font=("Helvetica", 14), bootstyle="warning")
        self.admin_status.pack(pady=10)

    def handle_register(self):
        username = self.reg_username.get().strip()
        password = self.reg_password.get().strip()
        if not username or not password:
            self.admin_status.config(text="Username and password required.")
            return
        if register_pending_admin(username, password):
            self.admin_status.config(text="Registration submitted! Awaiting main admin approval.", foreground="green")
        else:
            self.admin_status.config(text="Registration failed. Username may already exist.", foreground="red")

    def handle_login(self):
        username = self.login_username.get().strip()
        password = self.login_password.get().strip()
        if not username or not password:
            self.admin_status.config(text="Username and password required.")
            return
        if verify_admin(username, password):
            self.is_admin_logged_in = True
            self.admin_username = username
            self.admin_status.config(text=f"Welcome, {username}!", foreground="green")
            self.show_database_tab()
        else:
            self.admin_status.config(text="Login failed. Check credentials or wait for approval.", foreground="red")

    def show_database_tab(self):
        # Add the database tab if not already present
        if self.db_frame not in self.notebook.tabs():
            self.notebook.add(self.db_frame, text="Database")
        self.build_db_tab()
        self.notebook.select(self.db_frame)

    def build_db_tab(self):
        frame = self.db_frame
        for widget in frame.winfo_children(): widget.destroy()
        tb.Label(frame, text="Audio Evidence Database", font=("Segoe UI", 18, "bold"), bootstyle="primary inverse").pack(pady=(20, 10))
        # Table frame for padding and scrollbars
        table_frame = tb.Frame(frame)
        table_frame.pack(fill=BOTH, expand=True, padx=30, pady=10)
        columns = ("ID", "Filename", "Timestamp", "Location URL", "Transcription")
        self.db_tree = tb.Treeview(table_frame, columns=columns, show="headings", height=14, bootstyle="dark")
        # Scrollbars
        vsb = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.db_tree.yview)
        hsb = tb.Scrollbar(table_frame, orient=HORIZONTAL, command=self.db_tree.xview)
        self.db_tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        self.db_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        # Set column headings and widths
        col_widths = [60, 220, 160, 220, 220]
        for i, col in enumerate(columns):
            self.db_tree.heading(col, text=col, anchor=W)
            self.db_tree.column(col, width=col_widths[i], anchor=W, stretch=True)
        # Insert data with striped rows
        logs = get_all_logs()
        for idx, row in enumerate(logs):
            tag = 'evenrow' if idx % 2 == 0 else 'oddrow'
            self.db_tree.insert("", tk.END, values=row, tags=(tag,))
        self.db_tree.tag_configure('evenrow', background="#23272b")
        self.db_tree.tag_configure('oddrow', background="#2c3035")
        # Download and Delete buttons
        btn_frame = tb.Frame(frame)
        btn_frame.pack(pady=10)
        tb.Button(btn_frame, text="⬇️ Download", bootstyle="info-outline", width=16, command=self.download_selected_evidence).pack(side=LEFT, padx=10)
        tb.Button(btn_frame, text="🗑️ Delete", bootstyle="danger-outline", width=16, command=self.delete_selected_evidence).pack(side=LEFT, padx=10)
        tb.Button(btn_frame, text="🔄 Refresh", bootstyle="secondary-outline", width=16, command=self.build_db_tab).pack(side=LEFT, padx=10)
        tb.Button(btn_frame, text="🚪 Logout", bootstyle="secondary-outline", width=16, command=self.handle_logout).pack(side=LEFT, padx=10)

    def download_selected_evidence(self):
        selected = self.db_tree.selection()
        if not selected:
            Messagebox.show_warning("No selection", "Please select an evidence entry to download.")
            return
        item = self.db_tree.item(selected[0])
        filename = item['values'][1]
        if not os.path.exists(filename):
            Messagebox.show_error("File not found", f"File does not exist: {filename}")
            return
        save_path = filedialog.asksaveasfilename(defaultextension=".wav", initialfile=os.path.basename(filename), filetypes=[("WAV files", "*.wav")])
        if save_path:
            try:
                shutil.copy2(filename, save_path)
                Messagebox.show_info("Download complete", f"File saved to: {save_path}")
            except Exception as e:
                Messagebox.show_error("Error", f"Failed to save file: {e}")

    def delete_selected_evidence(self):
        selected = self.db_tree.selection()
        if not selected:
            Messagebox.show_warning("No selection", "Please select an evidence entry to delete.")
            return
        item = self.db_tree.item(selected[0])
        evidence_id = item['values'][0]
        filename = item['values'][1]
        confirm = Messagebox.yesno("Confirm Delete", f"Are you sure you want to delete this evidence?\n{filename}")
        if not confirm:
            return
        # Delete file
        try:
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            Messagebox.show_error("Error", f"Failed to delete file: {e}")
            return
        # Delete from database
        self.delete_evidence_from_db(evidence_id)
        Messagebox.show_info("Deleted", "Evidence deleted successfully.")
        self.build_db_tab()

    def delete_evidence_from_db(self, evidence_id):
        import sqlite3
        try:
            conn = sqlite3.connect('evidence.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM audio_logs WHERE id=?', (evidence_id,))
            conn.commit()
        except Exception as e:
            print(f"❌ Error deleting from database: {e}")
        finally:
            conn.close()

    def handle_logout(self):
        self.is_admin_logged_in = False
        self.admin_username = None
        # Remove database tab
        if self.db_frame in self.notebook.tabs():
            self.notebook.forget(self.db_frame)
        self.admin_status.config(text="Logged out.", foreground="orange")
        self.notebook.select(self.admin_frame)

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
        self.start_button.config(state=DISABLED)
        self.stop_button.config(state=NORMAL)
        self.secret_phrase_entry.config(state=DISABLED)
        messagebox.showinfo("Monitoring Started", "Silent Sentinel is now listening.")
        
        self.monitoring_thread = threading.Thread(target=monitoring_loop, args=(secret_phrase, self))
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()

    def stop_monitoring(self):
        stop_event.set()
        self.start_button.config(state=NORMAL)
        self.stop_button.config(state=DISABLED)
        self.secret_phrase_entry.config(state=NORMAL)
        self.update_status("🛑 Monitoring Stopped", "red")
        self.update_results("--", "--")

    def show_disable_alert_dialog(self, on_timeout_callback):
        """
        Shows a dialog with a 10-second countdown and a 'Disable Alert' button.
        If not disabled within 10 seconds, triggers the callback.
        """
        self.alert_cancelled = False
        dialog = tk.Toplevel(self.root)
        dialog.title("Alert Triggered!")
        dialog.geometry("350x150")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()
        dialog.transient(self.root)

        label = tb.Label(dialog, text="Secret phrase detected!\nYou have 10 seconds to disable the alert.", font=("Helvetica", 12))
        label.pack(pady=10)

        countdown_var = tk.StringVar(value="10")
        countdown_label = tb.Label(dialog, textvariable=countdown_var, font=("Helvetica", 24, "bold"), foreground="red")
        countdown_label.pack(pady=5)

        def disable_alert():
            self.alert_cancelled = True
            dialog.destroy()

        disable_btn = tb.Button(dialog, text="Disable Alert", command=disable_alert)
        disable_btn.pack(pady=10)

        def countdown(count):
            if self.alert_cancelled:
                return
            countdown_var.set(str(count))
            if count > 0:
                dialog.after(1000, countdown, count-1)
            else:
                dialog.destroy()
                if not self.alert_cancelled:
                    on_timeout_callback()

        countdown(10)

    # --- Main Admin Tab ---
    def build_main_admin_tab(self):
        frame = self.main_admin_frame
        for widget in frame.winfo_children(): widget.destroy()
        if not self.is_main_admin_logged_in:
            tb.Label(frame, text="Main Admin Login", font=("Helvetica", 18, "bold"), bootstyle="primary").pack(pady=20)
            # Username row
            main_user_row = tb.Frame(frame)
            main_user_row.pack(anchor=W, padx=10, pady=5)
            tb.Label(main_user_row, text="Username:", font=("Helvetica", 14)).pack(side=LEFT)
            self.main_admin_user = tb.Entry(main_user_row, font=("Helvetica", 14), width=30)
            self.main_admin_user.pack(side=LEFT, padx=10)
            # Password row
            main_pass_row = tb.Frame(frame)
            main_pass_row.pack(anchor=W, padx=10, pady=5)
            tb.Label(main_pass_row, text="Password:", font=("Helvetica", 14)).pack(side=LEFT)
            self.main_admin_pass = tb.Entry(main_pass_row, show="*", font=("Helvetica", 14), width=30)
            self.main_admin_pass.pack(side=LEFT, padx=10)
            tb.Button(frame, text="Login as Main Admin", bootstyle="danger", width=20, command=self.handle_main_admin_login).pack(pady=20)
            self.main_admin_status = tb.Label(frame, text="", font=("Helvetica", 14), bootstyle="warning")
            self.main_admin_status.pack(pady=10)
        else:
            tb.Label(frame, text="Pending Admin Registrations", font=("Helvetica", 18, "bold"), bootstyle="inverse-primary").pack(pady=20)
            # Table of pending admins
            columns = ("ID", "Username")
            self.pending_tree = tb.Treeview(frame, columns=columns, show="headings", height=12, bootstyle="dark")
            for col in columns:
                self.pending_tree.heading(col, text=col)
                self.pending_tree.column(col, width=120 if col=="ID" else 220)
            for row in get_pending_admins():
                self.pending_tree.insert("", tk.END, values=row)
            self.pending_tree.pack(fill=BOTH, expand=True, padx=20, pady=10)
            btn_frame = tb.Frame(frame)
            btn_frame.pack(pady=10)
            tb.Button(btn_frame, text="✅ Accept", bootstyle="success-outline", width=16, command=self.accept_selected_pending).pack(side=LEFT, padx=10)
            tb.Button(btn_frame, text="🗑️ Delete", bootstyle="danger-outline", width=16, command=self.delete_selected_pending).pack(side=LEFT, padx=10)
            tb.Button(btn_frame, text="🔄 Refresh", bootstyle="info-outline", width=16, command=self.build_main_admin_tab).pack(side=LEFT, padx=10)
            tb.Button(btn_frame, text="🚪 Logout", bootstyle="secondary-outline", width=16, command=self.handle_main_admin_logout).pack(side=LEFT, padx=10)

    def handle_main_admin_login(self):
        username = self.main_admin_user.get().strip()
        password = self.main_admin_pass.get().strip()
        if username == "Abhishek P" and password == "Abhi@2004":
            self.is_main_admin_logged_in = True
            self.build_main_admin_tab()
        else:
            self.main_admin_status.config(text="Main admin login failed.", foreground="red")

    def handle_main_admin_logout(self):
        self.is_main_admin_logged_in = False
        self.build_main_admin_tab()

    def accept_selected_pending(self):
        selected = self.pending_tree.selection()
        if not selected:
            Messagebox.show_warning("No selection", "Please select a pending admin to accept.")
            return
        item = self.pending_tree.item(selected[0])
        pending_id = item['values'][0]
        if accept_pending_admin(pending_id):
            Messagebox.show_info("Accepted", "Admin approved and can now log in.")
        else:
            Messagebox.show_error("Error", "Failed to accept admin.")
        self.build_main_admin_tab()

    def delete_selected_pending(self):
        selected = self.pending_tree.selection()
        if not selected:
            Messagebox.show_warning("No selection", "Please select a pending admin to delete.")
            return
        item = self.pending_tree.item(selected[0])
        pending_id = item['values'][0]
        if delete_pending_admin(pending_id):
            Messagebox.show_info("Deleted", "Pending admin deleted.")
        else:
            Messagebox.show_error("Error", "Failed to delete pending admin.")
        self.build_main_admin_tab()

    def open_precise_location_page(self):
        # Open the local Flask page in the browser
        webbrowser.open_new_tab("http://localhost:5000/get_precise_location")
        # Start polling for location
        self.root.after(1000, self.check_precise_location)

    def check_precise_location(self):
        from gui_app import precise_location
        if precise_location['lat'] is not None and precise_location['lng'] is not None:
            lat, lng = precise_location['lat'], precise_location['lng']
            self.precise_location_label.config(text=f"Precise Location: {lat:.6f}, {lng:.6f}")
            # Optionally, update the location link as well
            self.location_label.config(text=f"Location Link: https://www.google.com/maps?q={lat},{lng}")
        else:
            self.root.after(1000, self.check_precise_location)

@flask_app.route('/test_html')
def test_html():
    return FlaskResponse("<html><body><h1>Flask HTML is working!</h1></body></html>", mimetype='text/html')

if __name__ == "__main__":
    # Initialize the database
    init_database()
    
    # Start Flask app in a separate thread
    def run_flask():
        flask_app.run(host="0.0.0.0", port=5050, debug=False, use_reloader=False)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    root = tk.Tk()
    app = SentinelApp(root)
    root.mainloop() 