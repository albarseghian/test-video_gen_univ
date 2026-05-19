import os
import io
from google import genai
from google.genai import types
from pydub import AudioSegment

# --- Կարգավորումներ ---
# Օգտագործում ենք ձեր գործող API Key-ը
API_KEY = "AIzaSyCcyvoPzNYuS2YamgpEtYsOf9YY8GMo3Hc"
MODEL_ID = "gemini-3.1-flash-tts-preview"
VOICE_NAME = "Puck"
OUTPUT_FILE = "tests/test_gemini_3_1_audio.pcm"
TEST_TEXT = """
Լեռների գագաթներին դեռ ձյուն կար, բայց ստորոտում արդեն գարունը լիովին զգացվում էր։ Ծառերը ծաղկել էին, և օդում թարմության հոտ էր տարածված։ Գյուղի փոքր ճանապարհով մի ծեր մարդ քայլում էր՝ ձեռքին փայտյա գավազան, իսկ հեռվում երեխաների ծիծաղն էր լսվում, որոնք խաղում էին դաշտում։
"""
def test_tts():
    print(f"Սկսվում է թեստը {MODEL_ID} մոդելի հետ...")
    client = genai.Client(api_key=API_KEY)
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=TEST_TEXT,
            config=types.GenerateContentConfig(
                response_modalities=['AUDIO'],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=VOICE_NAME
                        )
                    )
                )
            )
        )

        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    data = part.inline_data.data
                    mime_type = getattr(part.inline_data, 'mime_type', '').lower()
                    print(f"📡 Մոդելը վերադարձրեց ձայն հետևյալ ֆորմատով՝ {mime_type}")

                    # Պահպանում ենք RAW բայթերը ուղղակի (առանց pydub-ի՝ ffmpeg սխալից խուսափելու համար)
                    with open(OUTPUT_FILE, 'wb') as f:
                        f.write(data)
                    
                    print(f"✅ Հաջողություն: Ձայնագրությունը պահպանվեց '{OUTPUT_FILE}' անվամբ (Raw PCM):")
                    return
        
        print("❌ Սխալ: Ձայնային տվյալներ չգտնվեցին պատասխանի մեջ:")
        
    except Exception as e:
        print(f"❌ Կրիտիկական սխալ թեստի ժամանակ: {e}")

if __name__ == "__main__":
    test_tts()
