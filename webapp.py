import os
import time
import requests
from flask import Flask, render_template, request, jsonify
import ai_engine # Your stealth tensor engine

app = Flask(__name__)

# Global Walkie-Talkie State
CALL_STATE = {
    "phone1": {"lang": "en", "voice_id": None},
    "phone2": {"lang": "ml", "voice_id": None},
    "message_queue": [] # Holds translated audio ready to be played
}

ELEVENLABS_API_KEY = ""

# --- ELEVENLABS HELPER FUNCTIONS ---
def clone_voice(audio_path, name):
    url = "https://api.elevenlabs.io/v1/voices/add"
    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    with open(audio_path, 'rb') as f:
        files = {'files': (audio_path, f, 'audio/wav')}
        data = {'name': f"WebClone_{name}", 'description': "WalkieTalkie clone"}
        response = requests.post(url, headers=headers, data=data, files=files)
    if response.status_code == 200:
        return response.json().get('voice_id')
    return None

def generate_voice(text, voice_id, target_lang, output_path):
    if target_lang == 'ml':
        text = ai_engine.text_to_manglish(text)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    data = {"text": text, "model_id": "eleven_multilingual_v2"}
    response = requests.post(url, json=data, headers=headers)
    with open(output_path, 'wb') as f:
        f.write(response.content)

# --- ROUTES ---
@app.route("/")
def index():
    return render_template("walkie.html")

@app.route("/api/setup", methods=["POST"])
def setup_user():
    """Receives the initial signup voice sample and clones it."""
    phone_id = request.form.get("phone_id") # 'phone1' or 'phone2'
    lang = request.form.get("lang")
    audio = request.files.get("audio")
    
    temp_path = f"temp_setup_{phone_id}.wav"
    audio.save(temp_path)
    
    # Clone Voice
    voice_id = clone_voice(temp_path, phone_id)
    CALL_STATE[phone_id]["lang"] = lang
    CALL_STATE[phone_id]["voice_id"] = voice_id
    
    return jsonify({"status": "success", "voice_id": voice_id})

@app.route("/api/transmit", methods=["POST"])
def transmit_audio():
    """Handles the Walkie-Talkie Push-to-Talk action."""
    sender_id = request.form.get("phone_id")
    receiver_id = "phone2" if sender_id == "phone1" else "phone1"
    
    sender_lang = CALL_STATE[sender_id]["lang"]
    receiver_lang = CALL_STATE[receiver_id]["lang"]
    sender_voice_id = CALL_STATE[sender_id]["voice_id"]
    
    audio = request.files.get("audio")
    in_path = f"in_{sender_id}.wav"
    audio.save(in_path)
    
    # 1. Transcribe & Translate via AI Engine
    original_text = ai_engine.transcribe_audio(in_path, language=sender_lang)
    
    if sender_lang == 'ml' and ai_engine.is_english_text(original_text):
        original_text = ai_engine.manglish_to_malayalam(original_text)
        
    translated_text = ai_engine.translate_text(original_text, sender_lang, receiver_lang)
    
    # 2. Synthesize using the SENDER'S cloned voice
    out_filename = f"out_{int(time.time())}.wav"
    out_path = os.path.join("static", out_filename)
    
    if sender_voice_id and translated_text.strip():
        generate_voice(translated_text, sender_voice_id, receiver_lang, out_path)
        
        # 3. Add to the queue for the receiver to pick up
        CALL_STATE["message_queue"].append({
            "target": receiver_id,
            "audio_url": f"/static/{out_filename}",
            "text": translated_text
        })
        
    return jsonify({"status": "transmitted"})

@app.route("/api/poll", methods=["GET"])
def poll_messages():
    """Phones constantly ping this to see if someone spoke to them."""
    phone_id = request.args.get("phone_id")
    messages = [m for m in CALL_STATE["message_queue"] if m["target"] == phone_id]
    
    # Remove fetched messages from the queue
    CALL_STATE["message_queue"] = [m for m in CALL_STATE["message_queue"] if m["target"] != phone_id]
    
    return jsonify({"messages": messages})

if __name__ == "__main__":
    os.makedirs("static", exist_ok=True)
    app.run(host="0.0.0.0", port=5000, threaded=True)