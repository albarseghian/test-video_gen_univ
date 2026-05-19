import torch
import os

path = os.path.join(os.path.dirname(__file__), 'weights', 'wav2lip.pth')

print(f"Loading original weights from {path}...")
checkpoint = torch.load(path, map_location="cpu")

if "state_dict" in checkpoint:
    s = checkpoint["state_dict"]
    new_s = {}
    for k, v in s.items():
        # Remove 'module.' prefix if present
        new_s[k.replace('module.', '')] = v
        
    print("Saving cleaned weights...")
    torch.save(new_s, path)
    print("Done! Weights have been fixed and are ready for lipsync.")
else:
    print("Weights are already cleaned! No changes made.")
