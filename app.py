from flask import Flask, render_template, request, send_file
import qrcode
import base64
import socket
import os
import io
import cv2
import numpy as np
import zipfile
from PIL import Image, ImageDraw, ImageFont
from pyzbar.pyzbar import decode

app = Flask(__name__)
UPLOAD_FOLDER = "static/qr_codes"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

QR_SIZE_LIMIT = 250  # Adjust based on actual QR limits
FLAG = "BASE64_QR"


def split_text(text, size_limit):
    # Split the original text into chunks.
    parts = [text[i:i+size_limit] for i in range(0, len(text), size_limit)]
    total = len(parts)
    # Encode each chunk independently.
    return [f"{FLAG}:{i+1}/{total}:" + base64.b64encode(part.encode()).decode() 
            for i, part in enumerate(parts)]

def generate_qr(text, client_ip):
    # Split original text (not the already encoded text)
    parts = split_text(text, QR_SIZE_LIMIT)
    images_data = []
    
    for i, part in enumerate(parts):
        qr = qrcode.QRCode(box_size=12, border=5)
        qr.add_data(part)
        qr.make(fit=True)
        img = qr.make_image(fill="black", back_color="white")
        
        if client_ip:
            img = add_ip_to_image(img, client_ip)
        
        # Save image in-memory
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_data = buffer.getvalue()
        
        # Convert to data URL
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        data_url = f"data:image/png;base64,{image_base64}"
        images_data.append(data_url)
    
    return images_data

def get_hostname_by_ip(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return "Unknown Host"

def add_ip_to_image(img, ip):
    hostname = get_hostname_by_ip(ip)
    label = f"{ip} - {hostname}"
    
    # Ensure the image is in RGB mode.
    img = img.convert("RGB")
    
    # Get dimensions of the original QR image.
    width, height = img.size
    font = ImageFont.load_default()
    
    # Create a temporary image to measure text size.
    temp_img = Image.new("RGB", (width, height), "white")
    temp_draw = ImageDraw.Draw(temp_img)
    bbox = temp_draw.textbbox((0, 0), label, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # New image size: add space for the label.
    new_height = height + text_height + 10  # extra margin
    new_img = Image.new("RGB", (width, new_height), "white")
    
    # Paste the QR code using a 4-item box (left, upper, right, lower).
    new_img.paste(img, (0, 0, width, height))
    
    # Draw the label below the QR code.
    draw = ImageDraw.Draw(new_img)
    text_position = ((width - text_width) // 2, height + 5)
    draw.text(text_position, label, fill="black", font=font)
    
    return new_img

def decode_qr(image_paths):
    texts = []
    
    for image_path in image_paths:
        img = cv2.imread(image_path)
        decoded_objects = decode(img)
        
        for obj in decoded_objects:
            data = obj.data.decode()
            print(f"Decoded Data: {data}")  # Debug output
            
            if data.startswith(FLAG):
                try:
                    part_info, base64_text = data.split(":", 2)[1:]
                    part_num, total_parts = map(int, part_info.split("/"))
                    texts.append((part_num, total_parts, base64_text))
                except ValueError:
                    print(f"Skipping malformed QR data: {data}")
            else:
                texts.append((None, None, data))
    
    # Sort parts by their part number.
    texts = sorted(texts, key=lambda x: x[0] if x[0] is not None else 0)
    decoded_message = ""
    
    # Decode each part separately.
    for part in texts:
        if part[0] is not None:
            try:
                decoded_message += base64.b64decode(part[2]).decode('utf-8')
            except Exception as e:
                decoded_message += f"[Error decoding part {part[0]}]"
        else:
            decoded_message += part[2]
    
    return decoded_message

def decode_qr_images(images):
    texts = []
    
    for img in images:
        decoded_objects = decode(img)
        
        for obj in decoded_objects:
            try:
                data = obj.data.decode()
            except Exception as e:
                data = f"[Error decoding: {str(e)}]"
            print(f"Decoded Data: {data}")  # Debug output
            
            if data.startswith(FLAG):
                try:
                    part_info, base64_text = data.split(":", 2)[1:]
                    part_num, total_parts = map(int, part_info.split("/"))
                    texts.append((part_num, total_parts, base64_text))
                except ValueError:
                    print(f"Skipping malformed QR data: {data}")
            else:
                texts.append((None, None, data))
    
    # Process parts if available.
    if any(t[0] is not None for t in texts):
        texts.sort(key=lambda x: x[0])
        decoded_message = ""
        for part in texts:
            if part[0] is not None:
                try:
                    decoded_message += base64.b64decode(part[2]).decode('utf-8')
                except Exception as e:
                    decoded_message += f"[Error decoding part {part[0]}]"
            else:
                decoded_message += part[2]
        return decoded_message
    else:
        if texts:
            try:
                data = texts[0][2]
                missing_padding = len(data) % 4
                if missing_padding:
                    data += "=" * (4 - missing_padding)
                return base64.b64decode(data).decode('utf-8')
            except Exception as e:
                return f"Error decoding data: {str(e)}"
        return ""


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    text = request.form["text"]
    # Get the real client IP using X-Forwarded-For if available
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    
    # Generate in-memory QR images (data URLs)
    images_data = generate_qr(text, client_ip)
    
    # Create ZIP archive in-memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for idx, data_url in enumerate(images_data):
            # Extract Base64 part and decode
            image_base64 = data_url.split(",")[1]
            image_data = base64.b64decode(image_base64)
            zipf.writestr(f"qr_{idx}.png", image_data)
    zip_buffer.seek(0)
    
    # Encode ZIP file as Base64 to send to template
    zip_base64 = base64.b64encode(zip_buffer.getvalue()).decode('utf-8')
    
    # Pass images (data URLs) and zip file (as Base64 string) to template
    return render_template("submit.html", images=images_data, zip_file=zip_base64)

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        files = request.files.getlist("file")
        images = []  # Will hold image arrays
        
        for file in files:
            if file.filename:
                # Read file bytes into memory
                data = file.read()
                nparr = np.frombuffer(data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                images.append(img)
        
        # Decode QR codes from in-memory images
        decoded_text = decode_qr_images(images)
        return render_template("result.html", content=decoded_text)
    
    return render_template("upload.html")


@app.route("/download/<filename>")
def download(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename), as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
