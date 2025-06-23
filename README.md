# Silent Sentinel - Emergency Alert System

## Overview
Silent Sentinel is a modern, cross-platform emergency alert and evidence collection system. It features a professional dark-themed desktop GUI, real-time audio monitoring, multi-channel alerting (SMS, email, phone call), evidence logging, and a robust admin management system. The app is designed for both usability and security, with a focus on real-world emergency response scenarios.

---

## Key Features

### 1. **Modern GUI (ttkbootstrap, Dark Theme)**
- Clean, professional dark UI using the `superhero` theme.
- Responsive layout, clear fonts, and intuitive navigation.
- Card-like sections and accent colors for a real developer-grade look.

### 2. **Audio Monitoring & Secret Phrase Detection**
- Continuously listens for a user-defined secret phrase (e.g., "help me lotus").
- When detected, triggers a 10-second cancel window before sending alerts.
- Records 10 minutes of evidence audio after an event.

### 3. **Multi-Channel Emergency Alerts**
- **SMS Alert:** Sends a Twilio SMS to a configured phone number.
- **Email Alert:** Sends a detailed email to a configured address.
- **Phone Call:** Initiates a Twilio call with a custom voice message (using Flask + TwiML).
- All credentials are securely loaded from a `.env` file.

### 4. **Location Tracking**
- **IP-based location** (default) for quick, approximate location.
- **Precise device location:**
  - "Get Precise Location" button opens a browser page.
  - Uses browser geolocation (with user permission) to fetch exact coordinates.
  - Updates the app and Google Maps link with the precise location.

### 5. **Evidence Database**
- All audio evidence is logged in a local SQLite database (`evidence.db`).
- Each entry includes: filename, timestamp, location URL, and transcription.
- Database is viewable in-app (after admin login) with a modern, scrollable, striped table.
- Download and delete evidence directly from the app.

### 6. **Admin System**
- **Registration:** New admins must register and await approval.
- **Main Admin:**
  - Hardcoded credentials: Username `Abhishek P`, Password `Abhi@2004`.
  - Can view, accept, or delete pending admin registrations.
- **Only approved admins** can log in and view the evidence database.
- Secure password hashing and robust user management.

### 7. **In-App Navigation**
- Tabs for Home, Admin, Main Admin, and Database (after login).
- All admin and evidence management is handled within the GUI.

### 8. **Robust Error Handling & UX**
- All dialogs and notifications use modern, styled message boxes.
- Scrollbars, padding, and striped rows for easy evidence review.
- All actions are confirmed and user-friendly.

---

## How to Use

1. **Install dependencies:**
   - `pip install -r requirements.txt`
   - `pip install ttkbootstrap pillow`
2. **Configure your `.env` file** with Twilio and email credentials.
3. **Run the app:**
   - `python gui_app.py`
4. **Register as admin** (pending approval by main admin).
5. **Main admin** logs in, approves admins.
6. **Monitor for secret phrase, trigger alerts, and manage evidence.**
7. **Get precise location** using the browser button for device-level accuracy.

---

## Recent Major Updates (Today)
- Switched to a professional dark theme with ttkbootstrap.
- Added a modern, scrollable, striped evidence database table with download/delete.
- Implemented a robust admin system with main admin approval.
- Added browser-based precise location fetching.
- Improved all dialogs, error handling, and user experience.
- Cleaned up and modernized all UI elements for a real developer-grade look.

---

## Credits
Developed by Abhishek P and contributors.

---

For any issues or feature requests, please open an issue on GitHub. 