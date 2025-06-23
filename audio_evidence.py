import pyaudio
import wave
import os
import datetime
import threading

# Constants for audio recording
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
EVIDENCE_SECONDS = 600  # 10 minutes
EVIDENCE_DIR = "evidence"

def _record_and_save():
    """
    Internal function to handle the actual recording and file saving.
    This runs in a separate thread.
    """
    audio = pyaudio.PyAudio()

    try:
        # Open microphone stream
        stream = audio.open(format=FORMAT, channels=CHANNELS,
                            rate=RATE, input=True,
                            frames_per_buffer=CHUNK)
        
        frames = []
        
        # Record for the specified duration
        for _ in range(0, int(RATE / CHUNK * EVIDENCE_SECONDS)):
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)

        # Stop and close the stream
        stream.stop_stream()
        stream.close()
        audio.terminate()

        # Create the evidence directory if it doesn't exist
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        
        # Generate a timestamped filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(EVIDENCE_DIR, f"evidence_{timestamp}.wav")

        # Save the recorded data as a WAV file
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(pyaudio.PyAudio().get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
        
        print(f"🎙️ Evidence audio recorded: {filename}")

    except Exception as e:
        print(f"❌ Failed to record evidence audio: {e}")

def record_evidence_audio():
    """
    Starts the audio evidence recording in a non-blocking thread.
    """
    print("🎙️ Starting evidence recording...")
    thread = threading.Thread(target=_record_and_save)
    thread.daemon = True  # Allows main program to exit even if thread is running
    thread.start()

if __name__ == '__main__':
    # This block allows you to test the evidence recording directly
    record_evidence_audio()
    print("Main program continues while recording happens in the background.")
    # In a real scenario, the main program would continue its tasks.
    # Here, we'll just wait for the recording to likely finish.
    threading.Event().wait(EVIDENCE_SECONDS + 2)
    print("Test finished.") 