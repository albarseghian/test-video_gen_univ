import os
import sys
import logging
import wave
import subprocess

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_sadtalker(pcm_path):
    if not os.path.exists(pcm_path):
        logger.error(f"Input file '{pcm_path}' does not exist.")
        return

    project_root = os.path.dirname(os.path.abspath(__file__))
    sadtalker_dir = os.path.join(project_root, "SadTalker")
    
    if not os.path.exists(sadtalker_dir):
        logger.error(f"SadTalker repository not found at {sadtalker_dir}. Please run scripts/setup_sadtalker.py first.")
        return

    # 1. Convert PCM to WAV
    wav_path = pcm_path.replace(".pcm", ".wav")
    logger.info(f"Loading {pcm_path} and converting to WAV...")
    try:
        if pcm_path.endswith(".pcm"):
            with open(pcm_path, 'rb') as pcm_file:
                pcm_data = pcm_file.read()
                
            with wave.open(wav_path, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
                wav_file.writeframes(pcm_data)
        else:
            import shutil
            if pcm_path != wav_path:
                shutil.copy2(pcm_path, wav_path)
        logger.info("Audio conversion to WAV successful.")
    except Exception as e:
        logger.error(f"Failed to load or convert audio: {e}")
        return

    # 2. Setup paths for SadTalker
    avatar_image = os.path.join(project_root, 'avatar_bank.mp4')
    if not os.path.exists(avatar_image):
        logger.error(f"Avatar image not found at {avatar_image}")
        return

    output_dir = os.path.join(project_root, "tests", "sadtalker_results")
    os.makedirs(output_dir, exist_ok=True)

    # 3. Run SadTalker Inference
    logger.info("Running SadTalker inference...")
    
    # Prefer local venv
    if os.name == 'nt':  # Windows
        python_exe = os.path.join(project_root, ".venv311", "Scripts", "python.exe")
        if not os.path.exists(python_exe):
            python_exe = os.path.join(project_root, "env", "Scripts", "python.exe")
    else:  # Ubuntu / Linux
        python_exe = os.path.join(project_root, "venv", "bin", "python3")
        if not os.path.exists(python_exe):
            python_exe = "python3" # Fallback to system python

    # We call SadTalker's inference script
    command = [
        python_exe,
        os.path.join(sadtalker_dir, "inference.py"),
        "--driven_audio", wav_path,
        "--source_image", avatar_image,
        "--result_dir", output_dir,
        "--still",  # Keep head pose more stable
        "--preprocess", "full",  # Crop to face
        "--enhancer", "gfpgan"   # Better face quality
    ]
    
    logger.info(f"Executing: {' '.join(command)}")
    
    try:
        # Run and capture output
        process = subprocess.Popen(
            command,
            cwd=sadtalker_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        for line in process.stdout:
            print(line, end='')
            
        process.wait()
        
        if process.returncode == 0:
            logger.info(f"SUCCESS! SadTalker video generated. Check the {output_dir} folder.")
        else:
            logger.error(f"SadTalker failed with return code {process.returncode}")
            
    except Exception as e:
        logger.error(f"Exception during SadTalker execution: {e}")

if __name__ == "__main__":
    test_file = r"tests/voices/Achernar.pcm"
    
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        
    logger.info(f"Starting SadTalker test with file: {test_file}")
    test_sadtalker(test_file)
