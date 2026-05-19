import os
import sys
import subprocess
import logging
import wave

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_v2_inference(audio_path, source_image=None, result_dir=None, still=True, preprocess='full', enhancer='gfpgan', size=256):
    """
    Runs SadTalker v2 inference following instructions from sadtalkerai.com
    """
    project_root = os.path.dirname(os.path.abspath(__file__))
    sadtalker_dir = os.path.join(project_root, "SadTalker")
    
    if not source_image:
        source_image = os.path.join(project_root, 'avatar_bank.mp4')
    
    if not result_dir:
        result_dir = os.path.join(project_root, "results", "v2_test")
    
    os.makedirs(result_dir, exist_ok=True)

    # 1. Environment Detection (Ubuntu vs Windows)
    if os.name == 'nt':
        python_exe = os.path.join(project_root, ".venv311", "Scripts", "python.exe")
        if not os.path.exists(python_exe):
            python_exe = os.path.join(project_root, "env", "Scripts", "python.exe")
    else:
        python_exe = os.path.join(project_root, "venv", "bin", "python3")
        if not os.path.exists(python_exe):
            python_exe = "python3"

    # 2. Check for basicsr patch (Robust non-importing patch)
    logger.info("Verifying basicsr compatibility...")
    try:
        # Use sysconfig to find site-packages without importing broken libs
        import sysconfig
        site_packages = sysconfig.get_path('purelib')
        basicsr_path = os.path.join(site_packages, 'basicsr')
        
        if os.path.exists(basicsr_path):
            logger.info(f"Patching basicsr at {basicsr_path}...")
            for root, dirs, files in os.walk(basicsr_path):
                for file in files:
                    if file.endswith('.py'):
                        fpath = os.path.join(root, file)
                        if os.path.getsize(fpath) > 0:
                            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            if 'functional_tensor' in content:
                                with open(fpath, 'w', encoding='utf-8') as f:
                                    f.write(content.replace('functional_tensor', 'functional'))
            
            # Also fix the scandir issue in __init__.py
            init_path = os.path.join(basicsr_path, 'utils', '__init__.py')
            if os.path.exists(init_path):
                with open(init_path, 'r', encoding='utf-8') as f:
                    init_content = f.read()
                if 'from .scandir import scandir' in init_content and 'try:' not in init_content:
                    with open(init_path, 'w', encoding='utf-8') as f:
                        f.write(init_content.replace('from .scandir import scandir', 'try:\n    from .scandir import scandir\nexcept:\n    from os import scandir'))
    except Exception as e:
        logger.warning(f"Auto-patch failed: {e}")

    # 3. Audio Validation (Ensure WAV format)
    wav_path = audio_path
    if audio_path.endswith('.pcm'):
        wav_path = audio_path.replace('.pcm', '.wav')
        logger.info(f"Converting PCM to WAV: {wav_path}")
        with open(audio_path, 'rb') as pcm_file:
            pcm_data = pcm_file.read()
        with wave.open(wav_path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(pcm_data)

    # 4. Build Command based on sadtalkerai.com instructions
    command = [
        python_exe,
        os.path.join(sadtalker_dir, "inference.py"),
        "--driven_audio", wav_path,
        "--source_image", source_image,
        "--result_dir", result_dir,
        "--preprocess", preprocess,  # 'crop', 'resize', 'full'
        "--enhancer", enhancer,      # 'gfpgan' or 'RestoreFormer'
        "--size", str(size)          # 256 or 512
    ]
    
    if still:
        command.append("--still")
        
    logger.info(f"Launching SadTalker v2 Inference: {' '.join(command)}")

    try:
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
            print(f"[SadTalker] {line}", end='')
            
        process.wait()
        
        if process.returncode == 0:
            logger.info(f"SUCCESS! Result saved in: {result_dir}")
        else:
            logger.error(f"SadTalker failed with return code {process.returncode}")
            
    except Exception as e:
        logger.error(f"Execution Error: {e}")

if __name__ == "__main__":
    # Default test with production assets
    test_audio = "tests/voices/Achernar.wav"
    
    if len(sys.argv) > 1:
        test_audio = sys.argv[1]

    run_v2_inference(
        audio_path=os.path.abspath(test_audio),
        preprocess='full',  # Best for production avatars
        enhancer='gfpgan',  # High quality
        still=True,         # Keep head stable
        size=256            # Standard resolution (512 is also supported)
    )
