"""Copy the current TX/RX release files from experimental/ to this folder and rewrite SHA256SUMS.txt.

    python publish_current.py LPM-10A-TX_PN2.20-cable-text-clear.bin APP_LPM-10RX_PN1.23-mains-tone-update.bin
"""
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
names = sys.argv[1:] or ["LPM-10A-TX_PN2.20-cable-text-clear.bin", "APP_LPM-10RX_PN1.23-mains-tone-update.bin"]
for old in os.listdir(HERE):
    if old.endswith(".bin") and old not in names:
        os.remove(os.path.join(HERE, old))
        print("removed", old)
with open(os.path.join(HERE, "SHA256SUMS.txt"), "w", newline="\n") as sums:
    for name in names:
        shutil.copyfile(os.path.join(HERE, "experimental", name), os.path.join(HERE, name))
        digest = hashlib.sha256(open(os.path.join(HERE, name), "rb").read()).hexdigest()
        sums.write(f"{digest}  {name}\n")
        print(digest, name)
