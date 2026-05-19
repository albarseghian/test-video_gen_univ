import os
import io
import time
from google import genai
from google.genai import types
from pydub import AudioSegment

# --- CONFIGURATION ---
API_KEY = "AIzaSyCcyvoPzNYuS2YamgpEtYsOf9YY8GMo3Hc"
MODEL_ID = "gemini-3.1-flash-tts-preview"
OUTPUT_DIR = "tests/voices"
TEST_TEXT = """
Մոդուլ 1: Ի՞նչ է շահերի բախումը։ Իրավիճակ, երբ կազմակերպության/իրավաբանական անձի կամ ֆիզիկական անձի անձնական, ընտանեկան, ընկերական, ֆինանսական և/կամ այլ շահերը և/կամ այլ նյութական/ոչ նյութական, սոցիալական կամ այլ գործոնները (ներառյալ, սակայն չսահմանափակվելով՝ ազգային, ռասայական, գենդերային, կրոնական պատկանելիությունը, քաղաքական հայացքները, դերն ու պաշտոնեական դիրքը, տեղեկացվածության և գիտելիքների մակարդակը, հարաբերությունները և այլ սոցիալական կապերը, հեղինակությունը ու գործարար համբավը) ազդում են կամ կարող են ազդեցություն ունենալ Բանկի շահերի  պաշտպանվածության, տվյալ անձանց կողմից իրենց օրենսդրական, պայմանագրային կամ աշխատանքային պարտավորությունների, պարտականությունների պատշաճ կատարման և/կամ այդ անձանց դատողության, դիրքորոշման, կայացրած որոշումների, վերաբերմունքի և/կամ գործողությունների, ներառյալ՝ դրանց անկողմնակալության, անկախության, ողջամտության, օբյեկտիվության և/կամ բանկի լավագույն շահերով առաջնորդվելու ունակության վրա։
"""

# The full list of 30 mythology/nature-inspired names for Gemini TTS
VOICES = [
    "Puck", "Charon", "Aoede", "Kore", "Fenrir",
    "Achernar", "Achird", "Algenib", "Algieba", "Alnilam",
    "Autonoe", "Callirrhoe", "Despina", "Enceladus", "Erinome",
    "Gacrux", "Iapetus", "Laomedeia", "Leda", "Orus",
    "Pulcherrima", "Rasalgethi", "Sadachbia", "Sadaltager", "Schedar",
    "Sulafat", "Umbriel", "Vindemiatrix", "Zephyr", "Zubenelgenubi"
]

MAX_RETRIES = 3
RETRY_DELAY = 5

def generate_voice_sample(client, voice_name):
    print(f"Processing voice: {voice_name}...")
    
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=TEST_TEXT,
                config=types.GenerateContentConfig(
                    response_modalities=['AUDIO'],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name
                            )
                        )
                    )
                )
            )

            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        pcm_data = part.inline_data.data
                        
                        import wave
                        pcm_path = os.path.join(OUTPUT_DIR, f"{voice_name}.pcm")
                        wav_path = os.path.join(OUTPUT_DIR, f"{voice_name}.wav")
                        mp3_path = os.path.join(OUTPUT_DIR, f"{voice_name}.mp3")

                        # 1. Save RAW PCM (Original data)
                        with open(pcm_path, 'wb') as f:
                            f.write(pcm_data)

                        # 2. Save WAV (Playable without ffmpeg)
                        try:
                            with wave.open(wav_path, 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2) # 16-bit
                                wf.setframerate(24000)
                                wf.writeframes(pcm_data)
                            print(f"  - Success: {voice_name} saved as WAV")
                        except Exception as wav_err:
                            print(f"  - Error saving WAV: {wav_err}")

                        # 3. Attempt Conversion to MP3 (Requires ffmpeg)
                        try:
                            audio = AudioSegment.from_raw(
                                io.BytesIO(pcm_data),
                                sample_width=2,
                                frame_rate=24000,
                                channels=1
                            )
                            audio.export(mp3_path, format="mp3")
                            print(f"  - Success: {voice_name} saved as MP3")
                        except Exception as conv_err:
                            print(f"  - Note: {voice_name} PCM was saved, but MP3 export failed (ffmpeg missing).")
                        
                        return True
            
            print(f"Error: No audio data returned for {voice_name}")
            return False

        except Exception as e:
            error_msg = str(e).lower()
            if "503" in error_msg or "overloaded" in error_msg or "deadline" in error_msg:
                print(f"  - Server busy (503/Timeout). Attempt {attempt+1}/{MAX_RETRIES}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            else:
                print(f"Error: API call failed for {voice_name}: {e}")
                return False
    
    print(f"Failed to generate {voice_name} after {MAX_RETRIES} attempts.")
    return False

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Directory created: {OUTPUT_DIR}")

    client = genai.Client(api_key=API_KEY)
    
    success_count = 0
    total_voices = len(VOICES)

    for i, voice in enumerate(VOICES):
        print(f"--- Processing {i+1}/{total_voices}: {voice} ---")
        if generate_voice_sample(client, voice):
            success_count += 1
        
        time.sleep(1)

    print(f"\nDone! Successfully generated {success_count} voices out of {total_voices}.")

if __name__ == "__main__":
    main()
