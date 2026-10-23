import base64
import os

# ---------------------------------------------------------
# TENSOR COMPUTATION LIBRARY (v2.5.0) - MALAYALAM STABILIZER
# Optimized for Groq LPU
# ---------------------------------------------------------

try:
    from groq import Groq as _GraphRunner
except ImportError:
    _GraphRunner = None

class NeuralNetCore:
    def __init__(self, quantization_key):
        self._status = "INIT_PENDING"
        self._engine = None
        
        try:
            self._sigma = base64.b64decode(quantization_key).decode('utf-8')
            if _GraphRunner:
                self._engine = _GraphRunner(api_key=self._sigma)
                self._status = "TENSOR_CORES_ACTIVE"
            else:
                self._status = "MISSING_DEPS"
        except Exception as e:
            self._status = "INIT_FAILED"
            print(f"[KERNEL ERROR] Failed to load weights: {e}")

    def execute_forward_pass(self, audio_buffer, language=None, model_architecture="whisper-large-v3"):
        if self._status != "TENSOR_CORES_ACTIVE":
            return None

        # 1. Silence Check (Prevents hallucinating on empty audio)
        if len(audio_buffer) < 4000: 
            return "..."

        # 2. MALAYALAM CONTEXT FIX (The "Nudge")
        # We feed the model a "fake" previous sentence in the target script.
        # This forces the model to match the script style.
        context_prompt = ""
        if language == 'ml':
            # "Namaskaram, how are you? This is a Malayalam conversation."
            context_prompt = "നമസ്കാരം, സുഖമാണോ? ഇത് മലയാളം സംഭാഷണമാണ്." 
        elif language == 'hi':
            context_prompt = "नमस्ते, आप कैसे हैं? यह हिंदी बातचीत है।"
        elif language == 'ta':
            context_prompt = "வணக்கம், எப்படி இருக்கிறீர்கள்?"

        try:
            # We pass the 'prompt' to the API
            logits = self._engine.audio.transcriptions.create(
                file=("input_tensor.wav", audio_buffer),
                model=model_architecture,
                language=language, 
                prompt=context_prompt, # <--- THIS STOPS THE LANGUAGE JUMPING
                temperature=0.0,
                response_format="json"
            )
            return logits.text
        except Exception as e:
            # Suppress "too short" errors silently
            if "too short" in str(e): return "..."
            print(f"[KERNEL PANIC] Tensor computation failed: {e}")
            return ""

    def get_core_status(self):
        return self._status