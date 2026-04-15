from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from detector import generate_frames, camera_alerts
import cv2
import asyncio
from pydantic import BaseModel
import detector
import random
import smtplib
from email.message import EmailMessage
import time
import threading
import os
import string

class EmailData(BaseModel):
    email: str

class EmailOTPData(BaseModel):
    email: str
    otp: str

app = FastAPI()

# React Frontend-க்கு அனுமதி வழங்க CORS செட் செய்கிறோம்
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # உங்கள் React ஆப்-க்கு (localhost:5173) மட்டும் கொடுக்கலாம் 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

otp_storage = {} # தற்காலிகமாக OTP-ஐ சேமிக்க

class AISettings(BaseModel):
    storage_path: str
    retention_days: int

class DirRequest(BaseModel):
    path: str = ""

class CreateDirRequest(BaseModel):
    path: str
    new_folder: str

@app.on_event("startup")
def startup_event():
    # Server ஆன் ஆனதும் தானாகவே AI Model-ஐ பேக்ரவுண்டில் இயக்க தொடங்கும்
    pass # detector.start_background_camera("0") கமெண்ட் செய்யப்பட்டுள்ளது

@app.get("/")
async def read_root():
    return {"message": "Security AI Backend is Running!"}

@app.get("/video_feed")
def video_feed(url: str = "0", type: str = "processed"):
    # கேமரா ஃபிரேம்களை தொடர்ச்சியாக (Live Video) React-க்கு அனுப்ப
    return StreamingResponse(generate_frames(url, type), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/set_alert_email")
async def set_alert_email(data: EmailData):
    detector.ALERT_EMAIL_RECEIVER = data.email
    return {"status": "success", "message": f"Email Alerts linked to {data.email}"}

def send_email_background(email: str, otp: str):
    # Background-ல் சத்தமில்லாமல் ஈமெயில் அனுப்பும் ஃபங்ஷன்
    try:
        msg = EmailMessage()
        msg['Subject'] = "EyeQ Security Login OTP"
        msg['From'] = detector.GMAIL_SENDER
        msg['To'] = email
        msg.set_content(f"Welcome to EyeQ Security Dashboard.\n\nYour login OTP is: {otp}\n\nDo not share this with anyone.")
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as smtp:
            smtp.login(detector.GMAIL_SENDER, detector.GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        print(f"✅ OTP Email successfully sent to {email}")
    except Exception as e:
        print(f"Background Email Error: {str(e)}")

@app.post("/set_ai_settings")
async def set_ai_settings(settings: AISettings):
    detector.STORAGE_PATH = settings.storage_path
    detector.LOG_RETENTION_DAYS = settings.retention_days
    if not os.path.exists(detector.STORAGE_PATH):
        os.makedirs(detector.STORAGE_PATH, exist_ok=True)
    return {"status": "success", "message": "Settings updated successfully"}

@app.post("/get_directories")
async def get_directories(req: DirRequest):
    try:
        if os.name == 'nt' and not req.path:
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
            return {"status": "success", "path": "", "parent_path": "", "directories": drives, "is_root": True}
        
        search_path = req.path if req.path else ("/" if os.name != 'nt' else "C:\\")
        if not os.path.exists(search_path):
            return {"status": "error", "message": "Path does not exist"}
            
        parent_path = os.path.dirname(search_path)
        if search_path == parent_path and os.name == 'nt':
            parent_path = "" 
            
        dirs = []
        for item in os.listdir(search_path):
            item_path = os.path.join(search_path, item)
            if os.path.isdir(item_path):
                dirs.append(item)
                
        return {"status": "success", "path": search_path, "parent_path": parent_path, "directories": sorted(dirs), "is_root": False}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/create_directory")
async def create_directory(req: CreateDirRequest):
    try:
        new_path = os.path.join(req.path, req.new_folder)
        os.makedirs(new_path, exist_ok=True)
        return {"status": "success", "message": "Folder created successfully", "path": new_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/clips/{filename}")
async def get_clip(filename: str):
    file_path = os.path.join(detector.STORAGE_PATH, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "File not found"}

@app.post("/send_otp")
async def send_otp(data: EmailData):
    otp = str(random.randint(1000, 9999))
    
    # OTP மற்றும் அது காலாவதியாகும் நேரம் (தற்போதைய நேரம் + 300 வினாடிகள் = 5 நிமிடங்கள்)
    otp_storage[data.email] = {"otp": otp, "expires_at": time.time() + 300}
    
    # --- SEND EMAIL OTP ---
    if detector.GMAIL_SENDER and detector.GMAIL_APP_PASSWORD:
        threading.Thread(target=send_email_background, args=(data.email, otp), daemon=True).start()
        return {"status": "success", "message": f"OTP securely sent to {data.email}"}
    else:
        return {"status": "error", "message": "Email not configured in backend. Please set GMAIL credentials in detector.py"}

@app.post("/verify_otp")
async def verify_otp(data: EmailOTPData):
    record = otp_storage.get(data.email)
    if record:
        if time.time() > record["expires_at"]:
            del otp_storage[data.email] # 5 நிமிடம் முடிந்திருந்தால் அழித்துவிடுகிறோம்
            return {"status": "error", "message": "OTP has expired! Please request a new one."}
            
        if record["otp"] == data.otp:
            del otp_storage[data.email] # OTP சரிபார்க்கப்பட்டதும் அழித்துவிட வேண்டும்
            return {"status": "success", "message": "OTP verified!"}
            
    return {"status": "error", "message": "Invalid OTP! Please try again."}

@app.get("/alert_status")
async def alert_status():
    # அனைத்து கேமராக்களின் Alerts-ஐயும் ஒருங்கிணைத்து செக் செய்ய
    active_alerts = [data for data in camera_alerts.values() if isinstance(data, dict) and data.get("msg")]
    if active_alerts:
        return {"alert": active_alerts[0]["msg"], "clip": active_alerts[0]["clip"]}
        
    return {"alert": "", "clip": ""}

@app.post("/dismiss_alert")
async def dismiss_alert():
    # User UI-ல் Dismiss செய்தவுடன் எல்லா கேமராக்களின் ரெக்கார்டிங்கையும் உடனே நிறுத்த
    for cam_url in detector.running_cameras.keys():
        detector.force_dismiss_alerts[cam_url] = True
    return {"status": "success", "message": "Recording stopped"}

@app.get("/test_camera")
async def test_camera(url: str):
    # RTSP/HTTP கேமரா வேலை செய்கிறதா என நிஜமாகவே செக் செய்ய
    def check_cam():
        try:
            cam_source = int(url) if url.isdigit() else url
            cap = cv2.VideoCapture(cam_source)
            if cap.isOpened():
                ret, _ = cap.read()
                cap.release()
                return ret
            return False
        except Exception:
            return False
            
    is_valid = await asyncio.to_thread(check_cam)
    if is_valid:
        detector.start_background_camera(url) # புதிய கேமராவை பேக்ரவுண்டில் ஆன் செய்ய
    return {"status": "success" if is_valid else "error"}

@app.get("/stop_camera")
async def stop_camera_endpoint(url: str):
    # Frontend-ல் கேமராவை அழித்தால், Backend-லும் அதை நிறுத்த
    detector.stop_camera(url)
    return {"status": "success", "message": f"Camera {url} processing stopped"}

@app.get("/stop_all_cameras")
async def stop_all_cameras_endpoint():
    # லாகின் திரையில் இருக்கும்போது பேக்ரவுண்டில் ஓடும் அனைத்து கேமராக்களையும் நிறுத்த
    for url in list(detector.running_cameras.keys()):
        detector.stop_camera(url)
    detector.camera_alerts.clear() # பழைய அலர்ட்களை முழுமையாக அழிக்க
    return {"status": "success", "message": "All cameras stopped"}