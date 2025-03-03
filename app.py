from flask import Flask, render_template, request, send_file
import qrcode
import base64
import os
import cv2
import numpy as np
import zipfile
from PIL import Image
from pyzbar.pyzbar import decode

app = Flask(__name__)
UPLOAD_FOLDER = "static/qr_codes"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

QR_SIZE_LIMIT = 250  # Adjust based on actual QR limits
FLAG = "BASE64_QR"


def split_text(encoded_text, size_limit):
    # Split the already Base64 encoded text
    parts = [encoded_text[i:i+size_limit] for i in range(0, len(encoded_text), size_limit)]
    total = len(parts)
    return [f"{FLAG}:{i+1}/{total}:{part}" for i, part in enumerate(parts)]


def generate_qr(text, client_ip):
    # Split the original text into chunks.
    parts = [text[i:i+QR_SIZE_LIMIT] for i in range(0, len(text), QR_SIZE_LIMIT)]
    # Create QR data with independent base64 encoding.
    qr_parts = [
        f"{FLAG}:{i+1}/{len(parts)}:" + base64.b64encode(part.encode()).decode() 
        for i, part in enumerate(parts)
    ]
    
    qr_images = []
    for i, part in enumerate(qr_parts):
        qr = qrcode.QRCode(box_size=12, border=5)
        qr.add_data(part)
        qr.make(fit=True)
        img = qr.make_image(fill="black", back_color="white")
        
        if client_ip:
            img = add_ip_to_image(img, client_ip)
        
        filename = f"qr_{i}.png"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        img.save(filepath)
        qr_images.append(f"/static/qr_codes/{filename}")
    
    return qr_images




def add_ip_to_image(img, ip):
    # Convert PIL image to NumPy array (RGB to BGR for OpenCV)
    np_img = np.array(img.convert("RGB")) 
    np_img = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR) 

    # Define font and add text
    font = cv2.FONT_HERSHEY_SIMPLEX
    position = (10, np_img.shape[0] - 10)  # Bottom-left corner
    font_scale = 1
    font_color = (0, 0, 0)  # Black
    thickness = 2

    cv2.putText(np_img, ip, position, font, font_scale, font_color, thickness, cv2.LINE_AA)

    # Convert back to PIL image
    return Image.fromarray(cv2.cvtColor(np_img, cv2.COLOR_BGR2RGB))




# def decode_qr(image_paths):
#     texts = []

#     for image_path in image_paths:
#         img = cv2.imread(image_path)
#         decoded_objects = decode(img)

#         for obj in decoded_objects:
#             data = obj.data.decode()
#             print(f"Decoded Data: {data}")  # Debugging output

#             if data.startswith(FLAG):
#                 try:
#                     part_info, base64_text = data.split(":", 2)[1:]
#                     part_num, total_parts = map(int, part_info.split("/"))
#                     texts.append((part_num, total_parts, base64_text))
#                 except ValueError:
#                     print(f"Skipping malformed QR data: {data}")
#             else:
#                 texts.append((None, None, data))

#     # Debugging: Print all extracted parts
#     texts.sort()

#     if any(t[0] is not None for t in texts):
#         # Sort fragments by part number
#         texts.sort(key=lambda x: x[0])
#         # Concatenate all Base64 fragments
#         combined_base64 = "".join([part[2] for part in texts])
#         # Ensure proper padding
#         missing_padding = len(combined_base64) % 4
#         if missing_padding:
#             combined_base64 += "=" * (4 - missing_padding)
#         try:
#             decoded_message = base64.b64decode(combined_base64).decode('utf-8')
#         except Exception as e:
#             return f"Error decoding message: {str(e)}"
#         return decoded_message


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




@app.route("/")
def home():
    return render_template("index.html")



@app.route("/generate", methods=["POST"])
def generate():
    text = request.form["text"]
    client_ip = request.remote_addr
    qr_images = generate_qr(text, client_ip)  # This returns relative paths

    # Ensure correct absolute paths for ZIP creation
    abs_qr_images = [os.path.join(os.getcwd(), img.lstrip("/")) for img in qr_images]

    # Create ZIP file
    zip_filename = os.path.join(UPLOAD_FOLDER, "qr_codes.zip")
    with zipfile.ZipFile(zip_filename, "w") as zipf:
        for img_path in abs_qr_images:
            if os.path.exists(img_path):  # Ensure file exists
                zipf.write(img_path, os.path.basename(img_path))  # Store filename only
            else:
                print(f"Skipping missing file: {img_path}")  # Debugging

    return render_template("submit.html", images=qr_images, zip_file=f"/{zip_filename.replace(os.getcwd(), '').lstrip(os.sep)}")




@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        files = request.files.getlist("file")  # Allow multiple uploads
        filepaths = []

        for file in files:
            if file.filename:
                filepath = os.path.join(UPLOAD_FOLDER, file.filename)
                file.save(filepath)
                filepaths.append(filepath)

        # Decode all uploaded images together
        decoded_text = decode_qr(filepaths)
        return render_template("result.html", content=decoded_text)

    return render_template("upload.html")


@app.route("/download/<filename>")
def download(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename), as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
