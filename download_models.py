import urllib.request
import ssl
import sys
from pathlib import Path

# Bypass SSL context verify to avoid certificate issues on some systems
ssl_context = ssl._create_unverified_context()

models = {
    "yolov8m.pt": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8m.pt",
    "osnet_x0_25_market1501.pt": "https://github.com/mikel-brostrom/deep_sort_reid/releases/download/v1.0/osnet_x0_25_market1501.pt"
}

dest_dir = Path("models")
dest_dir.mkdir(exist_ok=True)

for name, url in models.items():
    dest_path = dest_dir / name
    print(f"Downloading {name} from {url}...")
    try:
        # Use simple retrieve with unverified context
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context))
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url, str(dest_path))
        print(f"Successfully downloaded {name} to {dest_path}. Size: {dest_path.stat().st_size} bytes")
    except Exception as e:
        print(f"Error downloading {name}: {e}")
        sys.exit(1)

print("All downloads finished successfully.")
