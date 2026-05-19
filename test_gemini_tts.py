from google import genai
from google.genai import types
import time
import random
import logging
import os

# Set up logging to match app.py behavior
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
api_key = "AIzaSyCcyvoPzNYuS2YamgpEtYsOf9YY8GMo3Hc"
client = genai.Client(api_key=api_key)

# --- COPY OF gemini_safe_call FROM app.py ---
def gemini_safe_call(model, contents, config=None, retries=10, delay=2):
    for attempt in range(retries):
        try:
            if config:
                response = client.models.generate_content(model=model, contents=contents, config=config)
            else:
                response = client.models.generate_content(model=model, contents=contents)
            
            if not response.candidates or not response.candidates[0].content:
                finish_reason = getattr(response.candidates[0], 'finish_reason', 'UNKNOWN') if response.candidates else 'NO_CANDIDATES'
                raise RuntimeError(f"Gemini returned empty/blocked response. Reason: {finish_reason}")
                
            return response
        except Exception as e:
            err_msg = str(e).upper()
            if "400" in err_msg or "401" in err_msg or "403" in err_msg:
                logger.error(f"Կրիտիկական API սխալ: {e}.")
                raise e

            logger.warning(f"Gemini API attempt {attempt + 1}/{retries} failed for {model}: {e}")
            if attempt < retries - 1:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                logger.info(f"Սպասում ենք {wait_time:.2f} վայրկյան...")
                time.sleep(wait_time)
    
    raise RuntimeError(f"Gemini API-ն վերջնական ձախողվեց {retries} փորձից հետո ({model})")

# --- TEST DATA ---
vo_text = "Արևը դանդաղ մայր էր մտնում լեռների հետևում, և քաղաքը լցվում էր մեղմ ոսկեգույն լույսով։ Փողոցներում մարդիկ քայլում էին հանգիստ, ոմանք զրուցելով, մյուսները՝ իրենց մտքերի մեջ կորած։"
vo_label = "VO_TEST"
tests_folder = "c:/Users/Narek Alatuzyan/Desktop/video_gen_project/tests"
os.makedirs(tests_folder, exist_ok=True)

print(f"\n=== STARTING TTS API TEST (EXACT app.py LOGIC) ===")
print(f"Target Text: {vo_text}\n")

try:
    # --- EXACT TTS BLOCK FROM app.py ---
    response = gemini_safe_call(
        model='gemini-2.5-pro-preview-tts',
        contents=vo_text,
        config=types.GenerateContentConfig(
            response_modalities=['AUDIO'],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name='Puck'
                    )
                )
            )
        )
    )

    audio_saved = False
    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                mime_type = getattr(part.inline_data, 'mime_type', '').lower()
                print(f"--- [INFO] Model returned MIME Type: {mime_type} ---")
                
                # Check format
                ext = ".mp3"
                if "wav" in mime_type:
                    ext = ".wav"
                elif "ogg" in mime_type:
                    ext = ".ogg"
                elif "webm" in mime_type:
                    ext = ".webm"
                elif "mp3" in mime_type or "mpeg" in mime_type:
                    ext = ".mp3"
                elif "pcm" in mime_type or "l16" in mime_type:
                    ext = ".pcm"
                else:
                    raise RuntimeError(f"Unknown audio mime type: {mime_type}")
                
                audio_filename = f"test_audio3_{vo_label}{ext}"
                audio_path = os.path.join(tests_folder, audio_filename)
                
                print(f"--- [INFO] Saving file as: {audio_filename} (Size: {len(part.inline_data.data)} bytes) ---")
                
                with open(audio_path, 'wb') as f:
                    f.write(part.inline_data.data)
                
                if os.path.getsize(audio_path) < 1000:
                    raise RuntimeError(f"Audio file too small / corrupted: {vo_label}")
                
                audio_saved = True
                print(f"\n--- [SUCCESS] File saved at: {audio_path} ---")
                break
    
    if not audio_saved:
        print("\n--- [FAILED] No audio data found in candidates ---")

except Exception as final_err:
    print(f"\n--- [FAILED] CRITICAL ERROR: {final_err} ---")
