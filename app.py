from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import docx
import re
import os
import uuid
import json
import shutil
import time
import logging
import random
from google import genai
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
from google.genai import types
from dotenv import load_dotenv
from pydub import AudioSegment
import PIL.Image
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
import subprocess
from pptx import Presentation
from pdf2image import convert_from_path

# --- Avatar LipSync Integration ---
try:
    from lipsync import LipSync
    LIP_SYNC_AVAILABLE = True
except ImportError:
    LIP_SYNC_AVAILABLE = False
    logger.warning("lipsync library not found. Talking head feature will be disabled.")

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
CORS(app)  # Թույլատրում ենք հարցումները ֆրոնտենդից
 
# Գլոբալ փոփոխական՝ կանգնեցված պրոցեսները հետևելու համար
STOP_SIGNALS = set()

# Կարգավորում ենք Gemini API-ն՝ օգտագործելով միջավայրի փոփոխականները
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# GEMINI_API_KEY = "API_KEY_for_test"
if not GEMINI_API_KEY:
    raise RuntimeError("Կրիտիկական սխալ: GEMINI_API_KEY միջավայրի փոփոխականը սահմանված չէ:")

client = genai.Client(api_key=GEMINI_API_KEY)

def gemini_safe_call(model, contents, config=None, retries=10, delay=2):
    for attempt in range(retries):
        try:
            if config:
                response = client.models.generate_content(model=model, contents=contents, config=config)
            else:
                response = client.models.generate_content(model=model, contents=contents)
            
            # Հատուկ ստուգում Safety Block-ի համար
            if response.candidates:
                candidate = response.candidates[0]
                if candidate.finish_reason == 'SAFETY':
                    logger.error(f"Safety Block - Content was blocked by Gemini: {model}")
                    raise RuntimeError(f"ԿՈՆՏԵՆՏԻ ԱՐԳԵԼԱՓԱԿՈՒՄ (Safety): Gemini-ն համարում է այս պրոմպտը անթույլատրելի:")
                
                if not candidate.content:
                    raise RuntimeError(f"Gemini-ն վերադարձրեց դատարկ պատասխան (Reason: {candidate.finish_reason})")
            else:
                raise RuntimeError("Gemini Response-ում թեկնածուներ (candidates) չկան:")
                
            return response
        except Exception as e:
            err_msg = str(e).upper()
            
            # Եթե կա "Hard" սխալ, չենք շարունակում (400=Bad Request, 401/403=Auth, 404=Not Found, SAFETY=Blocked)
            if "400" in err_msg or "401" in err_msg or "403" in err_msg or "404" in err_msg or "SAFETY" in err_msg:
                logger.error(f"Կրիտիկական/Մշտական սխալ: {e}. Փորձերը դադարեցվում են:")
                raise e

            logger.warning(f"Gemini API attempt {attempt + 1}/{retries} failed for {model}: {e}")
            if attempt < retries - 1:
                # Exponential backoff with jitter
                # Higher attempts will wait longer (up to 2^9 = 512 seconds)
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                logger.info(f"Սպասում ենք {wait_time:.2f} վայրկյան...")
                time.sleep(wait_time)
    
    raise RuntimeError(f"Gemini API-ն վերջնական ձախողվեց {retries} փորձից հետո ({model})")

# Կատարում ենք առաջին "warm-up" զանգը ապագա տապալումները բացառելու համար
# try:
#     if gemini_safe_call("gemini-3.1-pro-preview", "Hello"):
#         logger.info("Gemini API warmup successful.")
# except Exception as e:
#     logger.warning(f"Warmup failed: {e}. Moving on.")

# Սահմանում ենք թղթապանակը վերբեռնված ֆայլերի համար
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def home():
    return send_from_directory('.', 'front.html')

def cleanup_old_sessions():
    now = time.time()
    if os.path.exists(UPLOAD_FOLDER):
        for folder_name in os.listdir(UPLOAD_FOLDER):
            folder_path = os.path.join(UPLOAD_FOLDER, folder_name)
            if os.path.isdir(folder_path) and os.stat(folder_path).st_mtime < now - 3600:
                try:
                    shutil.rmtree(folder_path)
                    logger.info(f"Cleaned up stale session: {folder_name}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {folder_name}: {e}")

def cleanup_loop():
    """Background loop to clean up old sessions every hour."""
    while True:
        try:
            cleanup_old_sessions()
        except Exception as e:
            logger.error(f"Cleanup loop encountered an error: {e}")
        time.sleep(3600)  # Wait for 1 hour

# Start the cleanup thread once on app startup
cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
cleanup_thread.start()

def update_progress(session_id, percent, message="", result=None, status="processing"):
    try:
        progress_file = os.path.join(UPLOAD_FOLDER, session_id, 'progress.json')
        if os.path.exists(os.path.dirname(progress_file)):
            data = {
                'percent': min(int(percent), 100), 
                'status': status,
                'message': message
            }
            if result is not None:
                data['result'] = result
            
            # Atomic write to prevent race conditions during frontend polling
            temp_file = progress_file + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(temp_file, progress_file)
    except Exception as e:
        logger.error(f"Failed to update progress: {e}")

@app.route('/progress/<session_id>')
def get_progress(session_id):
    progress_file = os.path.join(UPLOAD_FOLDER, session_id, 'progress.json')
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'status' not in data:
                    data['status'] = 'processing'
                return jsonify(data)
        except:
            return jsonify({'percent': 0, 'status': 'processing', 'message': 'Մշակվում է...'})
    return jsonify({'percent': 0, 'status': 'processing', 'message': 'Սկսվում է...'})

# --- Օժանդակ ֆունկցիաներ ---

def extract_slide_images_free(pptx_path, session_folder, session_id):
    """
    Ազատ (Free) տարբերակ սլայդները նկար դարձնելու համար:
    Օգտագործում է LibreOffice --convert-to pdf և հետո pdf2image:
    """
    logger.info(f"Converting PPTX to PDF using LibreOffice for session {session_id}...")
    
    # 1. Փոխակերպում ենք PDF-ի (Headless LibreOffice)
    # Ubuntu-ում պետք է լինի տեղադրված: sudo apt install libreoffice
    success = False
    for cmd in ['libreoffice', 'soffice']:
        try:
            logger.info(f"Attempting PDF conversion with {cmd}...")
            subprocess.run([
                cmd, '--headless', 
                '--convert-to', 'pdf', 
                '--outdir', session_folder, 
                pptx_path
            ], check=True, capture_output=True)
            success = True
            break
        except FileNotFoundError:
            continue
        except Exception as e:
            logger.error(f"Conversion with {cmd} failed: {e}")
            continue
            
    if not success:
        raise RuntimeError("LibreOffice (կամ soffice) չգտնվեց կամ չկարողացավ փոխակերպել PPTX-ը: Համոզվեք, որ 'sudo apt install libreoffice' կատարված է:")

    pdf_path = pptx_path.replace('.pptx', '.pdf').replace('.ppt', '.pdf')
    # Երբեմն LibreOffice-ը փոխում է անունը մի փոքր այլ կերպ եթե ուղին բարդ է
    actual_pdf_path = os.path.join(session_folder, os.path.basename(pptx_path).rsplit('.', 1)[0] + ".pdf")
    
    if not os.path.exists(actual_pdf_path):
        raise RuntimeError("PDF ֆայլը չգտնվեց LibreOffice-ի մշակումից հետո:")

    # 2. PDF-ը բաժանում ենք նկարների (pdf2image)
    # Ubuntu-ում պետք է լինի poppler-utils: sudo apt install poppler-utils
    logger.info("Slicing PDF into PNG images...")
    images = convert_from_path(actual_pdf_path, dpi=150)
    
    saved_paths = []
    for i, image in enumerate(images):
        slide_img_name = f"slide_{i+1}.png"
        slide_img_path = os.path.join(session_folder, slide_img_name)
        image.save(slide_img_path, 'PNG')
        saved_paths.append(slide_img_path)
    
    # Մաքրում ենք ժամանակավոր PDF-ը
    try: os.remove(actual_pdf_path)
    except: pass
    
    return saved_paths

def generate_avatar_video(session_folder, audio_path, output_filename):
    """
    Generates a talking head video segment for a given audio file.
    Uses avatar.png as the source.
    """
    if not LIP_SYNC_AVAILABLE:
        return None
        
    try:
        avatar_source = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'avatar.png')
        if not os.path.exists(avatar_source):
            logger.warning("avatar.png not found in project root. Skipping avatar generation.")
            return None
            
        checkpoint = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'weights', 'wav2lip.pth')
        if not os.path.exists(checkpoint):
            logger.warning(f"Wav2Lip weights not found at {checkpoint}. Skipping avatar generation.")
            return None

        # Determine device
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        logger.info(f"Initializing LipSync on {device}...")
        lip = LipSync(
            model='wav2lip',
            checkpoint_path=checkpoint,
            device=device,
            img_size=96
        )
        
        output_path = os.path.join(session_folder, output_filename)
        logger.info(f"Generating lip-sync for {audio_path}...")
        
        # This is a blocking call and might be very slow on CPU
        # Note: 'avatar_source' is an image, so LipSync will animate it.
        lip.sync(avatar_source, audio_path, output_path)
        
        if os.path.exists(output_path):
            logger.info(f"Avatar video generated successfully: {output_path}")
            return output_path
        return None
        
    except Exception as e:
        logger.error(f"Failed to generate avatar video: {e}")
        return None

def check_stop_signal(session_id):
    """Ստուգում է, արդյոք օգտատերը պահանջել է դադարեցնել պրոցեսը"""
    if session_id in STOP_SIGNALS:
        logger.info(f"Stop signal received for session {session_id}")
        return True
    return False

def run_video_processing(session_id, session_folder, doc_path, ppt_path, doc_filename, ppt_filename):
    try:
        # Կարդում ենք պահպանված Word փաստաթուղթը
        if check_stop_signal(session_id): return
        update_progress(session_id, 5, "Կարդացվում է Word փաստաթուղթը...")
        doc = docx.Document(doc_path)
        
        # Քաղում ենք տեքստը պարբերություններից և աղյուսակներից
        content = []
        for para in doc.paragraphs:
            content.append(para.text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    content.append(cell.text)
        
        text = " ".join(content)
        
        # Բաժանում ենք տեքստը ըստ VO նշումների և քաղում ենք տեքստը
        # Օգտագործում ենք regex խմբավորում, որպեսզի պահպանենք նաև VO նշաններըԽ
        parts = re.split(r'(?i)((?:vo|voice)\s*\d+)', text)
        
        vo_data = {}
        # parts-ը կունենա հետևյալ տեսքը՝ ['', 'VO 1', ' տեքստ...', 'vo 2', ' տեքստ...']
        for i in range(1, len(parts), 2):
            vo_label = parts[i].upper().strip() # Դարձնում ենք միասնական (օր. VO 1)
            vo_text = parts[i+1].strip() if i+1 < len(parts) else ""
            vo_data[vo_label] = vo_text

        # Ստեղծում ենք ինֆորմացիոն օբյեկտը
        metadata = {
            "session_id": session_id,
            "total_vo_count": len(vo_data),
            "vo_segments": vo_data,
            "original_doc": doc_filename,
            "original_ppt": ppt_filename
        }

        # --- Գնահատման թեստի ստեղծում (Gemini Flash) ---
        if check_stop_signal(session_id): return
        update_progress(session_id, 10, "Ստեղծվում է գնահատման թեստը...")
        
        # Քաղում ենք տեքստը առանց VO նշումների
        cleaned_text_for_test = re.sub(r'(?i)(?:vo|voice)\s*\d+', '', text).strip()
        
        # [SECURITY/PERFORMANCE] Եթե տեքստը չափազանց երկար է, սեղմում ենք այն՝ API-ի սխալներից խուսափելու համար
        # 30,000 նիշը լիովին բավարար է 10 հարց ստեղծելու համար
        MAX_TEST_CHARS = 30000 
        if len(cleaned_text_for_test) > MAX_TEST_CHARS:
            logger.warning(f"Test generation text is too long ({len(cleaned_text_for_test)} chars). Truncating to {MAX_TEST_CHARS}.")
            cleaned_text_for_test = cleaned_text_for_test[:MAX_TEST_CHARS] + "... [Text truncated for prompt size]"
        
        
        test_prompt = f"""
Դու փորձառու կրթական բովանդակություն ստեղծող ես: Ստորև ներկայացված է SOURCE DOCUMENT-ը:

--- SOURCE DOCUMENT START ---
{cleaned_text_for_test}
--- SOURCE DOCUMENT END ---

Հիմնվելով վերոհիշյալ SOURCE DOCUMENT-ի վրա՝ կազմիր գնահատման թեստ բաղկացած 10 հարցից:

Պահանջներ.
1. Յուրաքանչյուր հարց պետք է ունենա 4 պատասխան, որոնցից միայն մեկն է ճիշտ:
2. Սխալ տարբերակները (distractors) պետք է լինեն տրամաբանական և առնչվեն տեքստին:
3. Հարցերը պետք է լինեն տարբեր բարդության՝ թե՛ փաստացի, թե՛ վերլուծական:
4. Ճիշտ պատասխանները ներկայացրու ամենավերջում՝ առանձին բաժնով:

Պատասխանը տրամադրիր միայն հայերեն լեզվով:
"""

        test_response = gemini_safe_call(
            model='gemini-3-flash-preview', 
            contents=test_prompt,
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_ONLY_HIGH'),
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_ONLY_HIGH'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_ONLY_HIGH'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_ONLY_HIGH'),
                ]
            )
        )
        
        test_doc = docx.Document()
        test_doc.add_heading('Գնահատման թեստ', 0)
        test_text = getattr(test_response, "text", "")
        test_doc.add_paragraph(test_text if test_text else "Թեստը չհաջողվեց ստեղծել (API սխալ):")
        
        test_filename = "evaluation_test.docx"
        test_doc_path = os.path.join(session_folder, test_filename)
        test_doc.save(test_doc_path)
        metadata["test_file"] = test_filename

        # Միասնական աուդիո ֆայլի ստեղծման փոփոխականներ
        audio_segments_list = []
        audio_details = []
        current_offset_ms = 0

        update_progress(session_id, 15, "Սկսվում է ձայնագրությունների գեներացումը...")
        # Յուրաքանչյուր VO հատվածի մշակում ըստ ճիշտ հերթականության
        def _get_vo_num(label):
            m = re.search(r'\d+', label)
            return int(m.group()) if m else 0
            
        sorted_vo_items = sorted(vo_data.items(), key=lambda item: _get_vo_num(item[0]))
        
        total_vo = len(sorted_vo_items)
        if total_vo == 0: total_vo = 1 # prevent division by zero
        
        for i, (vo_label, vo_text) in enumerate(sorted_vo_items):
            if check_stop_signal(session_id): return
            if not vo_text.strip():
                continue
            
            current_vo_progress = 15 + (40 * i / total_vo)
            update_progress(session_id, current_vo_progress, f"Ստեղծվում է ձայնագրություն {i+1}/{len(sorted_vo_items)}: {vo_label}...")
                
            # Define baseline path, though we might update the extension dynamically based on Gemini's response
            baseline_filename = f"segment_{i+1}_{secure_filename(vo_label)}"
            audio_path = os.path.join(session_folder, baseline_filename + ".mp3")
            
            try:
                logger.info(f"Generating audio for {vo_label} using Fenrir...")
                
                # Ձայնային ֆայլի ստեղծում (gemini-3.1-flash-tts-preview)
                response = gemini_safe_call(
                    model='gemini-3.1-flash-tts-preview',
                    contents=vo_text,
                    config=types.GenerateContentConfig(
                        response_modalities=['AUDIO'],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name='Fenrir'
                                )
                            )
                        ),
                        safety_settings=[
                            types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_ONLY_HIGH'),
                            types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_ONLY_HIGH'),
                            types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_ONLY_HIGH'),
                            types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_ONLY_HIGH'),
                        ]
                    )
                )

                # Պահպանում ենք սացված աուդիո ֆայլը առաջարկվող ֆորմատով
                audio_saved = False
                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data:
                            mime_type = getattr(part.inline_data, 'mime_type', '').lower()
                            
                            # Ստուգում ենք իրական ֆորմատը որպեսզի սխալ extension չդնենք
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
                                raise RuntimeError(f"Անհայտ աուդիո ֆորմատ (MIME): {mime_type}. Չենք կարող մշակել:")
                                
                            audio_filename = baseline_filename + ext
                            audio_path = os.path.join(session_folder, audio_filename)
                            
                            with open(audio_path, 'wb') as f:
                                f.write(part.inline_data.data)
                            
                            # Ստուգում ենք ֆայլի չափսը (եթե < 1KB, հավանաբար կոռուպցիա է)
                            if os.path.getsize(audio_path) < 1000:
                                raise RuntimeError(f"Ձայնային ֆայլը չափազանց փոքր է կամ դատարկ (VO: {vo_label})")
                                
                            audio_saved = True
                            break
                
                if not audio_saved:
                    raise RuntimeError(f"Ձայնային հատվածի ստեղծումը ձախողվեց (VO: {vo_label}): Gemini-ն պատասխան տվեց, բայց աուդիո տվյալներ չգտնվեցին:")

                if not os.path.exists(audio_path):
                    logger.warning(f"Audio file missing for {vo_label}. Skipping.")
                    continue

                # 3. Աուդիոյի միացում և ժամանակային տվյալների հաշվարկ
                if audio_path.endswith(".pcm"):
                    # Gemini RAW PCM is usually 24kHz, 16-bit, Mono
                    segment = AudioSegment.from_raw(
                        audio_path, 
                        sample_width=2, 
                        frame_rate=24000, 
                        channels=1
                    )
                    # Convert to WAV immediately so FFmpeg (used by lipsync) can read it without errors
                    new_audio_path = audio_path.replace(".pcm", ".wav")
                    segment.export(new_audio_path, format="wav")
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass
                    audio_path = new_audio_path
                else:
                    segment = AudioSegment.from_file(audio_path)
                
                duration_ms = len(segment)
                
                # Պահպանում ենք սկիզբն ու ավարտը ընդհանուր աուդիոյի նկատմամբ
                audio_details.append({
                    "sequence": i + 1,
                    "vo_label": vo_label,
                    "start_offset_sec": current_offset_ms / 1000.0,
                    "end_offset_sec": (current_offset_ms + duration_ms) / 1000.0,
                    "duration": duration_ms / 1000.0,
                    "text": vo_text
                })

                audio_segments_list.append(segment)
                current_offset_ms += duration_ms
                
                # --- [AVATAR] Generate speaking segment ---
                if LIP_SYNC_AVAILABLE:
                    avatar_segment_filename = f"avatar_segment_{i+1}.mp4"
                    update_progress(session_id, current_vo_progress, f"Ստեղծվում է ավատարի ձայնակցում {i+1}/{len(sorted_vo_items)}...")
                    avatar_video_path = generate_avatar_video(session_folder, audio_path, avatar_segment_filename)
                    if avatar_video_path:
                        audio_details[-1]["avatar_video"] = avatar_segment_filename
                
                logger.info(f"Processed {vo_label}: {duration_ms/1000.0}s")

            except Exception as gemini_err:
                raise RuntimeError(f"Ձայնային սեգմենտի ստեղծումը ձախողվեց ({vo_label}): {gemini_err}")
                
            # Prevent API burst rate limiting
            time.sleep(0.5)
        
        if not audio_segments_list:
            raise RuntimeError("No audio segments were generated")
            
        full_audio = AudioSegment.empty()
        for seg in audio_segments_list:
            full_audio += seg

        # --- PowerPoint Սլայդների մշակում և Gemini պատկերի ստեղծում ---
        update_progress(session_id, 55, "Սկսվում է սլայդների մշակումը (LibreOffice)...")
        slide_analysis = []
        try:
            # Օգտագործում ենք ազատ (free) տարբերակը նկարները հանելու համար
            slide_images = extract_slide_images_free(ppt_path, session_folder, session_id)
            total_slides = len(slide_images)
            if total_slides == 0: raise RuntimeError("Ոչ մի սլայդ չհայտնաբերվեց:")

            for i, slide_img_path in enumerate(slide_images):
                if check_stop_signal(session_id): return
                current_slide_progress = 55 + (30 * i / total_slides)
                update_progress(session_id, current_slide_progress, f"Մշակվում է սլայդ {i+1}/{total_slides}...")
                
                slide_index = i + 1
                beautified_img_name = f"slide_{slide_index}_beautified.png"
                beautified_img_path = os.path.join(session_folder, beautified_img_name)
                
                # Պատրաստում ենք պատկերը Gemini-ի համար
                with PIL.Image.open(slide_img_path) as img:
                        
                        # Gemini Multimodal հարցում որպեսզի գեներացնենք նոր պատկեր:
                        # Մենք հստակ ասում ենք, որ անտեսի Aspose-ի Evaluation watermark-ը
                        prompt_beautify = """
                        Generate a high-quality, modern, beautified 16:9 presentation slide based exactly on this image's content. 
                        
                        STRICT REQUIREMENTS (LOGO & ICON PRESERVATION):
                        1. Identify all LOGOS and ICONS in the original image. You MUST keep them UNTOUCHABLE.
                        2. Preserve their exact shapes, colors, content, and positions. Do NOT attempt to 'beautify' or change the logos/icons themselves.
                        3. Only beautify the background, typography of general text, and overall layout while keeping the brand assets (logos/icons) identical to the original.
                        
                        CONTENT CLEANING:
                        1. Ignore any watermark text like 'Evaluation only', 'Created with Aspose', or 'Copyright'. These are NOT part of the content.
                        2. Do not include any mention of Aspose or Evaluation in the generated image.
                        3. Output a clean, professional visual without any system text.
                        """
                        logger.info(f"Generating beautified image for Slide {slide_index}. This might take a bit...")
                        
                        response = gemini_safe_call(
                            #  model='gemini-3-pro-image-preview',
                            model='gemini-3.1-flash-image-preview',
                            contents=[prompt_beautify, img],
                            config=types.GenerateContentConfig(
                                response_modalities=["IMAGE"],
                                image_config=types.ImageConfig(
                                    aspect_ratio="16:9"
                                ),
                                safety_settings=[
                                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_ONLY_HIGH'),
                                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_ONLY_HIGH'),
                                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_ONLY_HIGH'),
                                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_ONLY_HIGH'),
                                ]
                            )
                        )
                    
                        img_saved = False
                        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                            for part in response.candidates[0].content.parts:
                                if part.inline_data:
                                    with open(beautified_img_path, "wb") as f:
                                        f.write(part.inline_data.data)
                                    img_saved = True
                                    break
                                elif hasattr(part, 'image') and part.image:
                                    part.image.save(beautified_img_path)
                                    img_saved = True
                                    break
                        
                        if not img_saved:
                            raise RuntimeError(f"Սլայդի պատկերի ստեղծումը ձախողվեց (Սլայդ: {slide_index}): Gemini պատասխանը պատկեր չէր պարունակում:")
                        
                        # --- Երաշխավորում ենք, որ պատկերը ճիշտ 1920x1080 չափսերով է ---
                        if img_saved:
                            try:
                                with PIL.Image.open(beautified_img_path) as saved_img:
                                    resized_img = saved_img.resize((1920, 1080), PIL.Image.LANCZOS)
                                resized_img.save(beautified_img_path)
                                logger.info(f"Resized beautified image to 1920x1080 for Slide {slide_index}")
                            except Exception as resize_err:
                                raise RuntimeError(f"Սլայդի չափսերի փոփոխման սխալ: {resize_err}")

                slide_analysis.append({
                    "slide_number": slide_index,
                    "image_file": beautified_img_name if img_saved else slide_img_name,
                    "beautify_suggestions": "Image generated." if img_saved else "Failed to generate image."
                })
                logger.info(f"Processed and Beautified Slide {slide_index}")
                
                # Prevent API burst rate limiting
                time.sleep(0.5)
        except Exception as ppt_err:
            raise RuntimeError(f"PPTX վերլուծության սխալ: {ppt_err}")

        # Վերջնական աուդիո ֆայլի պահպանում
        full_audio_filename = "full_voiceover.mp3"
        full_audio_path = os.path.join(session_folder, full_audio_filename)
        full_audio.export(full_audio_path, format="mp3")

        # --- Տեսանյութի ստեղծում (MoviePy) ---
        if check_stop_signal(session_id): return
        update_progress(session_id, 85, "Ստեղծվում է վերջնական տեսանյութը (դա կարող է տևել մի քանի րոպե)...")
        video_filename = "final_video.mp4"
        video_path = os.path.join(session_folder, video_filename)
        
        video_segments = []
        # Ապահովում ենք ճշգրիտ համապատասխանություն 1-ին VO = 1-ին սլայդ սկզբունքով
        import itertools
        for detail, slide_info in itertools.zip_longest(audio_details, slide_analysis, fillvalue=None):
            if not detail:
                break  # Եթե ավարտվեցին ձայները, կանգ ենք առնում (տեսանյութի երկարությունը որոշվում է ձայնով)
                
            if not slide_info and slide_analysis:
                # Եթե սլայդները պակաս են, կրկնում ենք վերջին սլայդը մնացած ձայների համար
                slide_info = slide_analysis[-1]
                
            if slide_info:
                target_img_path = os.path.join(session_folder, slide_info['image_file'])
                if os.path.exists(target_img_path):
                    duration = detail['duration']
                    clip = ImageClip(target_img_path, duration=duration)
                    
                    # --- [AVATAR] Overlay talking head if available ---
                    if "avatar_video" in detail:
                        avatar_video_path = os.path.join(session_folder, detail["avatar_video"])
                        if os.path.exists(avatar_video_path):
                            from moviepy import VideoFileClip
                            # Create the avatar clip, resize it (e.g., 1/4 of height), and position it
                            # We use a circular mask or a simple corner overlay
                            avatar_clip = VideoFileClip(avatar_video_path).resized(height=360) # 1080 / 3
                            # Position at bottom-right with a small margin
                            avatar_clip = avatar_clip.with_position(("right", "bottom")).with_start(0)
                            
                            # Composite the slide and the avatar
                            from moviepy import CompositeVideoClip
                            clip = CompositeVideoClip([clip, avatar_clip])
                    
                    video_segments.append(clip)
        if not video_segments:
            raise RuntimeError("No video segments were created")
            
        final_video = concatenate_videoclips(video_segments, method="compose")
        final_video = final_video.with_audio(AudioFileClip(full_audio_path))
        final_video.write_videofile(video_path, fps=24, codec="libx264", audio_codec="aac")
        
        # Մաքրում ենք հիշողությունը (Resource Leak կանխում)
        final_video.close()
        for clip in video_segments:
            clip.close()

        # Metadata-ի թարմացում ժամանակային տվյալներով
        metadata["audio_segments_info"] = audio_details
        metadata["full_audio_path"] = full_audio_filename
        metadata["total_duration"] = current_offset_ms / 1000.0
        metadata["slide_analysis"] = slide_analysis

        metadata_path = os.path.join(session_folder, 'metadata.json')
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)

        # Հաջող ավարտի և արդյունքների ուղարկում ֆրոնտենդին
        final_result = {
            'success': True,
            'vo_count': len(vo_data),
            'session_id': session_id,
            'audio_timeline': audio_details,
            'total_duration': current_offset_ms / 1000.0,
            'video_url': video_filename,
            'slide_analysis': slide_analysis
        }
        update_progress(session_id, 100, "Ավարտված է", result=final_result, status="done")
        logger.info(f"Session {session_id} background processing finished successfully.")

    except Exception as e:
        logger.error(f"Error in background formatting: {e}")
        try:
            update_progress(session_id, 0, f"Սխալ: {str(e)}", result={'success': False, 'error': str(e)}, status="error")
        except:
            pass

@app.route('/process', methods=['GET', 'POST'], strict_slashes=False)
def process_files():
    # Եթե բրաուզերով ուղղակի բացեք այս հասցեն (GET), կտեսնեք այս հաղորդագրությունը
    if request.method == 'GET':
        return jsonify({
            'success': True, 
            'message': 'Սերվերը պատրաստ է ընդունել ֆայլեր (POST հարցման միջոցով)'
        }), 200

    try:
        doc_file = request.files.get('docFile')
        ppt_file = request.files.get('pptFile')

        if not doc_file or not ppt_file:
            return jsonify({'success': False, 'error': 'Ֆայլերը բացակայում են'}), 400
        
        # Ստեղծում ենք եզակի ID այս հարցման համար
        session_id = request.form.get('session_id')
        if not session_id:
            session_id = str(uuid.uuid4())
        session_folder = os.path.join(UPLOAD_FOLDER, session_id)
        os.makedirs(session_folder, exist_ok=True)

        doc_filename = secure_filename(doc_file.filename)
        ppt_filename = secure_filename(ppt_file.filename)
        
        update_progress(session_id, 2, "Ֆայլերը պահպանվում են սերվերում...")
        
        if not doc_filename.lower().endswith('.docx'):
            return jsonify({'success': False, 'error': 'Invalid format: Word document must be .docx'}), 400
            
        if not ppt_filename.lower().endswith(('.pptx', '.ppt')):
            return jsonify({'success': False, 'error': 'Invalid format: PowerPoint document must be .pptx or .ppt'}), 400
        
        doc_path = os.path.join(session_folder, doc_filename)
        ppt_path = os.path.join(session_folder, ppt_filename)
        
        doc_file.save(doc_path)
        ppt_file.save(ppt_path)
        
        # Start the background thread
        thread = threading.Thread(
            target=run_video_processing, 
            args=(session_id, session_folder, doc_path, ppt_path, doc_filename, ppt_filename),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': 'Մշակումը սկսվել է ֆոնային ռեժիմում'
        })
        
    except Exception as e:
        logger.error(f"Error starting process: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/download/<session_id>/<filename>')
def download_file(session_id, filename):
    folder = os.path.join(UPLOAD_FOLDER, session_id)
    return send_from_directory(folder, filename, as_attachment=True)

@app.route('/stop/<session_id>', methods=['POST'])
def stop_processing(session_id):
    """Ավելացնում է session-ը STOP_SIGNALS-ում"""
    logger.warning(f"User requested stop for session {session_id}")
    STOP_SIGNALS.add(session_id)
    
    # Թարմացնում ենք պրոգրեսը որպես կանգնեցված
    update_progress(session_id, 0, "Դադարեցված է օգտատիրոջ կողմից", status="cancelled")
    
    return jsonify({'success': True, 'message': 'Processing stop request received.'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
