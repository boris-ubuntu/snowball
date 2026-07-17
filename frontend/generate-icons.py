from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size, output_path):
    """Create a PWA icon with € symbol on blue gradient background"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw rounded rectangle background
    corner_radius = size // 5
    # Simple rounded rect using a series of rects and circles
    draw.rounded_rectangle([(0, 0), (size-1, size-1)], radius=corner_radius, fill='#00aff5')
    
    # Draw € symbol
    font_size = size // 2
    try:
        # Try to find a bold font
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        try:
            font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
    
    # Get text bounding box
    bbox = draw.textbbox((0, 0), "€", font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2 - bbox[0]
    y = (size - text_h) // 2 - bbox[1] - 2
    
    # Draw white €
    draw.text((x, y), "€", fill="white", font=font)
    
    img.save(output_path, 'PNG')

# Generate icons
script_dir = os.path.dirname(os.path.abspath(__file__))
sizes = [192, 512]
for size in sizes:
    output = os.path.join(script_dir, f'icon-{size}.png')
    create_icon(size, output)
    print(f"Created {output} ({size}x{size})")

print("All icons generated!")
