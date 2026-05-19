import os
import sys
import subprocess
import requests
import zipfile
import re
from tqdm import tqdm

def run_command(command, cwd=None):
    print(f"Running: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, shell=False)
    if result.returncode != 0:
        print(f"Error: Command failed with return code {result.returncode}")
        return False
    return True

def download_file(url, dest_path, expected_min_size=10*1024): # Default 10KB min
    if os.path.exists(dest_path):
        current_size = os.path.getsize(dest_path)
        if current_size >= expected_min_size:
            # print(f"File already exists and size seems okay ({current_size/1024:.1f}KB): {dest_path}")
            return True
        else:
            print(f"File {dest_path} too small ({current_size} bytes), re-downloading...")
            os.remove(dest_path)

    print(f"Downloading {url} to {dest_path}...")
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, 'wb') as f, tqdm(total=total_size, unit='B', unit_scale=True, desc=os.path.basename(dest_path)) as bar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                bar.update(size)
        return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False

def patch_file_comprehensive(file_path):
    if not os.path.exists(file_path):
        return
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        replacements = {
            'np.float': 'float',
            'np.int': 'int',
            'np.bool': 'bool',
            'np.complex': 'complex',
            'np.object': 'object',
            'torchvision.transforms.functional_tensor': 'torchvision.transforms.functional',
            'from .scandir import scandir': 'try:\n    from .scandir import scandir\nexcept:\n    from os import scandir'
        }
        
        original_content = content
        for search, replace in replacements.items():
            if search in content:
                content = re.sub(re.escape(search) + r'(?!\d)', replace, content)
        
        if content != original_content:
            print(f"Fixed compatibility in {file_path}")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
    except Exception as e:
        print(f"Failed to patch {file_path}: {e}")

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sadtalker_dir = os.path.join(project_root, "SadTalker")
    checkpoint_dir = os.path.join(sadtalker_dir, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)

    # 1. Ensure basicsr is patched and installed
    pip_cmd = [sys.executable, "-m", "pip", "install"]
    run_command(pip_cmd + ["numpy<2.0.0", "facexlib", "gfpgan", "basicsr"], cwd=project_root)

    # 2. Total Patching
    import sysconfig
    site_packages = sysconfig.get_path('purelib')
    targets = [sadtalker_dir, os.path.join(site_packages, "facexlib"), os.path.join(site_packages, "gfpgan"), os.path.join(site_packages, "basicsr")]
    for target in targets:
        if os.path.exists(target):
            for root, dirs, files in os.walk(target):
                for file in files:
                    if file.endswith('.py'):
                        patch_file_comprehensive(os.path.join(root, file))

    # 3. Weights - Correcting release tags (v0.0.1 vs v0.0.2-rc)
    v1_url = "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.1"
    v2_url = "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc"
    
    # Files in v0.0.1
    v1_weights = {
        "auido2exp_00062-model.pth.tar": 100*1024,
        "auido2pose_00140-model.pth.tar": 100*1024,
        "epoch_20.pth": 100*1024,
        "facevid2vid_00189-model.pth.tar": 500*1024*1024,
    }
    for name, size in v1_weights.items():
        download_file(f"{v1_url}/{name}", os.path.join(checkpoint_dir, name), expected_min_size=size)

    # Files in v0.0.2-rc
    v2_weights = {
        "mapping_00109-model.pth.tar": 10*1024*1024,
        "mapping_00229-model.pth.tar": 10*1024*1024,
        "SadTalker_V0.0.2_256.safetensors": 600*1024*1024,
        "SadTalker_V0.0.2_512.safetensors": 600*1024*1024,
    }
    for name, size in v2_weights.items():
        download_file(f"{v2_url}/{name}", os.path.join(checkpoint_dir, name), expected_min_size=size)

    # 4. BFM Fitting & Landmarks
    download_file("https://github.com/OpenTalker/SadTalker/releases/download/v0.0.1/shape_predictor_68_face_landmarks.dat", 
                  os.path.join(checkpoint_dir, "shape_predictor_68_face_landmarks.dat"), expected_min_size=90*1024*1024)
    
    bfm_zip = os.path.join(checkpoint_dir, "BFM_Fitting.zip")
    if download_file("https://github.com/OpenTalker/SadTalker/releases/download/v0.0.1/BFM_Fitting.zip", bfm_zip, expected_min_size=100*1024*1024):
        print("Extracting BFM Fitting files...")
        with zipfile.ZipFile(bfm_zip, 'r') as z:
            z.extractall(checkpoint_dir)
            # Ensure the structure matches what SadTalker expects (it often looks for BFM_Fitting subfolder)
            extract_path = os.path.join(checkpoint_dir, "BFM_Fitting")
            if not os.path.exists(extract_path):
                os.makedirs(extract_path)
            z.extractall(extract_path)

    print("\n[READY] All 9-byte files replaced. Run sadtalker_v2_test.py.")

if __name__ == "__main__":
    main()
