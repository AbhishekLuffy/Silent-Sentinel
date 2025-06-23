import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def make_call():
    """
    Makes a phone call using Twilio to play a demo audio message when the secret phrase is detected.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_phone = os.getenv("TWILIO_PHONE")
    recipient_phone = os.getenv("RECIPIENT_PHONE_NUMBER")

    # Check if all required environment variables are set
    if not all([account_sid, auth_token, twilio_phone, recipient_phone]):
        print("❌ Error: Twilio environment variables not set. Cannot make phone call.")
        return

    try:
        client = Client(account_sid, auth_token)
        
        # Make the call
        # This will use Twilio's text-to-speech to say a message
        # You can replace the 'url' parameter with a TwiML Bin URL if you want to play custom audio
        call = client.calls.create(
            twiml='<Response><Say>Emergency alert! The secret phrase has been detected. This is an automated call from Silent Sentinel.</Say></Response>',
            from_=twilio_phone,
            to=recipient_phone
        )
        print(f"✅ Phone call initiated successfully! Call SID: {call.sid}")
        return call.sid
    except Exception as e:
        print(f"❌ Failed to make phone call: {e}")
        return None

if __name__ == '__main__':
    # This block allows you to test the phone call functionality directly
    print("Testing phone call...")
    make_call() 