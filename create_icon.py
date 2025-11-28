from PIL import Image

# Convert JPG to ICO
img = Image.open('lyridanlogo.jpg')

# Resize to common icon sizes
icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
img.save('lyridanlogo.ico', format='ICO', sizes=icon_sizes)

print("Icon created successfully: lyridanlogo.ico")
