import PyInstaller.__main__
import os
import shutil
import plistlib
import subprocess

# --- CONFIGURATION ---
VERSION = "1.1.1"
COPYRIGHT = "Copyright © 2025 Elevatorisbest"
APP_NAME = "Lyridan"
SCRIPT_FILE = "gui.py"
ICON_FILE = "lyridanlogo.icns" 

# 1. CLEANUP
if os.path.exists('build'): shutil.rmtree('build')
if os.path.exists('dist'): shutil.rmtree('dist')

# 2. SETUP VARIABLES
sep = os.pathsep

# 3. RUN PYINSTALLER
print(f"Compiling {APP_NAME} v{VERSION}...")

PyInstaller.__main__.run([
    SCRIPT_FILE,
    f'--name={APP_NAME}',
    '--noconfirm',
    '--clean',
    '--windowed',
    '--target-arch=universal2',
    f'--icon={ICON_FILE}', 
    f'--add-data=English.txt{sep}.',
    f'--add-data=lyridanlogo.ico{sep}.', 
    '--hidden-import=syllabize',
    '--hidden-import=config',
    '--hidden-import=nlp_manager',
    '--collect-all=tkinterdnd2',
    '--collect-all=pykakasi',
    '--collect-all=transliterate',
    '--collect-all=cutlet',
    '--collect-all=sudachipy',
    '--collect-all=sudachidict_full',
    '--collect-all=g2p_en',
    '--collect-all=torch',
    '--collect-all=transformers',
    '--collect-all=unidic_lite',
    '--collect-all=fugashi',
])

# 4. POST-PROCESS: INJECT VERSION INTO INFO.PLIST
app_path = os.path.join('dist', f'{APP_NAME}.app')
info_plist_path = os.path.join(app_path, 'Contents', 'Info.plist')

if os.path.exists(info_plist_path):
    print(f"Updating Info.plist version to {VERSION}...")
    with open(info_plist_path, 'rb') as f:
        plist = plistlib.load(f)
    plist['CFBundleShortVersionString'] = VERSION
    plist['CFBundleVersion'] = VERSION
    plist['NSHumanReadableCopyright'] = COPYRIGHT
    plist['CFBundleGetInfoString'] = "Romanizing, transliterating and syllabizing tool"
    with open(info_plist_path, 'wb') as f:
        plistlib.dump(plist, f)

# 5. CREATE DMG (The New Part)
print("\n-------------------------------------------------------")
print("Creating DMG Installer...")

# Define paths
dmg_staging_folder = os.path.join('dist', 'dmg_staging')
dmg_output_path = os.path.join('dist', f'{APP_NAME}.dmg')

# A. Prepare Staging Folder
if os.path.exists(dmg_staging_folder): shutil.rmtree(dmg_staging_folder)
os.makedirs(dmg_staging_folder)

# B. Copy App to Staging
print("Copying App to staging area...")
shutil.copytree(app_path, os.path.join(dmg_staging_folder, f'{APP_NAME}.app'))

# C. Create Symlink to /Applications
# This allows the user to drag the app to the Applications folder easily
print("Creating /Applications shortcut...")
os.symlink('/Applications', os.path.join(dmg_staging_folder, 'Applications'))

# D. Build the DMG using 'hdiutil' (Built-in macOS tool)
# We use 'subprocess' to run the terminal command
cmd = [
    'hdiutil', 'create',
    '-volname', APP_NAME,       # The name of the "disk" when mounted
    '-srcfolder', dmg_staging_folder,
    '-ov',                      # Overwrite if exists
    '-format', 'UDZO',          # Compressed format
    dmg_output_path
]

try:
    subprocess.run(cmd, check=True)
    print(f"✅ DMG created successfully: {dmg_output_path}")
    
    # Clean up staging folder to keep 'dist' clean
    shutil.rmtree(dmg_staging_folder)
    
except subprocess.CalledProcessError as e:
    print(f"❌ Error creating DMG: {e}")

print("\n-------------------------------------------------------")
print(f"Build Finished! You can find '{APP_NAME}.dmg' in the 'dist' folder.")
print("-------------------------------------------------------")