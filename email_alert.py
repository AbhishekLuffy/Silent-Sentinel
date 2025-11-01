import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def send_email_alert(location_link="Location unavailable", latitude=None, longitude=None):
    """
    Sends an email alert using a Gmail account, including a location link and coordinates.
    """
    sender_email = os.getenv("SENDER_EMAIL")
    password = os.getenv("SENDER_PASSWORD")
    recipient_email = os.getenv("RECIPIENT_EMAIL")

    # Check if all required environment variables are set
    if not all([sender_email, password, recipient_email]):
        print("❌ Error: Email environment variables not set. Cannot send email.")
        return

    # Build the emergency message
    body = (
        "🚨 EMERGENCY ALERT 🚨\n\n"
        "This is an emergency message from Silent Sentinel.\n"
        "The secret phrase was detected. Immediate attention is required!\n\n"
    )
    if latitude and longitude:
        body += (
            f"Location Coordinates:\n"
            f"Latitude: {latitude}\n"
            f"Longitude: {longitude}\n"
            f"Google Maps: https://www.google.com/maps?q={latitude},{longitude}\n\n"
        )
    else:
        body += f"Last known location: {location_link}\n\n"

    body += "Please respond immediately and check on the user.\n"

    subject = "🚨 Silent Sentinel Emergency Alert"
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = recipient_email

    try:
        # Connect to Gmail's SMTP server
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()  # Secure the connection
            server.login(sender_email, password)
            server.send_message(msg)
            print("✅ Email alert sent successfully!")
    except smtplib.SMTPAuthenticationError:
        print("❌ Failed to send email: Authentication failed. Check your email/password.")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

if __name__ == '__main__':
    # This block allows you to test the email functionality directly
    print("Testing email alert...")
    test_lat = "12.9716"
    test_lon = "77.5946"
    send_email_alert(latitude=test_lat, longitude=test_lon)