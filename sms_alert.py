import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def send_sms_alert(location_link="Location unavailable"):
    """
    Sends an SMS alert using Twilio, including a location link.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_phone = os.getenv("TWILIO_PHONE")
    target_phone = os.getenv("TARGET_PHONE")

    # Check if all required environment variables are set
    if not all([account_sid, auth_token, twilio_phone, target_phone]):
        print("❌ Error: Twilio environment variables not set. Cannot send SMS.")
        return

    try:
        client = Client(account_sid, auth_token)
        message_body = (
            f"🚨 Silent Sentinel Alert: Secret phrase detected from Abhishek P.\n"
            f"Location: {location_link}"
        )

        message = client.messages.create(
            body=message_body,
            from_=twilio_phone,
            to=target_phone
        )
        print(f"✅ SMS alert sent successfully! SID: {message.sid}")
    except Exception as e:
        print(f"❌ Failed to send SMS: {e}")

if __name__ == '__main__':
    # This block allows you to test the SMS functionality directly
    print("Testing SMS alert...")
    # Example link for testing
    test_link = "https://www.google.com/maps?q=12.9716,77.5946"
    send_sms_alert(test_link) 