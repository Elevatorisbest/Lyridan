import PyInstaller.__main__
import os
import shutil
import plistlib # Needed to edit the Info.plist properly

# --- CONFIGURATION ---
VERSION = "1.1.0"
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
    
    # SYSTEM SETTINGS
    '--noconfirm',
    '--clean',
    '--windowed',
    
    # ARCHITECTURE
    '--target-arch=universal2',
    
    # ICONS
    f'--icon={ICON_FILE}', 
    
    # DATA FILES
    f'--add-data=English.txt{sep}.',
    f'--add-data=lyridanlogo.ico{sep}.', 
    
    # IMPORTS & PACKAGES
    '--hidden-import=syllabize',
    '--hidden-import=config',
    '--collect-all=tkinterdnd2',
    '--collect-all=pykakasi',
    '--collect-all=transliterate',
])

# 4. POST-PROCESS: INJECT VERSION INTO INFO.PLIST
# This step fixes the "0.0.0" issue automatically
info_plist_path = os.path.join('dist', f'{APP_NAME}.app', 'Contents', 'Info.plist')

if os.path.exists(info_plist_path):
    print(f"Updating Info.plist version to {VERSION}...")
    
    with open(info_plist_path, 'rb') as f:
        plist = plistlib.load(f)

    # Update the dictionary
    plist['CFBundleShortVersionString'] = VERSION
    plist['CFBundleVersion'] = VERSION
    plist['NSHumanReadableCopyright'] = COPYRIGHT
    plist['CFBundleGetInfoString'] = "Romanizing, transliterating and syllabizing tool"
    
    # Write it back
    with open(info_plist_path, 'wb') as f:
        plistlib.dump(plist, f)
else:
    print("Error: Could not find Info.plist to update version number.")

print("\n-------------------------------------------------------")
print(f"Build Finished! {APP_NAME}.app is ready in 'dist/'")
print(f"Version: {VERSION}")
print("-------------------------------------------------------")