import sqlite3
import os
import requests
import time
from flask import Flask, render_template, request, jsonify, g
import ai_engine  # Import our AI Brain

# --- CONFIGURATION ---
ELEVENLABS_API_KEY = ""  # 🔴 PASTE KEY HERE

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(APP_ROOT, 'database.db')
UPLOAD_FOLDER = os.path.join(APP_ROOT, 'static', 'uploads')
OUTPUT_FOLDER = os.path.join(APP_ROOT, 'static', 'output')

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# --- DATABASE HELPERS ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None: db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS voice_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, voice_id_elevenlabs TEXT, sample_file_path TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id))''')
        db.commit()

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/voice-lab')
def voice_lab():
    cur = get_db().cursor()
    cur.execute("SELECT users.name, voice_profiles.voice_id_elevenlabs FROM users JOIN voice_profiles ON users.id = voice_profiles.user_id")
    users = cur.fetchall()
    return render_template('voice_lab.html', users=users)

@app.route('/add-voice', methods=['POST'])
def add_voice():
    try:
        name = request.form['name']
        file = request.files['file']
        filename = f"{name}_sample.webm"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        url = "https://api.elevenlabs.io/v1/voices/add"
        headers = {"xi-api-key": ELEVENLABS_API_KEY}
        files = {'files': (filename, open(filepath, 'rb'), 'audio/webm')}
        data = {'name': name, 'description': f"Voice clone for {name}"}

        response = requests.post(url, headers=headers, data=data, files=files)
        
        if response.status_code != 200:
            return jsonify({"status": "error", "message": response.text})

        voice_id = response.json().get('voice_id')
        
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("INSERT INTO users (name) VALUES (?)", (name,))
            user_id = cur.lastrowid
        except:
            cur.execute("SELECT id FROM users WHERE name = ?", (name,))
            user_id = cur.fetchone()['id']

        cur.execute("INSERT INTO voice_profiles (user_id, voice_id_elevenlabs, sample_file_path) VALUES (?, ?, ?)",
                    (user_id, voice_id, filepath))
        db.commit()

        return jsonify({"status": "success", "voice_id": voice_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/start-session')
def start_session():
    cur = get_db().cursor()
    cur.execute("SELECT users.name, voice_profiles.voice_id_elevenlabs FROM users JOIN voice_profiles ON users.id = voice_profiles.user_id")
    users = cur.fetchall()
    return render_template('session.html', users=users)

# --- UPDATED CONVERSATION LOGIC ---
@app.route('/process-conversation', methods=['POST'])
def process_conversation():
    try:
        file = request.files['file']
        speaker_name = request.form['speaker_name']
        source_lang = request.form['source_lang']
        target_lang = request.form['target_lang']
        voice_id = request.form['voice_id']

        # 1. Save Input Audio
        timestamp = int(time.time())
        filename = f"input_{timestamp}.webm"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # 2. Transcribe (Ear) - UPDATED TO FORCE LANGUAGE
        print(f"👂 Listening to {speaker_name} ({source_lang})...")
        
        original_text = ai_engine.transcribe_audio(filepath, language=source_lang)
        print(f"📝 Original Recognition: {original_text}")

        # --- 🔴 MANGLISH INPUT FIX ---
        # If user said they are speaking Malayalam, but Whisper gave us English letters...
        if source_lang == 'ml' and ai_engine.is_english_text(original_text):
            print(f"⚠️ Detected Manglish input ('{original_text}'). Converting to Script...")
            original_text = ai_engine.manglish_to_malayalam(original_text)
            print(f"🔄 Converted to Script: {original_text}")
        # -----------------------------

        # 3. Translate (Brain)
        print(f"🧠 Translating {source_lang} -> {target_lang}...")
        translated_text = ai_engine.translate_text(original_text, source_lang, target_lang)
        print(f"🈯 Translated: {translated_text}")

        # 4. Prepare Speech Text (Manglish Output Logic Check)
        final_speech_text = translated_text
        
        if target_lang == 'ml':
            print("🔄 Target is Malayalam: Converting to Manglish for TTS...")
            final_speech_text = ai_engine.text_to_manglish(translated_text)
        else:
            print(f"✅ Target is {target_lang}: Supported natively by ElevenLabs.")

        # 5. Speak (The Mouth)
        print(f"👄 Speaking as {speaker_name}...")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "text": final_speech_text,
            "model_id": "eleven_multilingual_v2", 
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
        }
        
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            output_filename = f"output_{timestamp}.mp3"
            output_path = os.path.join(OUTPUT_FOLDER, output_filename)
            with open(output_path, 'wb') as f:
                f.write(response.content)

            return jsonify({
                "status": "success",
                "original_text": original_text,
                "translated_text": translated_text, 
                "audio_url": f"/static/output/{output_filename}"
            })
        else:
            return jsonify({"status": "error", "message": "ElevenLabs Error: " + response.text})

    except Exception as e:
        print(e)
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)