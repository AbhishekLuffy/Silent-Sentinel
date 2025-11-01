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
    register_pending_admin, get_pending_admins, accept_pending_admin, delete_pending_admin,
    create_user, verify_user, get_all_users
)
from flask import Flask, Response as FlaskResponse
from flask import request, redirect, url_for, session
import shutil
import webbrowser
import json

# --- Flask App for TwiML Voice Alert ---
flask_app = Flask(__name__)
flask_app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

@flask_app.route('/voice_alert', methods=['GET', 'POST'])
def voice_alert():
    response = VoiceResponse()
    response.say(
        "This is an emergency alert from Silent Sentinel. Help is needed at location: latitude 13.3223, longitude 75.774. "
        "An SMS and Email have already been sent to your mobile with full details. Please check them and respond immediately.",
        voice='alice', language='en-US')
    return FlaskResponse(str(response), mimetype='text/xml')

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
    <p id="coords"></p>
    <script>
    function getLocation() {
      document.getElementById('status').innerText = 'Requesting location...';
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function(pos) {
          document.getElementById('status').innerText = 'Location received! Sending to app...';
          document.getElementById('coords').innerText = 'Latitude: ' + pos.coords.latitude + ', Longitude: ' + pos.coords.longitude;
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
precise_location = {'lat': None, 'lng': None}

@flask_app.route('/submit_location', methods=['POST'])
def submit_location():
    data = request.get_json()
    precise_location['lat'] = data.get('lat')
    precise_location['lng'] = data.get('lng')
    return 'OK'

# --- Auth Pages (Signup/Login/Logout) ---
@flask_app.route('/')
def index():
    if session.get('user_phone'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth'))

@flask_app.route('/auth', methods=['GET', 'POST'])
def auth():
    error_signup = ''
    error_login = ''
    if request.method == 'POST':
        action = request.form.get('action', '')
        if action == 'signup':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            phone = request.form.get('phone', '').strip()
            address = request.form.get('address', '').strip()
            password = request.form.get('password', '')
            confirm = request.form.get('confirm', '')
            if not name or not email or not phone or not address or not password or password != confirm:
                error_signup = 'Invalid input or passwords do not match.'
            else:
                created = create_user(name, email, phone, address, password)
                if not created:
                    error_signup = 'Email or phone already registered.'
                else:
                    session['user_phone'] = phone
                    return redirect(url_for('dashboard'))
        elif action == 'login':
            phone = request.form.get('phone', '').strip()
            password = request.form.get('password', '')
            if verify_user(phone, password):
                session['user_phone'] = phone
                return redirect(url_for('dashboard'))
            else:
                error_login = 'Invalid credentials.'
    return FlaskResponse(auth_combined_html(error_signup, error_login), mimetype='text/html')

# Keep legacy routes but redirect to /auth to avoid multiple pages
@flask_app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        return auth()
    return redirect(url_for('auth'))

@flask_app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        return auth()
    return redirect(url_for('auth'))

@flask_app.route('/logout')
def logout():
    session.pop('user_phone', None)
    return redirect(url_for('auth'))

@flask_app.route('/dashboard')
def dashboard():
    if not session.get('user_phone'):
        return redirect(url_for('login'))
    html = f'''
    <html><body style="font-family:sans-serif;background:#111;color:#eee;padding:30px;">
    <h2>Welcome</h2>
    <p>You are logged in as: {session.get('user_phone')}</p>
    <p>
      <a href="{url_for('logout')}">Logout</a> |
      <a href="{url_for('get_precise_location_page')}">Get Precise Location</a> |
      <a href="{url_for('admin_users')}">Admin: Users</a>
    </p>
    </body></html>
    '''
    return FlaskResponse(html, mimetype='text/html')

def auth_combined_html(error_signup: str, error_login: str):
    # Build HTML without using f-strings to avoid escaping JS braces
    signup_error_html = '<p style="color:red;">' + error_signup + '</p>' if error_signup else ''
    login_error_html = '<p style="color:red;">' + error_login + '</p>' if error_login else ''
    base_html = '''
    <html><body style="font-family:sans-serif;background:#111;color:#eee;padding:30px;">
    <h2>Welcome to Silent Sentinel</h2>
    <div style="margin:10px 0;">
      <button onclick="showTab('login')">Login</button>
      <button onclick="showTab('signup')">Create Account</button>
    </div>
    <div id="login" style="display:block;max-width:420px;padding:16px;border:1px solid #333;">
      <h3>Login</h3>
      __LOGIN_ERROR__
      <form method="POST">
        <input type="hidden" name="action" value="login" />
        <div><label>Phone (User ID)</label><br><input name="phone" required></div>
        <div><label>Password</label><br><input name="password" type="password" required></div>
        <button type="submit">Login</button>
      </form>
    </div>
    <div id="signup" style="display:none;max-width:420px;padding:16px;border:1px solid #333;margin-top:20px;">
      <h3>Create Account</h3>
      __SIGNUP_ERROR__
      <form method="POST">
        <input type="hidden" name="action" value="signup" />
        <div><label>Name</label><br><input name="name" required></div>
        <div><label>Email</label><br><input name="email" type="email" required></div>
        <div><label>Phone (User ID)</label><br><input name="phone" required></div>
        <div><label>Address</label><br><input name="address" required></div>
        <div><label>Password</label><br><input name="password" type="password" required></div>
        <div><label>Confirm Password</label><br><input name="confirm" type="password" required></div>
        <button type="submit">Create account</button>
      </form>
    </div>
    <script>
    function showTab(tab){
      document.getElementById('login').style.display = tab==='login' ? 'block' : 'none';
      document.getElementById('signup').style.display = tab==='signup' ? 'block' : 'none';
    }
    </script>
    </body></html>
    '''
    return base_html.replace('__LOGIN_ERROR__', login_error_html).replace('__SIGNUP_ERROR__', signup_error_html)

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
        Messagebox.showerror("Microphone Error", f"Could not open microphone: {e}")
        return

    while not stop_event.is_set():
        app_instance.update_status("🟢 Listening...", "green")
        frames = [stream.read(CHUNK, exception_on_overflow=False) for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)) if not stop_event.is_set()]

        if stop_event.is_set(): break

        # Transcribe the audio and check for the secret phrase
        transcription = None
        # Save the audio to a temporary file for transcription only (not for evidence)
        temp_filename = os.path.join(OUTPUT_DIR, "temp_clip.wav")
        with wave.open(temp_filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(audio.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))

        print(f"Temporary audio for transcription: {temp_filename}")

        r = sr.Recognizer()
        with sr.AudioFile(temp_filename) as source:
            try:
                text = r.recognize_google(r.record(source)).lower()
                transcription = text
                app_instance.update_results(f'"{text}"', None)
                if secret_phrase in text:
                    app_instance.update_status("✅ Triggered! Waiting to send alerts...", "orange")
                    location_link = get_location_link()
                    app_instance.update_results(f'"{text}"', location_link)
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
        # Remove the temporary file after use
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

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
        self.root.geometry("1000x700")
        self.root.resizable(True, True)
        self.is_admin_logged_in = False
        self.admin_username = None
        self.is_main_admin_logged_in = False
        self.current_user_phone = None
        
        # Use a modern dark theme with custom styling
        style = tb.Style("superhero")
        self.root.configure(bg="#0a0a0a")
        
        # Configure custom styles for modern look with hover effects
        style.configure("Modern.TFrame", background="#1a1a1a", relief="flat")
        style.configure("Card.TFrame", background="#2a2a2a", relief="flat", borderwidth=1)
        style.configure("Gradient.TLabel", background="#1a1a1a", foreground="#ffffff", font=("Segoe UI", 12))
        style.configure("Title.TLabel", background="#1a1a1a", foreground="#00d4ff", font=("Segoe UI", 24, "bold"))
        style.configure("Subtitle.TLabel", background="#1a1a1a", foreground="#888888", font=("Segoe UI", 11))
        style.configure("Modern.TButton", background="#00d4ff", foreground="#000000", font=("Segoe UI", 10, "bold"))
        style.configure("Success.TButton", background="#00ff88", foreground="#000000", font=("Segoe UI", 10, "bold"))
        style.configure("Danger.TButton", background="#ff4444", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        
        # Add hover effects for buttons
        style.map("Modern.TButton", 
                 background=[('active', '#00b8e6'), ('pressed', '#0099cc')])
        style.map("Success.TButton", 
                 background=[('active', '#00e677'), ('pressed', '#00cc66')])
        style.map("Danger.TButton", 
                 background=[('active', '#ff6666'), ('pressed', '#cc3333')])
        
        # Add hover effects for frames
        style.map("Card.TFrame", 
                 background=[('active', '#3a3a3a')])

        # --- Modern Animated Header ---
        header_frame = tb.Frame(self.root, style="Modern.TFrame")
        header_frame.pack(fill=X, pady=(0, 15))
        
        # Add gradient effect with multiple frames
        gradient_frame = tb.Frame(header_frame, style="Modern.TFrame")
        gradient_frame.pack(fill=X, padx=0, pady=0)
        
        title_frame = tb.Frame(gradient_frame, style="Modern.TFrame")
        title_frame.pack(side=LEFT, padx=(40, 20), pady=25)
        
        # Main title with glow effect and hover animation
        title_label = tb.Label(title_frame, text="🔐 Silent Sentinel", style="Title.TLabel")
        title_label.pack(anchor=W)
        self.add_hover_effect(title_label, "#00d4ff", "#00e6ff")
        
        # Subtitle with fade effect
        subtitle_label = tb.Label(title_frame, text="Emergency Alert System", style="Subtitle.TLabel")
        subtitle_label.pack(anchor=W, pady=(5, 0))
        self.add_hover_effect(subtitle_label, "#888888", "#aaaaaa")
        
        # Status indicator (will be updated after login)
        self.status_frame = tb.Frame(gradient_frame, style="Modern.TFrame")
        self.status_frame.pack(side=RIGHT, padx=(20, 40), pady=25)

        # --- Notebook (Tabs) - Hidden until auth ---
        self.notebook = tb.Notebook(self.root, bootstyle="dark")
        # Don't pack yet - will be shown after authentication

        # --- Add desktop app features ---
        self.add_desktop_app_features()
        
        # --- Blocker: Require user auth (login/create account) before entering the app ---
        self.show_user_auth_modal()

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
        
        # Modern card design with gradient effect and hover
        card = tb.Frame(frame, style="Card.TFrame", padding=40)
        card.pack(pady=30, padx=30, fill=BOTH, expand=True)
        self.add_card_hover_effect(card)
        
        # Header section with modern styling and hover effects
        header_section = tb.Frame(card, style="Card.TFrame")
        header_section.pack(fill=X, pady=(0, 30))
        
        header_title = tb.Label(header_section, text="🎙️ Audio Monitoring", style="Title.TLabel")
        header_title.pack(anchor=W)
        self.add_hover_effect(header_title, "#00d4ff", "#00e6ff")
        
        header_subtitle = tb.Label(header_section, text="Configure your emergency alert system", style="Subtitle.TLabel")
        header_subtitle.pack(anchor=W, pady=(5, 0))
        self.add_hover_effect(header_subtitle, "#888888", "#aaaaaa")
        # Secret Phrase Input with modern styling and hover effects
        phrase_section = tb.Frame(card, style="Card.TFrame")
        phrase_section.pack(fill=X, pady=(0, 20))
        self.add_card_hover_effect(phrase_section)
        
        phrase_label = tb.Label(phrase_section, text="Secret Phrase", style="Gradient.TLabel")
        phrase_label.pack(anchor=W, pady=(0, 8))
        self.add_hover_effect(phrase_label, "#ffffff", "#00d4ff")
        
        phrase_frame = tb.Frame(phrase_section, style="Card.TFrame")
        phrase_frame.pack(fill=X)
        
        self.secret_phrase_entry = tb.Entry(phrase_frame, font=("Segoe UI", 14), width=40)
        self.secret_phrase_entry.insert(0, "help me lotus")
        self.secret_phrase_entry.pack(fill=X, pady=(0, 10))
        
        # Add focus effects to entry
        self.add_entry_focus_effect(self.secret_phrase_entry)
        
        # Location section with modern button and hover effects
        location_section = tb.Frame(card, style="Card.TFrame")
        location_section.pack(fill=X, pady=(0, 20))
        self.add_card_hover_effect(location_section)
        
        loc_btn = tb.Button(location_section, text="📍 Get Precise Location", style="Modern.TButton", 
                           width=30, command=self.open_precise_location_page)
        loc_btn.pack(pady=(0, 10))
        self.add_button_hover_animation(loc_btn, "#00d4ff", "#00b8e6", "#0099cc")
        
        self.precise_location_label = tb.Label(location_section, text="Precise Location: Not set", 
                                             style="Subtitle.TLabel")
        self.precise_location_label.pack()
        self.add_hover_effect(self.precise_location_label, "#888888", "#aaaaaa")
        
        # Control buttons with modern styling and hover effects
        control_section = tb.Frame(card, style="Card.TFrame")
        control_section.pack(fill=X, pady=(20, 0))
        self.add_card_hover_effect(control_section)
        
        button_frame = tb.Frame(control_section, style="Card.TFrame")
        button_frame.pack()
        
        self.start_button = tb.Button(button_frame, text="🎙️ Start Monitoring", style="Success.TButton", 
                                     width=25, command=self.start_monitoring)
        self.start_button.pack(side=LEFT, padx=(0, 15))
        self.add_button_hover_animation(self.start_button, "#00ff88", "#00e677", "#00cc66")
        
        self.stop_button = tb.Button(button_frame, text="⛔ Stop Monitoring", style="Danger.TButton", 
                                    width=25, command=self.stop_monitoring, state=DISABLED)
        self.stop_button.pack(side=LEFT)
        self.add_button_hover_animation(self.stop_button, "#ff4444", "#ff6666", "#cc3333")
        # Status & Results with modern styling and hover effects
        status_section = tb.Frame(card, style="Card.TFrame")
        status_section.pack(fill=X, pady=(30, 0))
        self.add_card_hover_effect(status_section)
        
        status_title = tb.Label(status_section, text="System Status", style="Gradient.TLabel")
        status_title.pack(anchor=W, pady=(0, 10))
        self.add_hover_effect(status_title, "#ffffff", "#00d4ff")
        
        self.status_label = tb.Label(status_section, text="🛑 Monitoring Stopped", 
                                   style="Danger.TLabel", font=("Segoe UI", 14, "bold"))
        self.status_label.pack(anchor=W, pady=(0, 8))
        self.add_hover_effect(self.status_label, "#ff4444", "#ff6666")
        
        self.transcription_label = tb.Label(status_section, text="Last Transcription: --", 
                                          style="Subtitle.TLabel", wraplength=700)
        self.transcription_label.pack(anchor=W, pady=(0, 5))
        self.add_hover_effect(self.transcription_label, "#888888", "#aaaaaa")
        
        self.location_label = tb.Label(status_section, text="Location Link: --", 
                                     style="Gradient.TLabel", cursor="hand2")
        self.location_label.pack(anchor=W)
        self.add_hover_effect(self.location_label, "#ffffff", "#00d4ff")
        self.alert_cancelled = False

    def add_hover_effect(self, widget, normal_color, hover_color):
        """Add hover effect to any widget"""
        def on_enter(event):
            widget.config(foreground=hover_color)
            widget.config(cursor="hand2")
        
        def on_leave(event):
            widget.config(foreground=normal_color)
            widget.config(cursor="")
        
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def add_button_hover_animation(self, button, normal_bg, hover_bg, pressed_bg):
        """Add custom hover animation to buttons"""
        def on_enter(event):
            button.config(background=hover_bg)
            # Add subtle scale effect
            button.config(relief="raised")
        
        def on_leave(event):
            button.config(background=normal_bg)
            button.config(relief="flat")
        
        def on_press(event):
            button.config(background=pressed_bg)
        
        def on_release(event):
            button.config(background=hover_bg)
        
        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)
        button.bind("<Button-1>", on_press)
        button.bind("<ButtonRelease-1>", on_release)

    def add_card_hover_effect(self, card_frame):
        """Add hover effect to card frames"""
        def on_enter(event):
            card_frame.config(background="#3a3a3a")
            # Add subtle shadow effect
            card_frame.config(relief="raised")
        
        def on_leave(event):
            card_frame.config(background="#2a2a2a")
            card_frame.config(relief="flat")
        
        card_frame.bind("<Enter>", on_enter)
        card_frame.bind("<Leave>", on_leave)

    def add_entry_focus_effect(self, entry_widget):
        """Add focus effects to entry widgets"""
        def on_focus_in(event):
            entry_widget.config(relief="solid", borderwidth=2)
            entry_widget.config(highlightcolor="#00d4ff")
        
        def on_focus_out(event):
            entry_widget.config(relief="flat", borderwidth=1)
        
        entry_widget.bind("<FocusIn>", on_focus_in)
        entry_widget.bind("<FocusOut>", on_focus_out)

    def add_desktop_app_features(self):
        """Add desktop app-like features"""
        # Add window controls
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Add keyboard shortcuts
        self.root.bind("<Control-q>", lambda e: self.on_closing())
        self.root.bind("<F5>", lambda e: self.refresh_application())
        
        # Add window state management
        self.root.bind("<Configure>", self.on_window_configure)
        
        # Add tooltips for better UX
        self.add_tooltips()

    def on_closing(self):
        """Handle application closing"""
        if hasattr(self, 'monitoring_thread') and self.monitoring_thread.is_alive():
            stop_event.set()
        self.root.quit()
        self.root.destroy()

    def refresh_application(self):
        """Refresh the application"""
        self.root.update_idletasks()

    def on_window_configure(self, event):
        """Handle window configuration changes"""
        if event.widget == self.root:
            # Add window state management here if needed
            pass

    def add_tooltips(self):
        """Add tooltips to important elements"""
        # This would require a tooltip library, but we can simulate with status updates
        pass

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
        """Update status with smooth color transition"""
        def update():
            self.status_label.config(text=message)
            if color == "green":
                self.status_label.config(foreground="#00ff88")
            elif color == "red":
                self.status_label.config(foreground="#ff4444")
            elif color == "orange":
                self.status_label.config(foreground="#ffaa00")
            else:
                self.status_label.config(foreground="#ffffff")
        self.root.after(0, update)

    def update_results(self, transcription, location_link):
        self.root.after(0, lambda: self.transcription_label.config(text=f"Last Transcription: {transcription}"))
        if location_link:
            self.root.after(0, lambda: self.location_label.config(text=f"Location Link: {location_link}"))

    def start_monitoring(self):
        secret_phrase = self.secret_phrase_entry.get().strip().lower()
        if not secret_phrase:
            Messagebox.show_warning("Warning", "Secret phrase cannot be empty.")
            return

        stop_event.clear()
        self.start_button.config(state=DISABLED)
        self.stop_button.config(state=NORMAL)
        self.secret_phrase_entry.config(state=DISABLED)
        Messagebox.show_info("Monitoring Started", "Silent Sentinel is now listening.")
        
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

    # --- User Auth Modal (Login / Create Account) ---
    def show_user_auth_modal(self):
        modal = tk.Toplevel(self.root)
        modal.title("Silent Sentinel - Authentication")
        modal.geometry("600x650")
        modal.resizable(False, False)
        modal.transient(self.root)
        modal.grab_set()
        modal.configure(bg="#0a0a0a")

        # Modern modal styling
        container = tb.Frame(modal, style="Modern.TFrame", padding=40)
        container.pack(fill=BOTH, expand=True)

        # Header with gradient effect
        header_frame = tb.Frame(container, style="Modern.TFrame")
        header_frame.pack(fill=X, pady=(0, 30))
        
        title = tb.Label(header_frame, text="🔐 Welcome to Silent Sentinel", 
                        style="Title.TLabel", font=("Segoe UI", 20, "bold"))
        title.pack(pady=(0, 8))
        
        subtitle = tb.Label(header_frame, text="Please login or create an account to continue", 
                           style="Subtitle.TLabel")
        subtitle.pack()

        tabs = tb.Notebook(container, bootstyle="dark")
        tabs.pack(fill=BOTH, expand=True)

        # Login Tab with modern styling
        login_tab = tb.Frame(tabs, style="Card.TFrame")
        tabs.add(login_tab, text="🔑 Login")

        login_status = tb.Label(login_tab, text="", style="Danger.TLabel")
        login_status.pack(pady=(20, 0))

        # Modern form styling
        form_frame = tb.Frame(login_tab, style="Card.TFrame")
        form_frame.pack(fill=X, padx=20, pady=20)

        lf1 = tb.Frame(form_frame, style="Card.TFrame")
        lf1.pack(fill=X, pady=12)
        tb.Label(lf1, text="Phone (User ID)", style="Gradient.TLabel", width=20, anchor=W).pack(side=LEFT)
        login_phone_entry = tb.Entry(lf1, font=("Segoe UI", 12), width=25)
        login_phone_entry.pack(side=LEFT, padx=(10, 0))

        lf2 = tb.Frame(form_frame, style="Card.TFrame")
        lf2.pack(fill=X, pady=12)
        tb.Label(lf2, text="Password", style="Gradient.TLabel", width=20, anchor=W).pack(side=LEFT)
        login_password_entry = tb.Entry(lf2, font=("Segoe UI", 12), width=25, show="*")
        login_password_entry.pack(side=LEFT, padx=(10, 0))

        def perform_login():
            phone = login_phone_entry.get().strip()
            password = login_password_entry.get().strip()
            if not phone or not password:
                login_status.config(text="Phone and password are required.")
                return
            if verify_user(phone, password):
                self.current_user_phone = phone
                modal.destroy()
                self.show_main_application()
            else:
                login_status.config(text="Invalid credentials.")

        login_btn = tb.Button(form_frame, text="🚀 Login", style="Success.TButton", 
                             width=20, command=perform_login)
        login_btn.pack(pady=(20, 0))
        self.add_button_hover_animation(login_btn, "#00ff88", "#00e677", "#00cc66")

        # Create Account Tab with modern styling
        signup_tab = tb.Frame(tabs, style="Card.TFrame")
        tabs.add(signup_tab, text="✨ Create Account")

        signup_status = tb.Label(signup_tab, text="", style="Danger.TLabel")
        signup_status.pack(pady=(20, 0))

        # Modern signup form styling
        signup_form_frame = tb.Frame(signup_tab, style="Card.TFrame")
        signup_form_frame.pack(fill=X, padx=20, pady=20)

        sf1 = tb.Frame(signup_form_frame, style="Card.TFrame")
        sf1.pack(fill=X, pady=8)
        tb.Label(sf1, text="Name", style="Gradient.TLabel", width=20, anchor=W).pack(side=LEFT)
        su_name = tb.Entry(sf1, font=("Segoe UI", 12), width=25)
        su_name.pack(side=LEFT, padx=(10, 0))

        sf2 = tb.Frame(signup_form_frame, style="Card.TFrame")
        sf2.pack(fill=X, pady=8)
        tb.Label(sf2, text="Email", style="Gradient.TLabel", width=20, anchor=W).pack(side=LEFT)
        su_email = tb.Entry(sf2, font=("Segoe UI", 12), width=25)
        su_email.pack(side=LEFT, padx=(10, 0))

        sf3 = tb.Frame(signup_form_frame, style="Card.TFrame")
        sf3.pack(fill=X, pady=8)
        tb.Label(sf3, text="Phone (User ID)", style="Gradient.TLabel", width=20, anchor=W).pack(side=LEFT)
        su_phone = tb.Entry(sf3, font=("Segoe UI", 12), width=25)
        su_phone.pack(side=LEFT, padx=(10, 0))

        sf4 = tb.Frame(signup_form_frame, style="Card.TFrame")
        sf4.pack(fill=X, pady=8)
        tb.Label(sf4, text="Address", style="Gradient.TLabel", width=20, anchor=W).pack(side=LEFT)
        su_address = tb.Entry(sf4, font=("Segoe UI", 12), width=25)
        su_address.pack(side=LEFT, padx=(10, 0))

        sf5 = tb.Frame(signup_form_frame, style="Card.TFrame")
        sf5.pack(fill=X, pady=8)
        tb.Label(sf5, text="Password", style="Gradient.TLabel", width=20, anchor=W).pack(side=LEFT)
        su_password = tb.Entry(sf5, font=("Segoe UI", 12), width=25, show="*")
        su_password.pack(side=LEFT, padx=(10, 0))

        sf6 = tb.Frame(signup_form_frame, style="Card.TFrame")
        sf6.pack(fill=X, pady=8)
        tb.Label(sf6, text="Confirm Password", style="Gradient.TLabel", width=20, anchor=W).pack(side=LEFT)
        su_confirm = tb.Entry(sf6, font=("Segoe UI", 12), width=25, show="*")
        su_confirm.pack(side=LEFT, padx=(10, 0))

        def perform_signup():
            name = su_name.get().strip()
            email = su_email.get().strip().lower()
            phone = su_phone.get().strip()
            address = su_address.get().strip()
            password = su_password.get().strip()
            confirm = su_confirm.get().strip()
            if not name or not email or not phone or not address or not password:
                signup_status.config(text="All fields are required.")
                return
            if password != confirm:
                signup_status.config(text="Passwords do not match.")
                return
            if create_user(name, email, phone, address, password):
                # Account created successfully - clear form and switch to login tab
                su_name.delete(0, tk.END)
                su_email.delete(0, tk.END)
                su_phone.delete(0, tk.END)
                su_address.delete(0, tk.END)
                su_password.delete(0, tk.END)
                su_confirm.delete(0, tk.END)
                signup_status.config(text="Account created! Please login with your credentials.", bootstyle="success")
                # Switch to login tab and pre-fill phone
                tabs.select(0)  # Switch to login tab
                login_phone_entry.delete(0, tk.END)
                login_phone_entry.insert(0, phone)
                login_status.config(text="Account created successfully. Please login.", bootstyle="success")
            else:
                signup_status.config(text="Email or phone already registered.")

        signup_btn = tb.Button(signup_form_frame, text="✨ Create Account", style="Success.TButton", 
                              width=20, command=perform_signup)
        signup_btn.pack(pady=(20, 0))
        self.add_button_hover_animation(signup_btn, "#00ff88", "#00e677", "#00cc66")

    def show_main_application(self):
        """Show the main application interface after successful authentication"""
        # Animate the notebook appearance
        self.animate_notebook_appearance()
        
        # Update header to show logged in user with animation
        self.animate_user_status()
    
    def animate_notebook_appearance(self):
        """Animate the notebook sliding in from the right"""
        # Pack the notebook to make the main app visible
        self.notebook.pack(fill=BOTH, expand=True, padx=20, pady=10)
        
        # Add a subtle animation effect
        self.root.update_idletasks()
        
    def animate_user_status(self):
        """Animate the user status indicator"""
        # Clear existing status
        for widget in self.status_frame.winfo_children():
            widget.destroy()
        
        # Create animated status indicator
        status_container = tb.Frame(self.status_frame, style="Modern.TFrame")
        status_container.pack()
        
        # Online indicator with pulsing effect
        online_indicator = tb.Label(status_container, text="🟢", font=("Segoe UI", 12))
        online_indicator.pack(side=LEFT, padx=(0, 8))
        
        user_label = tb.Label(status_container, text=f"Logged in: {self.current_user_phone}", 
                             style="Gradient.TLabel")
        user_label.pack(side=LEFT)
        
        # Add pulsing animation to the indicator
        self.pulse_indicator(online_indicator)
    
    def pulse_indicator(self, indicator):
        """Create a pulsing animation for the online indicator"""
        def pulse():
            current_color = indicator.cget("foreground")
            if current_color == "#00ff88":
                indicator.config(foreground="#00aa55")
            else:
                indicator.config(foreground="#00ff88")
            self.root.after(1000, pulse)
        pulse()

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
        # Open the local Flask page in the browser (correct port 5050)
        webbrowser.open_new_tab("http://localhost:5050/get_precise_location")
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

# --- Admin Users Web View ---
@flask_app.route('/admin/users')
def admin_users():
    # Require normal login first
    if not session.get('user_phone'):
        return redirect(url_for('login'))
    # Simple table of registered users
    rows = get_all_users()
    tr = ''.join([f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3] or ''}</td><td>{r[4] or ''}</td><td>{r[5]}</td></tr>" for r in rows])
    html = f'''
    <html><body style="font-family:sans-serif;background:#111;color:#eee;padding:30px;">
    <h2>Registered Users</h2>
    <table border="1" cellpadding="8" cellspacing="0" style="border-color:#333;">
      <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Phone</th><th>Address</th><th>Created</th></tr></thead>
      <tbody>{tr}</tbody>
    </table>
    <p><a href="{url_for('dashboard')}">Back</a></p>
    </body></html>
    '''
    return FlaskResponse(html, mimetype='text/html')

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