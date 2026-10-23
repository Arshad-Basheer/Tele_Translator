import warnings
warnings.filterwarnings("ignore")

import subprocess
import time
import os
import sys
import math
import struct
from contextlib import contextmanager
import requests
import wave
import ai_engine  

# =======================================================================
# 🎛️ SYSTEM HARDWARE CONFIGURATION
# =======================================================================
PHONE_MIC_IN_DEVICE = 7  
PI_MIC_IN_DEVICE = 0     
PHONE_AUX_OUT_DEVICE = 7 
PI_SPEAKER_DEVICE = 0    

ELEVENLABS_API_KEY = ""

# =======================================================================
# 📡 DYNAMIC BLUETOOTH TRACKERS (UPDATED FOR PIPEWIRE)
# =======================================================================
def get_bluetooth_source():
    """Finds the active Bluetooth microphone stream from the phone call."""
    try:
        out = subprocess.check_output("pactl list short sources", shell=True).decode()
        for line in out.splitlines():
            if "bluez_source" in line or "bluez_input" in line:
                return line.split()[1]
    except Exception:
        pass
    return None

def get_bluetooth_sink():
    """Finds the active Bluetooth speaker stream to inject audio into the phone call."""
    try:
        out = subprocess.check_output("pactl list short sinks", shell=True).decode()
        for line in out.splitlines():
            if "bluez_sink" in line or "bluez_output" in line:
                return line.split()[1]
    except Exception:
        pass
    return None

# =======================================================================
# 🔊 AUDIO ROUTING CONTROLLERS
# =======================================================================
def create_beep_file(filename="beep.wav"):
    """Generates a perfect 0.3s digital beep using pure Python."""
    if not os.path.exists(filename):
        sample_rate, duration, frequency = 16000, 0.3, 800.0
        with wave.open(filename, 'w') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sample_rate)
            for i in range(int(sample_rate * duration)):
                value = int(32767.0 * math.sin(frequency * math.pi * 2 * i / sample_rate))
                f.writeframes(struct.pack('<h', value))

def play_beep():
    """Plays an alert tone through the active pulse stream."""
    os.system("aplay -D pulse beep.wav >/dev/null 2>&1") 
    time.sleep(0.3)

def record_audio(device_id, duration, filename="temp_input.wav"):
    """Records audio strictly from the designated source."""
    if device_id == 7:
        print(f"   [🎙️] Listening to Phone Call for {duration} seconds...")
        bt_source = get_bluetooth_source()
        source = bt_source if bt_source else "default"
        os.system(f"timeout {duration} parecord --device={source} --rate=16000 --channels=1 --file-format=wav {filename} >/dev/null 2>&1")
    else:
        print(f"   [🎙️] Listening to Local Room for {duration} seconds... (Speak Now)")
        cmd = [
            "arecord", "-D", "pulse", "-c", "1", "-r", "16000",
            "-f", "S16_LE", "-d", str(duration), "-q", filename
        ]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            pass 
            
    if not os.path.exists(filename) or os.path.getsize(filename) < 100:
        wf = wave.open(filename, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b'\x00' * (16000 * 2 * duration))
        wf.close()
        
    print("   [⏹️] Recording Captured.")
    return filename

def play_audio_to_device(filename, device_id):
    """Plays the translated WAV safely to the strictly designated output."""
    if device_id == 7:
        print(f"   [🔊] Injecting translated audio into Cellular Call...")
        bt_sink = get_bluetooth_sink()
        if bt_sink:
            os.system(f"paplay --device={bt_sink} {filename} >/dev/null 2>&1")
        else:
            print("   [⚠️] Bluetooth Sink not found! Falling back to local speaker.")
            os.system(f"paplay {filename} >/dev/null 2>&1")
    else:
        print(f"   [🔊] Playing translated audio to Local Speaker...")
        os.system(f"paplay {filename} >/dev/null 2>&1")

# =======================================================================
# 🧠 AI & VOICE CLONING (ELEVENLABS)
# =======================================================================
def clone_voice(audio_filepath, speaker_name):
    print(f"   [☁️ ] Extracting vocal signature for '{speaker_name}'...")
    url = "https://api.elevenlabs.io/v1/voices/add"
    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    with open(audio_filepath, 'rb') as f:
        files = {'files': (audio_filepath, f, 'audio/wav')}
        data = {'name': f"LiveCall_{speaker_name}", 'description': "On-the-fly hardware clone"}
        response = requests.post(url, headers=headers, data=data, files=files)
        
    if response.status_code == 200:
        v_id = response.json().get('voice_id')
        print(f"   [✅] Voice Cloned! (ID: {v_id})")
        return v_id
    else:
        print(f"   [❌] ElevenLabs Error: {response.text}")
        return None

def generate_voice(text, voice_id, target_lang):
    print("   [👄] Synthesizing translated speech...")
    if target_lang == 'ml':
        speech_text = ai_engine.text_to_manglish(text)
    else:
        speech_text = text

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    data = {
        "text": speech_text, 
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
    }
    response = requests.post(url, json=data, headers=headers)
    
    mp3_file = "temp_output.mp3"
    with open(mp3_file, 'wb') as f:
        f.write(response.content)
        
    wav_file = "temp_output.wav"
    # 🔴 FIX: Cranked volume up to 8.0 to fix the quiet remote caller
    os.system(f"ffmpeg -y -i {mp3_file} -filter:a 'volume=8.0' -ar 16000 -ac 1 {wav_file} >/dev/null 2>&1")
    
    return wav_file

# =======================================================================
# 🔄 THE MAIN CALL LOOP
# =======================================================================
def run_translation_call(phone1_lang, phone2_lang):
    print("\n" + "="*50)
    print(" 📞 LIVE CALL CONNECTED | TRANSLATOR ENGAGED")
    print("="*50)
    
    p1_voice_id = None
    p2_voice_id = None
    
    while True:
        try:
            # ---------------------------------------------------------
            # TURN 1: REMOTE CALLER (PHONE 2 via Bluetooth)
            # ---------------------------------------------------------
            print(f"\n📱 REMOTE CALLER TURN ({phone2_lang.upper()} -> {phone1_lang.upper()})")
            print("-" * 50)
            
            # 🔴 FIX: Added beep for the remote caller too!
            play_beep()
            
            # 🔴 FIX: 10s for the first turn, 7s for the rest!
            p2_dur = 10 if p2_voice_id is None else 7
            audio_in = record_audio(PHONE_MIC_IN_DEVICE, duration=p2_dur, filename="p2_input.wav") 
            print("   [🧠] Processing Audio Tensor...")
            original_text = ai_engine.transcribe_audio(audio_in, language=phone2_lang)
            
            if "விரும்புகிறீர்கள்" in original_text or original_text.strip() == "...":
                print("   [⚠️] Silence detected, skipping AI processing.")
            else:
                if phone2_lang == 'ml' and ai_engine.is_english_text(original_text):
                    original_text = ai_engine.manglish_to_malayalam(original_text)
                    
                translated = ai_engine.translate_text(original_text, phone2_lang, phone1_lang)
                print(f"   [📝] Recognized: '{original_text}'")
                print(f"   [🌐] Translated: '{translated}'")
                
                if p2_voice_id is None and len(original_text) > 2: 
                    p2_voice_id = clone_voice(audio_in, "Remote_Caller")
                
                if p2_voice_id and translated.strip() and translated != "...":
                    audio_out = generate_voice(translated, p2_voice_id, phone1_lang)
                    play_audio_to_device(audio_out, PI_SPEAKER_DEVICE)

            print("\n   [⏳] Waiting 2 seconds for smooth transition...")
            time.sleep(2)

            # ---------------------------------------------------------
            # TURN 2: LOCAL USER (PHONE 1 via I2S Mic)
            # ---------------------------------------------------------
            print(f"\n🎤 LOCAL USER TURN ({phone1_lang.upper()} -> {phone2_lang.upper()})")
            print("-" * 50)
            play_beep() 
            
            # 🔴 FIX: 10s for the first turn, 7s for the rest!
            p1_dur = 10 if p1_voice_id is None else 7
            audio_in = record_audio(PI_MIC_IN_DEVICE, duration=p1_dur, filename="p1_input.wav")
            print("   [🧠] Processing Audio Tensor...")
            original_text = ai_engine.transcribe_audio(audio_in, language=phone1_lang)
            
            if "You want it" in original_text or original_text.strip() == "...":
                print("   [⚠️] Silence detected, skipping AI processing.")
            else:
                if phone1_lang == 'ml' and ai_engine.is_english_text(original_text):
                    original_text = ai_engine.manglish_to_malayalam(original_text)
                    
                translated = ai_engine.translate_text(original_text, phone1_lang, phone2_lang)
                print(f"   [📝] Recognized: '{original_text}'")
                print(f"   [🌐] Translated: '{translated}'")
                
                if p1_voice_id is None and len(original_text) > 2: 
                    p1_voice_id = clone_voice(audio_in, "Local_User")
                
                if p1_voice_id and translated.strip() and translated != "...":
                    audio_out = generate_voice(translated, p1_voice_id, phone2_lang)
                    play_audio_to_device(audio_out, PHONE_AUX_OUT_DEVICE)

            print("\n   [⏳] Waiting 2 seconds for smooth transition...")
            time.sleep(2)

        except KeyboardInterrupt:
            print("\n\n🛑 Hardware Loop Terminated by User. Disengaging...")
            break

# =======================================================================
# 🚀 SYSTEM BOOT
# =======================================================================
if __name__ == "__main__":
    os.system('clear') 
    create_beep_file() # Ensure the beep file exists on startup!
    print("========================================")
    print(" 🌍 AI SMART HARDWARE BOOT SEQUENCE ")
    print("========================================")
    print("\nAvailable Languages: en (English), ml (Malayalam), hi (Hindi), ta (Tamil)")
    
    p1_lang = input("Enter Language Code for Phone 1 (Local User/Mic): ").strip().lower()
    p2_lang = input("Enter Language Code for Phone 2 (Remote Caller/Bluetooth): ").strip().lower()
    
    if p1_lang not in ['en', 'ml', 'hi', 'ta']: p1_lang = 'en'
    if p2_lang not in ['en', 'ml', 'hi', 'ta']: p2_lang = 'ml'
    
    print(f"\n✅ Configuration Locked: [Local: {p1_lang.upper()}] | [Remote: {p2_lang.upper()}]")
    run_translation_call(phone1_lang=p1_lang, phone2_lang=p2_lang)