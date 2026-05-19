import os
import sys
import logging
import wave

# Disable PyTorch compilation to fix the "cl is not found" error on Windows
os.environ["TORCH_COMPILE_DISABLE"] = "1"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Check if lipsync is available
try:
    from lipsync import LipSync
    LIP_SYNC_AVAILABLE = True
except ImportError as e:
    LIP_SYNC_AVAILABLE = False
    logger.error(f"lipsync library not found: {e}")

def test_avatar(pcm_path):
    if not os.path.exists(pcm_path):
        logger.error(f"Input file '{pcm_path}' does not exist.")
        logger.info("Please provide a valid .pcm file to test.")
        return

    if not LIP_SYNC_AVAILABLE:
        logger.error("LipSync is not available. Please ensure it is installed.")
        return

    # 1. Convert PCM to WAV (using Python's built-in 'wave' module instead of pydub)
    wav_path = pcm_path.replace(".pcm", ".wav")
    logger.info(f"Loading {pcm_path} and converting to WAV...")
    try:
        if pcm_path.endswith(".pcm"):
            # Gemini RAW PCM is usually 24kHz, 16-bit, Mono
            with open(pcm_path, 'rb') as pcm_file:
                pcm_data = pcm_file.read()
                
            with wave.open(wav_path, 'wb') as wav_file:
                wav_file.setnchannels(1)       # Mono
                wav_file.setsampwidth(2)       # 16-bit
                wav_file.setframerate(24000)   # 24kHz
                wav_file.writeframes(pcm_data)
        else:
            # If it's already a .wav, just copy it or use it directly
            import shutil
            if pcm_path != wav_path:
                shutil.copy2(pcm_path, wav_path)
            
        logger.info("Audio conversion to WAV successful.")
    except Exception as e:
        logger.error(f"Failed to load or convert audio: {e}")
        return

    # 2. Setup paths for Avatar Generation
    project_root = os.path.dirname(os.path.abspath(__file__))
    avatar_source = os.path.join(project_root, 'avatar_bank.mp4')
    checkpoint = os.path.join(project_root, 'weights', 'wav2lip.pth')
    output_path = pcm_path.replace(".pcm", "bank_avatar_output.mp4")

    if not os.path.exists(avatar_source):
        logger.error(f"Avatar image not found at {avatar_source}")
        return
        
    if not os.path.exists(checkpoint):
        logger.error(f"Wav2Lip weights not found at {checkpoint}")
        return

    # 3. Initialize LipSync and Generate Video
    import torch
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info(f"Initializing LipSync on {device}...")
    
    try:
        lip = LipSync(
            model='wav2lip',
            checkpoint_path=checkpoint,
            device=device,
            img_size=96
        )
        
        logger.info(f"Generating lip-sync video. This might take a while on CPU...")
        logger.info(f"Input image: {avatar_source}")
        logger.info(f"Input audio: {wav_path}")
        
        # This is the blocking call from app.py
        lip.sync(avatar_source, wav_path, output_path)
        
        if os.path.exists(output_path):
            logger.info(f"SUCCESS! Avatar video generated successfully: {output_path}")
        else:
            logger.error("Failed. LipSync completed but output file was not created.")
            
    except Exception as e:
        logger.error(f"Exception during LipSync generation: {e}")

if __name__ == "__main__":
    # 👉 PUT YOUR FILE PATH HERE:
    # Example: test_file = r"tests/voices/Achernar.pcm"
    test_file = r"tests/voices/Achernar.pcm"
    
    # You can still pass it via command line if you want
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        
    logger.info(f"Starting isolated avatar generation test with file: {test_file}")
    test_avatar(test_file)
