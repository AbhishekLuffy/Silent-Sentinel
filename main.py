import pyaudio
import wave
import os
import datetime
import speech_recognition as sr
from sms_alert import send_sms_alert
from email_alert import send_email_alert
from audio_evidence import record_evidence_audio
from location_utils import get_location_link
from app import make_call

# Constants
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
RECORD_SECONDS = 5
OUTPUT_DIR = "audio_clips"
SECRET_PHRASE = "help me lotus"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

def transcribe_audio(filename):
    """
    Transcribes the given audio file using Google Speech Recognition.
    """
    r = sr.Recognizer()
    with sr.AudioFile(filename) as source:
        audio_data = r.record(source)
        try:
            # Recognize speech using Google Speech Recognition
            text = r.recognize_google(audio_data)
            print(f"Transcription: \"{text}\"")
            return text.lower()
        except sr.UnknownValueError:
            print("Google Speech Recognition could not understand audio")
            return ""
        except sr.RequestError as e:
            print(f"Could not request results from Google Speech Recognition service; {e}")
            return ""

def record_audio():
    audio = pyaudio.PyAudio()

    try:
        stream = audio.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK)

        print("Listening... Press Ctrl+C to stop.")

        while True:
            frames = []
            try:
                # Read audio data, ignoring overflows
                for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    frames.append(data)
            except Exception as e:
                print(f"⚠️ Audio read error: {e}")
                continue  # Skip to the next recording cycle

            # Save the recorded data as a WAV file
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(OUTPUT_DIR, f"clip_{timestamp}.wav")
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(audio.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(b''.join(frames))

            print(f"Saved audio: {filename}")

            # Transcribe the audio and check for the secret phrase
            transcription = transcribe_audio(filename)
            if SECRET_PHRASE in transcription:
                print("✅ Secret phrase detected! Triggering alerts...")
                
                # Get location and trigger alerts
                location_link = get_location_link()
                send_sms_alert(location_link)
                send_email_alert(location_link)
                make_call()  # Make the emergency phone call
                record_evidence_audio()
            else:
                print("❌ No phrase detected.")

    except KeyboardInterrupt:
        print("\nStopped by user.")

    finally:
        # Safely close the stream and terminate PyAudio
        if 'stream' in locals() and stream.is_active():
            stream.stop_stream()
            stream.close()
        audio.terminate()

if __name__ == "__main__":
    record_audio() 