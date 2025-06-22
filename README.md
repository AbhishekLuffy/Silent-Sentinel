# Silent Sentinel - Setup Guide

Welcome to Silent Sentinel! This guide will walk you through the necessary steps to set up and run the project on your local machine after cloning the repository.

## 1. Prerequisites

Before you begin, ensure you have the following software installed on your system:

*   **Python 3**: The core programming language for the project. You can download it from [python.org](https://www.python.org/downloads/).
*   **Git**: The version control system used to clone the repository. You can download it from [git-scm.com](https://git-scm.com/downloads).
*   **(macOS Only) Homebrew**: A package manager for macOS, required to install a specific audio dependency. You can install it from [brew.sh](https://brew.sh/).

## 2. Cloning the Repository

First, clone the project from GitHub to your local machine using the following command in your terminal:

```bash
git clone https://github.com/AbhishekLuffy/Silent-Sentinel.git
cd Silent-Sentinel
```

## 3. Environment Setup and Dependencies

This project has several dependencies, including ones for handling audio, sending alerts, and managing environment variables.

### Step 3.1: Install PortAudio (macOS Only)

`PyAudio` has a system dependency called `PortAudio`. If you are on macOS, you must install it first using Homebrew:

```bash
brew install portaudio
```
*(For Windows/Linux, `pip` will often handle this, but you may need to consult `PyAudio`'s documentation for your specific distribution if you encounter issues.)*

### Step 3.2: Create a Virtual Environment (Recommended)

It's highly recommended to use a virtual environment to keep the project's dependencies isolated from your system's global Python packages.

```bash
# Create a virtual environment named 'venv'
python3 -m venv venv

# Activate the virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
.\\venv\\Scripts\\activate
```

### Step 3.3: Install Python Packages

With your virtual environment activated, install all the necessary Python packages listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

## 4. Configuration (Crucial Step)

The application uses external services (Twilio for SMS, Gmail for email) and requires API keys and credentials to function. These are stored in a `.env` file that you must create yourself, as it's excluded from the repository for security reasons.

### Step 4.1: Create the `.env` file

In the root directory of the project, create a new file named `.env`.

### Step 4.2: Add Your Credentials

Open the `.env` file and add the following variables, replacing the placeholder values with your actual information:

```ini
# --- Twilio Credentials for SMS Alerts ---
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
TWILIO_PHONE=+15017122661 # Your Twilio phone number
TARGET_PHONE=+919876543210 # The verified number to send SMS alerts to

# --- Gmail Credentials for Email Alerts ---
SENDER_EMAIL=your.email@gmail.com
SENDER_PASSWORD=your_google_app_password_here # IMPORTANT: Use an App Password
RECIPIENT_EMAIL=recipient.email@example.com # The email address to send alerts to
```

### **How to get the credentials:**

*   **Twilio (`TWILIO_*`)**:
    1.  Log in to your [Twilio Console](https://www.twilio.com/console).
    2.  Your `Account SID` and `Auth Token` are on the main dashboard.
    3.  `TWILIO_PHONE` is the phone number you purchased or were assigned by Twilio.
    4.  `TARGET_PHONE` must be a number you have verified in your Twilio account.

*   **Gmail (`SENDER_*`)**:
    1.  `SENDER_EMAIL` is the Gmail address you want to send alerts from.
    2.  **IMPORTANT**: You cannot use your regular Gmail password. You must generate a 16-character **App Password**. Follow the instructions on Google's support page: [Sign in with App Passwords](https://support.google.com/accounts/answer/185833).

## 5. Running the Application

Once all the setup and configuration steps are complete, you can launch the application with the following command:

```bash
python gui_app.py
```

This will open the Silent Sentinel desktop GUI, and you can start monitoring from there. 