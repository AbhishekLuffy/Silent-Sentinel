import sys
import wave
import pyaudio
import os

def play_audio(filename):
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return
    try:
        wf = wave.open(filename, 'rb')
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pa.get_format_from_width(wf.getsampwidth()),
                         channels=wf.getnchannels(),
                         rate=wf.getframerate(),
                         output=True)
        print(f"▶️ Playing: {filename}")
        chunk = 1024
        data = wf.readframes(chunk)
        while data:
            stream.write(data)
            data = wf.readframes(chunk)
        stream.stop_stream()
        stream.close()
        pa.terminate()
        wf.close()
        print("✅ Playback finished.")
    except Exception as e:
        print(f"❌ Error playing audio: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        filename = input("Enter audio filename (e.g., audio_clips/clip_YYYYMMDD_HHMMSS.wav): ")
    play_audio(filename) 