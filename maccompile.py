import PyInstaller.__main__
import os
import shutil

# 1. CLEANUP
# Remove previous build folders to ensure a fresh compile
if os.path.exists('build'): shutil.rmtree('build')
if os.path.exists('dist'): shutil.rmtree('dist')

# 2. SETUP VARIABLES
# macOS uses ':' as a separator, Windows uses ';'. This handles it automatically.
sep = os.pathsep

# Name of your app
app_name = "Lyridan"

# ENTRY POINT
script_file = "gui.py"

# 3. RUN PYINSTALLER
PyInstaller.__main__.run([
    script_file,
    f'--name={app_name}',
    
    # SYSTEM SETTINGS
    '--noconfirm',
    '--clean',
    '--windowed',  # Essential for Mac Apps
    
    # MAC SPECIFIC: BUILD FOR INTEL AND APPLE SILICON
    '--target-arch=universal2',
    
    # ICONS
    # NOTE: For the App Icon (Dock), Mac requires .icns. 
    # If you only have .ico, convert it or PyInstaller might ignore it/warn.
    '--icon=lyridanlogo.icns', 
    
    # DATA FILES (Syntax: "source_path:dest_path")
    # We use 'sep' to automatically switch between ; (win) and : (mac)
    f'--add-data=English.txt{sep}.',
    f'--add-data=lyridanlogo.ico{sep}.', # Keeping this so your internal GUI can load the ico
    
    # IMPORTS
    '--hidden-import=syllabize',
    '--hidden-import=config',
    
    # COLLECT ALL PACKAGES
    '--collect-all=tkinterdnd2',
    '--collect-all=pykakasi',
    '--collect-all=transliterate',
    
    # OPTIONAL: Code Signing (Uncomment and edit if you have your ID)
    # f'--codesign-identity=Developer ID Application: YOUR NAME (TEAMID)',
])

print("\n-------------------------------------------------------")
print(f"Build Finished! Check the 'dist/{app_name}.app' folder.")
print("-------------------------------------------------------")