import os
import time
import PIL.Image
from google import genai
from google.genai import types

# --- Կարգավորումներ ---
API_KEY = "AIzaSyCcyvoPzNYuS2YamgpEtYsOf9YY8GMo3Hc"
MODEL_ID = "veo-3.1-generate-preview" 
# Ընտրեք որևէ նկար ձեր վերջին սեսիայից (օրինակ՝ slide_1_beautified.png)
# Եթե չկա, փոխարինեք գոյություն ունեցող նկարի ուղիով
INPUT_IMAGE_PATH = r"c:\Users\Narek Alatuzyan\Desktop\test1.png" 
OUTPUT_VIDEO_PATH = "tests/veo_animated_slide.mp4"
PROMPT = "Maintain the exact Armenian text and layout of this slide perfectly. Do not change any letters or characters. Add only a subtle, professional background animation: a soft light sweep across the page and a gentle floating motion of the background elements, while keeping all text 100% static and legible."

def test_veo_animation():
    print(f"🚀 Սկսվում է Veo թեստը ({MODEL_ID})...")
    
    if not os.path.exists(INPUT_IMAGE_PATH):
        print(f"❌ Սխալ: Մուտքային նկարը չգտնվեց՝ {INPUT_IMAGE_PATH}")
        print("Խնդրում եմ տեղադրել որևէ նկար այդ ուղիով կամ փոխել INPUT_IMAGE_PATH-ը:")
        return

    client = genai.Client(api_key=API_KEY)
    
    try:
        print(f"🖼️ Բեռնվում է նկարը ({INPUT_IMAGE_PATH})...")
        # Օգտագործում ենք պաշտոնական Image.from_file մեթոդը
        image_input = types.Image.from_file(location=INPUT_IMAGE_PATH)

        print(f"📤 Հարցում է ուղարկվում Veo 3.1-ին...")
        # Կանչում ենք վիդեո գեներացիայի գործողությունը
        operation = client.models.generate_videos(
            model=MODEL_ID,
            prompt=PROMPT,
            image=image_input,
            config=types.GenerateVideosConfig(
                aspect_ratio="16:9",
                # duration_seconds=10  # Կարող եք դնել 5 կամ 10
            )
        )

        print(f"⏳ Գործողությունը սկսված է (ID: {operation.name}):")
        print("Վիդեոյի գեներացումը կարող է տևել 2-5 րոպե: Խնդրում ենք սպասել...")

        # Պարբերաբար ստուգում ենք կարգավիճակը (Polling)
        while not operation.done:
            print("... դեռ մշակվում է ...")
            time.sleep(30) # Սպասում ենք 30 վայրկյան հաջորդ ստուգումից առաջ
            operation = client.operations.get(operation)

        # Երբ ավարտվի, պահպանում ենք արդյունքը
        if operation.response and operation.response.generated_videos:
            generated_video = operation.response.generated_videos[0]
            # 1. Նախ ներբեռնում ենք ֆայլը սերվերից
            client.files.download(file=generated_video.video)
            # 2. Հետո պահպանում ենք տեղում
            generated_video.video.save(OUTPUT_VIDEO_PATH)
            print(f"✅ ՀԱՋՈՂՈՒԹՅՈՒՆ! Անիմացված վիդեոն պահպանվեց՝ {OUTPUT_VIDEO_PATH}")
        else:
            print("❌ Սխալ: Վիդեո տվյալներ չստացվեցին:")

    except Exception as e:
        print(f"❌ Կրիտիկական սխալ Veo թեստի ժամանակ: {e}")

if __name__ == "__main__":
    test_veo_animation()
