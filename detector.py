import warnings
warnings.filterwarnings("ignore")

import os
# System level matrum C++ warnings-ah hide panna
os.environ['GLOG_minloglevel'] = '3'
os.environ['OPENCV_LOG_LEVEL'] = 'SILENT'
# MediaPipe / TensorFlow warnings-ah hide panna intha 2 lines use aagum
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
# OMP / libiomp5md.dll multiple copies warning மற்றும் கேமரா Crash-ஐ தடுக்க
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import logging
logging.getLogger('absl').setLevel(logging.ERROR) # MediaPipe Warnings-ஐ முழுமையாக மறைக்க
logging.getLogger('ultralytics').setLevel(logging.ERROR) # YOLO Warnings-ஐ மறைக்க

import onnxruntime as ort # ONNX Model-ஐ பயன்படுத்த (TF/Keras-க்கு பதிலாக)

import cv2
import numpy as np
import mediapipe as mp
import joblib
import time # State Machine timer-kaga add panniyachu
import csv # Landmark Dataset Save panna add panniyachu
import datetime # Time and Date-kaga add panniyachu
import threading # Video hang aagamal irukka
import smtplib
from email.message import EmailMessage

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles # கை, கால்களுக்கு தனி கலர் கொடுக்க

# Import Custom Modules we created
from visuals import draw_detailed_face, draw_detailed_hand, LEFT_HAND_LMS_DETAILED, RIGHT_HAND_LMS_DETAILED
from motion import MotionDetector
from ultralytics import YOLO # YOLOv8 for Highly Accurate Human Detection

import math
from itertools import combinations

# --- EMAIL SETUP (GMAIL) ---
ALERT_EMAIL_RECEIVER = "" # Frontend-லிருந்து லாகின் செய்த Email இங்கு வரும்
GMAIL_SENDER = "eyeq.company83@gmail.com" # ⚠️ உங்களது நிஜமான Gmail ஐடியை இங்கே கட்டாயம் எழுதவும்!
GMAIL_APP_PASSWORD = "qprwutwmyobhspju"   # உங்களின் 16-இலக்க App Password

# Dynamic AI Storage Config
STORAGE_PATH = "suspicious_events"
LOG_RETENTION_DAYS = 30

def send_modern_email(message, duration_mins):
    if not ALERT_EMAIL_RECEIVER or not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        return
    def send_task():
        try:
            msg = EmailMessage()
            msg['Subject'] = f"🚨 URGENT: Prolonged {message} Detected! 🚨"
            msg['From'] = GMAIL_SENDER
            msg['To'] = ALERT_EMAIL_RECEIVER
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: white; padding: 30px; border-radius: 10px; border-top: 5px solid #d30000; box-shadow: 0px 4px 10px rgba(0,0,0,0.1);">
                    <h2 style="color: #d30000; text-align: center;">⚠️ CRITICAL SECURITY WARNING ⚠️</h2>
                    <p style="font-size: 16px; color: #333;">Dear Admin,</p>
                    <p style="font-size: 16px; color: #333;">Our AI Security system has detected a continuous threat that requires your immediate attention.</p>
                    <div style="background-color: #ffeeee; padding: 15px; border-left: 5px solid #d30000; margin: 20px 0;">
                        <h3 style="margin: 0; color: #b30000;">Threat Type: {message}</h3>
                        <p style="margin: 5px 0 0 0; font-weight: bold; color: #555;">Continuous Duration: Over {duration_mins} minute(s)</p>
                        <p style="margin: 5px 0 0 0; color: #555;">Time: {datetime.datetime.now().strftime('%d-%b-%Y %I:%M %p')}</p>
                    </div>
                    <p style="font-size: 16px; color: #333;">The threat is still ongoing. Please check the live dashboard and take necessary actions immediately.</p>
                    <center style="margin-top: 20px;">
                        <a href="http://localhost:5173" style="display: inline-block; padding: 12px 24px; font-size: 16px; color: white; background-color: #d30000; text-decoration: none; border-radius: 5px; font-weight: bold;">View Live Dashboard</a>
                    </center>
                </div>
            </body>
            </html>
            """
            msg.add_alternative(html_content, subtype='html')
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
                smtp.send_message(msg)
        except Exception as e:
            print("Email Error:", e)
    threading.Thread(target=send_task).start()

def show_os_popup(message, duration_mins):
    """Linux/Cloud Safe Alert Logging"""
    def popup_thread():
        title = f"🚨 EyeQ Security Prolonged Alert ({duration_mins} Min) 🚨"
        text = f"CRITICAL WARNING!\n\n'{message}' has been continuously occurring for over {duration_mins} minutes!\n\nPlease check the dashboard/cameras immediately."
        print("="*50)
        print(title)
        print(text)
        print("="*50)
    threading.Thread(target=popup_thread, daemon=True).start()

def auto_cleanup_logs():
    """பழைய வீடியோக்கள் மற்றும் படங்களை குறிப்பிட்ட நாட்களுக்குப் பிறகு அழிக்க"""
    if LOG_RETENTION_DAYS <= 0 or not os.path.exists(STORAGE_PATH):
        return # 0 என்றால் அழிக்க வேண்டாம்
    try:
        now = time.time()
        for filename in os.listdir(STORAGE_PATH):
            file_path = os.path.join(STORAGE_PATH, filename)
            if os.path.isfile(file_path):
                if os.stat(file_path).st_mtime < now - (LOG_RETENTION_DAYS * 86400): # 86400 வினாடிகள் = 1 நாள்
                    os.remove(file_path)
                    print(f"🗑️ [AUTO-CLEANUP] Deleted old log file: {filename}")
    except Exception as e:
        print("Cleanup error:", e)

class CentroidTracker:
    def __init__(self, max_distance=150, max_disappeared=30):
        self.center_points = {}
        self.objects_data_dict = {} # Last known object data
        self.disappeared = {}       # Missing frames count
        self.id_count = 0
        self.max_distance = max_distance
        self.max_disappeared = max_disappeared # Box மறையாமல் இருக்க நினைவாற்றல்

    def update(self, objects_data):
        tracked_objects = []
        matched_ids = set()

        for obj in objects_data:
            x, y, w, h = obj[:4]
            # Center x, y kandupudikurom (Centroid)
            cx, cy = x + w // 2, y + h // 2
            
            same_object = False
            closest_id = None
            min_dist = self.max_distance
            
            for obj_id, pt in self.center_points.items():
                if obj_id in matched_ids:
                    continue
                dist = math.hypot(cx - pt[0], cy - pt[1])
                if dist < min_dist:
                    min_dist = dist
                    closest_id = obj_id
                    
            if closest_id is not None:
                self.center_points[closest_id] = (cx, cy)
                new_obj = [x, y, w, h, closest_id] + obj[4:]
                self.objects_data_dict[closest_id] = new_obj
                self.disappeared[closest_id] = 0
                tracked_objects.append(new_obj)
                matched_ids.add(closest_id)
                same_object = True
                    
            if not same_object:
                self.center_points[self.id_count] = (cx, cy)
                new_obj = [x, y, w, h, self.id_count] + obj[4:]
                self.objects_data_dict[self.id_count] = new_obj
                self.disappeared[self.id_count] = 0
                tracked_objects.append(new_obj)
                matched_ids.add(self.id_count)
                self.id_count += 1 # Internal ID strict-a increase aaganum (sorting-kaga)

        # ஆட்கள் கேமராவில் மறைந்தால் (அல்லது மிஸ் ஆனால்) பாக்ஸ்-ஐ உடனே அழிக்காமல் hold செய்வது
        for obj_id in list(self.center_points.keys()):
            if obj_id not in matched_ids:
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > self.max_disappeared:
                    self.center_points.pop(obj_id)
                    self.objects_data_dict.pop(obj_id)
                    self.disappeared.pop(obj_id)
                else:
                    # AI ஒரு நிமிடம் தவறவிட்டாலும், பழைய பாக்ஸ்-ஐயே ஸ்கிரீனில் தொடர்ந்து காண்பிக்கும்
                    tracked_objects.append(self.objects_data_dict[obj_id])

        return tracked_objects

camera_alerts = {} # Store alerts and clip filenames dynamically
latest_frames = {} # பேக்ரவுண்டில் ப்ராசஸ் ஆகும் ஃபிரேம்களை சேமிக்க
latest_clean_frames = {} # அசைவு மற்றும் AI பாக்ஸ் இல்லாத ஒரிஜினல் ஃபிரேம்களை சேமிக்க
active_threads = {} # ரன் ஆகிக்கொண்டிருக்கும் கேமராக்களின் லிஸ்ட்
running_cameras = {} # கேமராவை நிறுத்த ஒரு Flag
force_dismiss_alerts = {} # Dashboard-ல் இருந்து அலர்ட்டை நிறுத்த

def _run_camera_loop(camera_url=0):
    global camera_alerts, latest_frames, latest_clean_frames, running_cameras, force_dismiss_alerts
    camera_alerts[camera_url] = {"msg": "", "clip": ""} # Initialize empty alert and clip
    force_dismiss_alerts[camera_url] = False
    
    if not os.path.exists(STORAGE_PATH):
        os.makedirs(STORAGE_PATH, exist_ok=True)
        
    # Initialize CSV for Dataset Collection (ML Model Training-kaga)
    if not os.path.exists('action_dataset.csv'):
        with open('action_dataset.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([f"feature_{i}" for i in range(132)] + ["label"]) # 33 points * 4 coordinates + Label

    frame_count = 0
    fall_counter = 0
    
    # --- STATE MACHINE SETUP ---
    last_motion_time = 0  # AI starts as Idle
    person_histories = {} # LSTM sequence-க்காக ஒவ்வொரு நபரின் history-ஐயும் சேமிக்க
    violence_streak = {}  # தொடர்ச்சியாக 26 படங்களுக்கு சண்டை என கணித்தால் அலர்ட் கொடுக்க
    fall_streak = {}      # தொடர்ச்சியாக 26 படங்களுக்கு கீழே விழுந்தால் அலர்ட் கொடுக்க
    current_alert = ""      # Dynamic alert tracking
    alert_start_time = 0    # When the current alert started
    email_sent_1min = False # Email flag
    popup_sent_2min = False # Popup flag
    no_alert_frames = 0     # Flicker prevention
    prev_wrists = {}
    video_writer = None     # Video Record செய்வதற்கான ஆப்ஜெக்ட்
    current_clip_name = ""  # தற்போதைய வீடியோவின் பெயர்

    # --- LSTM Data Collection Setup ---
    recording_state = {"action": None, "frames": [], "person_id_to_record": None}
    SEQUENCE_LENGTH = 30
    tracker = CentroidTracker(max_distance=150, max_disappeared=30) # Box தொடர்ந்து இருக்க

    # Load Custom ML Models (Separate Fall and Violence)
    try:
        clf_fall = joblib.load('fall_model.pkl')
        clf_viol = joblib.load('violence_model.pkl')
        print("ML Models 'fall_model.pkl' & 'violence_model.pkl' loaded successfully.")
    except FileNotFoundError:
        print("Warning: ML models not found! Running in Rule-Based Mode (No ML).")
        clf_fall = None
        clf_viol = None
        
    # Load LSTM Video Model (Moments calculation)
    try:
        lstm_session = ort.InferenceSession('action_model.onnx')
        lstm_input_name = lstm_session.get_inputs()[0].name
        lstm_actions = ["fall", "violence", "normal"] # train_lstm.py-ல் உள்ளபடி 3 classes ஆக மாற்றப்பட்டுள்ளது
        print(f"[SUCCESS] ONNX LSTM Model connected with {len(lstm_actions)} classes: {lstm_actions}!")
    except Exception:
        print("Warning: 'action_model.onnx' not found. Fallback to Images.")
        lstm_session = None

    # ஒவ்வொரு நபருக்கும் தனித்தனி நிறங்களை ஒதுக்க ஒரு Color Palette (BGR Format)
    PERSON_COLORS = [
        (255, 255, 0),   # Cyan (சியான்)
        (255, 0, 255),   # Magenta (மெஜந்தா)
        (0, 255, 255),   # Yellow (மஞ்சள்)
        (255, 100, 0),   # Blue-ish (நீலம்)
        (0, 165, 255),   # Orange (ஆரஞ்சு)
        (128, 0, 128),   # Purple (ஊதா)
        (0, 200, 100)    # Greenish (பச்சை)
    ]

    custom_yolo_path = 'runs/detect/strict_human_model/weights/best.pt'
    if os.path.exists(custom_yolo_path):
        print("Loading Custom Trained YOLO Model for STRICT Human Detection...")
        yolo_model = YOLO(custom_yolo_path)
    else:
        print("Loading YOLOv8n (Nano) AI for Ultra-Fast Human Detection (Lag Fix)...")
        yolo_model = YOLO('yolov8n.pt') # Lag-ஐ குறைக்க yolov8m லிருந்து yolov8n ஆக மாற்றப்பட்டுள்ளது

    motion_detector = MotionDetector() # Initialize Motion Detector

    # Windows-la OpenCV camera warnings-a thadukka CAP_DSHOW use pandrom
    if isinstance(camera_url, int) or (isinstance(camera_url, str) and camera_url.isdigit()):
        cap = cv2.VideoCapture(int(camera_url), cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(camera_url)
    
    # லைவ் கேமராவில் ஏற்படும் 'Delay' (Lag)-ஐ தடுத்து, Real-time ஆக மாற்ற
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # பழைய ஃபிரேம்களை தடுத்து லேட்டஸ்ட் ஃபிரேமை மட்டும் எடுக்க
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640) # AI வேகமாக ஸ்கேன் செய்ய Resolution செட் செய்தல்
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 60) # கேமராவின் அதிகபட்ச வேகத்தை பயன்படுத்த
    
    # 1. Multi-Person Pose Estimators (Dict)
    # ஒவ்வொருவருக்கும் தனித்தனி Pose Model (கைகள் மாறுவதைத் தடுக்க)
    pose_estimators = {}

    print("System Starting... Please wait for background training.")
    system_start_time = time.time()
    WARMUP_SECONDS = 5.0 # Refresh ஆனதும் 5 வினாடி கழித்து Detect செய்ய

    running_cameras[camera_url] = True

    while running_cameras.get(camera_url, False):
        ret, frame = cap.read()
        if not ret or frame is None:
            print(f"[WARNING] Camera {camera_url} feed empty! Retrying in 2 seconds...")
            time.sleep(2)
            cap.reconnect()
            continue
            
        # --- CLEAN RAW FRAME (WITHOUT ANY DRAWINGS) ---
        raw_frame = frame.copy()
        
        # --- NORMAL FRAME (WITHOUT NIGHT VISION) ---
        normal_frame = frame.copy()
            
        frame_count += 1
        
        # --- FRAME SKIPPING FOR LOW-END LAPTOPS (8GB RAM / i3) ---
        # 3 ஃபிரேம்களுக்கு ஒருமுறை மட்டும் AI-ஐ ரன் செய்தால் போதும் (CPU சுமை 70% குறையும்)
        if frame_count % 3 != 0:
            continue
        
        # --- LOW LIGHT / NIGHT MODE ENHANCEMENT ---
        # வெளிச்சம் குறைவாக இருந்தால் ஆட்டோமேட்டிக்காக பிரைட்னஸ் மற்றும் கான்ட்ராஸ்டை அதிகரிக்கும்
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        avg_brightness = np.mean(gray_frame)
        if avg_brightness < 60: # மிகவும் இருட்டாக இருந்தால் (சராசரி வெளிச்சம் 60-க்கு கீழ்)
            frame = cv2.convertScaleAbs(frame, alpha=2.5, beta=50) # Brightness & Contrast Boost
            cv2.putText(frame, "* Night Vision Active *", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        elif avg_brightness > 180: # வெளிச்சம் அதிகமாக இருந்தால் (Over Light / Glare)
            # Brightness-ஐ குறைத்து ஆட்களை தெளிவாக காட்ட Alpha & Beta அளவுகளை குறைத்தல்
            frame = cv2.convertScaleAbs(frame, alpha=0.8, beta=-40) 
            cv2.putText(frame, "* Anti-Glare Active *", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # --- MOTION DETECTION ---
        motion_bboxes, fgMask, motion_warming_up = motion_detector.process_frame(frame)
        
        # --- STATE MACHINE: STEP 1 - YOLOv8 Human Detection ---
        # Fan, kaathu, screen ellam ignore aagidum. "Person" (Class 0) mattum thaan edukkum.
        results = yolo_model(frame, classes=[0], verbose=False)
        
        active_bboxes = []
        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                if conf > 0.45: # 45% - துல்லியத்தை அதிகரிக்க (பொய்யான மனித உருவங்களை தடுக்க)
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # --- STATIC PHOTO & POSTER FILTER ---
                    # YOLO கண்டுபிடித்த பாக்ஸ் உள்ளே நிஜமாகவே அசைவு (Motion) இருக்கிறதா என செக் செய்கிறோம்
                    box_mask = fgMask[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
                    moving_pixels = cv2.countNonZero(box_mask)
                    box_area = max(1, (x2 - x1) * (y2 - y1))
                    motion_percentage = (moving_pixels / box_area) * 100
                    
                    # அசைவு இருந்தாலும் இல்லாவிட்டாலும் எப்பொழுதும் மனிதனை கண்டுபிடிக்க (Always ON Model)
                    is_real_human = True
                                
                    if is_real_human:
                        active_bboxes.append([x1, y1, x2 - x1, y2 - y1]) # x, y, w, h format
                    
        # ஒரே நபருக்கு 2 பாக்ஸ்கள் விழுவதைத் தடுக்க (Remove Duplicate Overlapping Boxes)
        filtered_bboxes = []
        for box1 in active_bboxes:
            x1, y1, w1, h1 = box1
            cx1, cy1 = x1 + w1 // 2, y1 + h1 // 2
            is_duplicate = False
            for box2 in filtered_bboxes:
                x2, y2, w2, h2 = box2
                # ஒரு பாக்ஸின் மையம் இன்னொரு பாக்ஸிற்குள் இருந்தால் அது Duplicate
                if x2 < cx1 < x2 + w2 and y2 < cy1 < y2 + h2:
                    is_duplicate = True
                    break
            if not is_duplicate:
                filtered_bboxes.append(box1)
                
        # --- FAST WARM-UP TIMER ---
        elapsed_time = time.time() - system_start_time
        warmup_time_left = max(0.0, WARMUP_SECONDS - elapsed_time)
        is_warming_up = warmup_time_left > 0 # 3 வினாடி நேரம் மட்டும் Warm-up
        
        if not is_warming_up and len(filtered_bboxes) > 0:
            last_motion_time = time.time() # Timer-ah reset pannu

        # --- CLEAN HUD (Heads Up Display) SETUP ---
        hud_info = []
        alert_msg = ""
        box_color = (0, 255, 0)
        action_text = ""
        
        is_ai_analyzing = True # எப்பொழுதும் AI இயங்கிக்கொண்டே இருக்க (Always ON Mode)

        if is_warming_up:
            hud_info.append(f"Status: Camera Warming Up... ({warmup_time_left:.1f}s left)")
        elif is_ai_analyzing:
            # --- MULTI-PERSON TRACKING ---
            # YOLO boxes-ah vachu stable ID kuduka tracker-ah use pandrom
            tracked_persons = tracker.update(filtered_bboxes) # Filtered boxes-ஐ அனுப்புகிறோம்
            
            # Internal ID vachu sort pandrom, appo thaan aala dynamic-a 1, 2, 3 nu number panna mudiyum
            tracked_persons.sort(key=lambda x: x[4])
            
            persons_with_info = [] # Process panna data-va inga serthu vekka

            any_human_falling = False
            
            # கேமராவை விட்டு வெளியேறிய நபர்களின் Pose Model-ஐ அழித்து மெமரியை மிச்சப்படுத்த
            active_ids = [p[4] for p in tracked_persons]
            for p_id in list(pose_estimators.keys()):
                if p_id not in active_ids:
                    pose_estimators[p_id].close()
                    del pose_estimators[p_id]
                    if p_id in person_histories:
                        del person_histories[p_id] # மெமரியை கிளியர் செய்ய
                    if p_id in violence_streak:
                        del violence_streak[p_id]
                    if p_id in fall_streak:
                        del fall_streak[p_id]
                        
            # --- FIX: Person மிஸ் ஆனால் ஸ்டக் ஆகாமல் இருக்க ரெக்கார்டிங்-ஐ ரீசெட் செய்ய ---
            if recording_state["action"] and recording_state["person_id_to_record"] not in active_ids:
                recording_state = {"action": None, "frames": [], "person_id_to_record": None}

            # --- MULTI-PERSON PROCESSING LOOP ---
            for index, person_data in enumerate(tracked_persons): # STEP 1: INDIVIDUAL ANALYSIS
                x, y, w, h, person_id = person_data
                
                display_id = index + 1 # Dynamic ID (1st varavaru 1, 2nd varavaru 2)
                pad = 5 # 20-ல் இருந்து 5 ஆக குறைக்கப்பட்டுள்ளது (பக்கத்து ஆளின் கை வருவதை தடுக்க)
                y1, y2 = max(0, y-pad), min(frame.shape[0], y+h+pad)
                x1, x2 = max(0, x-pad), min(frame.shape[1], x+w+pad)
                
                roi = frame[y1:y2, x1:x2]
                normal_roi = normal_frame[y1:y2, x1:x2]
                
                if roi.size > 0:
                    # --- Image Pre-processing (Light-ah handle panna) ---
                    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
                    l, a, b = cv2.split(lab)
                    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
                    cl = clahe.apply(l)
                    limg = cv2.merge((cl, a, b))
                    final_frame = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
                    final_frame = cv2.GaussianBlur(final_frame, (3, 3), 0)

                    # ஒவ்வொரு நபருக்கும் (person_id) தனித்தனி Pose Model
                    if person_id not in pose_estimators:
                        pose_estimators[person_id] = mp_pose.Pose(
                            static_image_mode=False, 
                            model_complexity=0, # 0 = Lightning Fast Mode (மிகவும் வேகம்)
                            min_detection_confidence=0.5, 
                            min_tracking_confidence=0.5
                        )

                    results = pose_estimators[person_id].process(cv2.cvtColor(final_frame, cv2.COLOR_BGR2RGB))

                    if results.pose_landmarks:
                        landmarks = results.pose_landmarks.landmark
                        
                        # --- STRICT HUMAN STRUCTURE CHECK ---
                        # குறைந்தது 8 உடல் பாகங்களாவது (கண்கள், கைகள், கால்கள்) 40% மேல் தெளிவாகத் தெரிந்தால் மட்டுமே மனிதன் என உறுதி செய்ய
                        visible_parts_count = sum(1 for lm in landmarks if lm.visibility > 0.4)
                        
                        # தோள்பட்டை (Shoulder) அல்லது இடுப்பு (Hip) ஏதேனும் ஒன்று தெரிந்தால் தான் அது முறையான உடல் அமைப்பு
                        has_body_structure = (landmarks[11].visibility > 0.4 or landmarks[12].visibility > 0.4 or 
                                              landmarks[23].visibility > 0.4 or landmarks[24].visibility > 0.4)
                        
                        if visible_parts_count < 8 or not has_body_structure:
                            continue # சரியான மனித உருவம் இல்லை என்றால் Bounding Box வரையக்கூடாது
                        
                        # --- ACTION RECOGNITION LOGIC (நிறத்தை முதலில் எடுக்க இதை மேலே கொண்டு வந்துள்ளோம்) ---
                        lm_data = [val for lm in landmarks for val in (lm.x, lm.y, lm.z, lm.visibility)]
                        
                        # கடந்த 30 Frames-ஐ நியாபகம் வைத்துக்கொள்ளும் லாஜிக் (LSTM-க்காக)
                        if person_id not in person_histories:
                            person_histories[person_id] = []
                        person_histories[person_id].append(lm_data)
                        if len(person_histories[person_id]) > SEQUENCE_LENGTH:
                            person_histories[person_id].pop(0) # பழையதை நீக்கி புதியதை சேர்

                        # நபரைக் குறிக்கும் ID-ஐ வைத்து அவருக்கு ஒரு நிரந்தர நிறத்தை தேர்ந்தெடுத்தல்
                        person_color = PERSON_COLORS[person_id % len(PERSON_COLORS)]

                        # --- ML Model Predictions (Fall & Violence தனித்தனியாக) ---
                        current_is_fall = False
                        current_is_viol = False
                        
                        # 1. Static Image Checking (Single Frame Backup)
                        if clf_fall is not None:
                            current_is_fall = (clf_fall.predict([lm_data])[0] == 1)
                        if clf_viol is not None and lstm_session is None:
                            # LSTM மாடல் இருந்தால், இமேஜ் மாடலின் Violence-ஐ தவிர்க்கவும் (தவறான அலர்ட்டை தடுக்க)
                            current_is_viol = (clf_viol.predict([lm_data])[0] == 1)
                            
                        # 2. LSTM Movement Sequence Check (Highly Accurate!)
                        if lstm_session is not None and len(person_histories[person_id]) == SEQUENCE_LENGTH:
                            input_seq = np.expand_dims(person_histories[person_id], axis=0).astype(np.float32)
                            pred = lstm_session.run(None, {lstm_input_name: input_seq})[0][0]
                            action_idx = np.argmax(pred)
                            
                            # --- AI Motion Speed Filter (Updated for Strict Accuracy) ---
                            # Variance-ஐ பயன்படுத்தினால் (நடந்து வரும்போது) தவறாக அலர்ட் வரும்.
                            # எனவே கடந்த 20 ஃபிரேம்களில் கைகள் எப்போதாவது 'அதிவேகமாக' (Punch/Slap) சீறிப்பாய்ந்துள்ளதா என செக் செய்கிறோம்.
                            seq_data = np.array(person_histories[person_id])
                            
                            max_lw_speed = 0
                            max_rw_speed = 0
                            for i in range(-20, 0):
                                lw_s = math.hypot(seq_data[i, 60] - seq_data[i-5, 60], seq_data[i, 61] - seq_data[i-5, 61])
                                rw_s = math.hypot(seq_data[i, 64] - seq_data[i-5, 64], seq_data[i, 65] - seq_data[i-5, 65])
                                if lw_s > max_lw_speed: max_lw_speed = lw_s
                                if rw_s > max_rw_speed: max_rw_speed = rw_s
                                
                            # கைகள் சாதாரணமாக அசைவதை சண்டை என எடுத்துக்கொள்ளக் கூடாது (Strict Filter)
                            is_glitch = (max_lw_speed >= 0.50) or (max_rw_speed >= 0.50) # அதிவேகமான Punch-களை அனுமதிக்க அளவை அதிகரித்துள்ளோம்
                            is_hands_moving_fast = (0.08 < max_lw_speed < 0.50) or (0.08 < max_rw_speed < 0.50) # சாதாரணமாக நடக்கும்போது கைகள் அசைவதை தவிர்க்க 0.05-ஐ 0.08 ஆக்கியுள்ளோம்

                            if is_glitch:
                                current_is_viol = False # AI குழம்பியிருந்தால் சண்டை எனத் தவறாக அலர்ட் தரக் கூடாது
                            elif lstm_actions[action_idx] == "violence" and pred[action_idx] > 0.85: # Confidence-ஐ 75% இலிருந்து 85% ஆக உயர்த்தியுள்ளோம்
                                if is_hands_moving_fast:
                                    current_is_viol = True 
                            elif lstm_actions[action_idx] == "fall" and pred[action_idx] > 0.80: # Fall Confidence-ஐ 80% ஆக்கியுள்ளோம்
                                hip_y_start = seq_data[0, 97]
                                hip_y_end = seq_data[-1, 97]
                                if (hip_y_end - hip_y_start) > 0.05: # Fall என்றால் உடல் வேகமாக கீழே இறங்க வேண்டும்
                                    current_is_fall = True

                        # --- 26 Continuous Pictures Check ---
                        if person_id not in violence_streak:
                            violence_streak[person_id] = 0
                        if person_id not in fall_streak:
                            fall_streak[person_id] = 0
                            
                        # --- UNCONSCIOUS FALL LOGIC (User's Idea) ---
                        # நபர் கீழே விழுந்து (w > h) அசைவே இல்லாமல் (Motion Mask Black) இருந்தால்
                        box_mask = fgMask[max(0, y):min(frame.shape[0], y+h), max(0, x):min(frame.shape[1], x+w)]
                        person_motion = (cv2.countNonZero(box_mask) / max(1, w * h)) * 100
                        is_motionless = person_motion < 1.0 # அசைவு இல்லை (Motion mask black)
                        is_lying_down = (w > h * 0.95) # ஷூ லேஸ் கட்டும்போது அல்லது முட்டி போடும்போது Fall எனத் தவறாக வருவதை தடுக்க 0.95 ஆக்கியுள்ளோம்
                        
                        if is_lying_down and is_motionless:
                            current_is_fall = True
                            fall_streak[person_id] += 2 # மயக்கத்தில் இருப்பதால் வேகமாக அலர்ட் கொடுக்க
                            
                        if current_is_viol:
                            violence_streak[person_id] += 2 # வேகமாக அலர்ட் ஆக
                        else:
                            violence_streak[person_id] = max(0, violence_streak[person_id] - 1)
                            
                        if current_is_fall:
                            fall_streak[person_id] += 2 
                        else:
                            fall_streak[person_id] = max(0, fall_streak[person_id] - 1)
                            
                        is_viol_ml = (violence_streak[person_id] >= 10) # 12 லிருந்து 10 ஆக குறைக்கப்பட்டுள்ளது
                        is_fall_ml = (fall_streak[person_id] >= 10) # 15 லிருந்து 10 ஆக குறைக்கப்பட்டுள்ளது

                        # Text & Color Setup
                        if clf_fall is None and lstm_session is None:
                            action_text = "Tracking (No ML)"
                            box_color = person_color
                        elif is_fall_ml:
                            action_text = "Unconscious Fall!" if (is_lying_down and is_motionless) else "Fall Detected"
                            box_color = (0, 0, 255)
                        elif is_viol_ml:
                            action_text = "Aggressive" # தனியாக இருக்கும்போது மாடல் வேலை செய்வதைக் காட்ட
                            box_color = (0, 165, 255) # Orange Color
                        elif lstm_session is not None and len(person_histories[person_id]) < SEQUENCE_LENGTH:
                            action_text = "Analyzing..." # முதல் 30 frames டேட்டா சேரும் வரை
                            box_color = person_color
                        else:
                            action_text = "Normal"
                            box_color = person_color

                        # Fall Detection (Rule-based + ML Combo)
                        nose_lm = landmarks[mp_pose.PoseLandmark.NOSE.value]
                        knee_lm = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
                        # மூக்கு முட்டியை விட கீழே சென்றால் மட்டுமே Rule-based Fall (ஷூ லேஸ் கட்டும்போது தப்பாக அலர்ட் வருவதை தடுக்க)
                        local_fall = (nose_lm.visibility > 0.5 and knee_lm.visibility > 0.5 and nose_lm.y > knee_lm.y)
                        if (is_lying_down and is_motionless) or local_fall or is_fall_ml:
                            any_human_falling = True

                        # எல்லா தகவல்களையும் வரைவதற்காக (Drawing) சேமித்தல்
                        persons_with_info.append({
                            'x': x, 'y': y, 'w': w, 'h': h, 'person_id': person_id, 'display_id': display_id,
                            'action_text': action_text, 'box_color': box_color, 'is_viol_ml': is_viol_ml,
                            'roi': roi, 'normal_roi': normal_roi, 'pose_results': results, 'landmarks': landmarks,
                            'roi_coords': (x1, y1), 'lm_data': lm_data
                        })
                            
            # --- STEP 2: INTERACTION ANALYSIS (VIOLENCE BETWEEN TWO PEOPLE) ---
            if len(persons_with_info) >= 2:
                # இரண்டு பாக்ஸ்கள் ஒன்றுடன் ஒன்று மோதுகிறதா என சரிபார்க்கும் ஃபங்ஷன்
                def boxes_overlap(p1, p2):
                    x1, y1, w1, h1 = p1['x'], p1['y'], p1['w'], p1['h']
                    x2, y2, w2, h2 = p2['x'], p2['y'], p2['w'], p2['h']
                    
                    # Basic Intersection Check
                    if (x1 + w1 < x2 or x2 + w2 < x1 or y1 + h1 < y2 or y2 + h2 < y1):
                        return False
                        
                    # Deep Overlap Check (லேசாக உரசினால் சண்டை கிடையாது, Area கணக்கீடு)
                    ix1, iy1 = max(x1, x2), max(y1, y2)
                    ix2, iy2 = min(x1 + w1, x2 + w2), min(y1 + h1, y2 + h2)
                    inter_area = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                    
                    min_area = min(w1 * h1, w2 * h2)
                    # குறைந்தபட்சம் 20% பாக்ஸ் ஒன்றோடு ஒன்று கலந்திருந்தால் மட்டுமே Overlap
                    return (inter_area / min_area) > 0.20

                for p1, p2 in combinations(persons_with_info, 2):
                    if boxes_overlap(p1, p2):
                        if p1['is_viol_ml'] or p2['is_viol_ml']:
                            # பாக்ஸ்கள் மோதினால் மற்றும் நிஜமாகவே கைகளை அசைத்து சண்டையிட்டால்
                            p1['action_text'] = "Fighting!"
                            p2['action_text'] = "Fighting!"
                            p1['box_color'] = (0, 0, 255) # Red
                            p2['box_color'] = (0, 0, 255) # Red
                            if not alert_msg:
                                alert_msg = "VIOLENCE DETECTED!"
                        else:
                            # சும்மா பக்கத்தில் நின்றால்
                            if p1['action_text'] == "Normal": p1['action_text'] = "Standing Close"
                            if p2['action_text'] == "Normal": p2['action_text'] = "Standing Close"

            # --- STEP 3: DRAWING LOOP (using the processed info) ---
            for p_info in persons_with_info:
                x, y, w, h, person_id, display_id = p_info['x'], p_info['y'], p_info['w'], p_info['h'], p_info['person_id'], p_info['display_id']
                action_text, box_color = p_info['action_text'], p_info['box_color']
                
                # --- SKELETON COLORS (Unique for each person and body parts) ---
                # நபரின் நிரந்தர நிறத்தை எடுக்கிறோம்
                p_color = PERSON_COLORS[person_id % len(PERSON_COLORS)]
                b, g, r = p_color
                
                # இடது மற்றும் வலது பாகங்களுக்கு தனித்தனி வண்ணங்கள் (Vibrant Colors)
                left_color = (b, g, r)               # இடது கை, கால்களுக்கு நபரின் ஒரிஜினல் நிறம்
                right_color = (g, r, b)              # வலது கை, கால்களுக்கு மாறுபட்ட (Channel Swapped) நிறம்
                center_color = (255, 255, 255)       # முகத்தின் நடுப்பகுதிக்கு வெள்ளை
                
                left_points = {1, 2, 3, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31}
                right_points = {4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32}

                # 1. எலும்பு மூட்டுகளுக்கான (Points) நிறங்கள்
                custom_lm_style = {}
                for i in range(33):
                    if i in left_points:
                        custom_lm_style[i] = mp_drawing.DrawingSpec(color=left_color, circle_radius=3, thickness=-1)
                    elif i in right_points:
                        custom_lm_style[i] = mp_drawing.DrawingSpec(color=right_color, circle_radius=3, thickness=-1)
                    else: # Nose(0) & Body
                        custom_lm_style[i] = mp_drawing.DrawingSpec(color=center_color, circle_radius=4, thickness=-1)

                # 2. எலும்புகளை இணைக்கும் கோடுகளுக்கான (Lines) நிறங்கள்
                custom_conn_style = {}
                for connection in mp_pose.POSE_CONNECTIONS:
                    start_idx, end_idx = connection
                    if start_idx in left_points and end_idx in left_points:
                        custom_conn_style[connection] = mp_drawing.DrawingSpec(color=left_color, thickness=2)
                    elif start_idx in right_points and end_idx in right_points:
                        custom_conn_style[connection] = mp_drawing.DrawingSpec(color=right_color, thickness=2)
                    else: # Cross-body connections
                        custom_conn_style[connection] = mp_drawing.DrawingSpec(color=center_color, thickness=2)

                mp_drawing.draw_landmarks(
                    p_info['roi'], p_info['pose_results'].pose_landmarks, mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=custom_lm_style,
                    connection_drawing_spec=custom_conn_style
                )
                mp_drawing.draw_landmarks(
                    p_info['normal_roi'], p_info['pose_results'].pose_landmarks, mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=custom_lm_style,
                    connection_drawing_spec=custom_conn_style
                )
                
                h_roi, w_roi = p_info['roi'].shape[:2]
                x1_roi, y1_roi = p_info['roi_coords']
                
                # --- DETAILED HAND & FACE DRAWING ---
                draw_detailed_hand(frame, p_info['landmarks'], LEFT_HAND_LMS_DETAILED, mp_pose.PoseLandmark.LEFT_WRIST.value, (h_roi, w_roi), (x1_roi, y1_roi))
                draw_detailed_hand(frame, p_info['landmarks'], RIGHT_HAND_LMS_DETAILED, mp_pose.PoseLandmark.RIGHT_WRIST.value, (h_roi, w_roi), (x1_roi, y1_roi))
                draw_detailed_face(frame, p_info['landmarks'], (h_roi, w_roi), (x1_roi, y1_roi))
                draw_detailed_hand(normal_frame, p_info['landmarks'], LEFT_HAND_LMS_DETAILED, mp_pose.PoseLandmark.LEFT_WRIST.value, (h_roi, w_roi), (x1_roi, y1_roi))
                draw_detailed_hand(normal_frame, p_info['landmarks'], RIGHT_HAND_LMS_DETAILED, mp_pose.PoseLandmark.RIGHT_WRIST.value, (h_roi, w_roi), (x1_roi, y1_roi))
                draw_detailed_face(normal_frame, p_info['landmarks'], (h_roi, w_roi), (x1_roi, y1_roi))
                
                # --- Bounding Box & Text ---
                cv2.rectangle(frame, (x, y), (x+w, y+h), box_color, 2)
                cv2.putText(frame, f"Human {display_id} ({action_text})", (x, max(20, y-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, box_color, 2)
                cv2.rectangle(normal_frame, (x, y), (x+w, y+h), box_color, 2)
                cv2.putText(normal_frame, f"Human {display_id} ({action_text})", (x, max(20, y-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, box_color, 2)

                # --- DATA COLLECTION (SEQUENCE RECORDING) ---
                if recording_state["action"] and recording_state["person_id_to_record"] == person_id:
                    recording_state["frames"].append(p_info['lm_data'])
                    if len(recording_state["frames"]) >= SEQUENCE_LENGTH:
                        sequence_data = np.array(recording_state["frames"])
                        data_path = os.path.join("Sophisticated_LSTM_Data", recording_state["action"])
                        os.makedirs(data_path, exist_ok=True)
                        sequence_num = len(os.listdir(data_path))
                        file_path = os.path.join(data_path, f"{sequence_num}.npy")
                        np.save(file_path, sequence_data)
                        print(f"--- SAVED sequence to {file_path} ---")
                        recording_state = {"action": None, "frames": [], "person_id_to_record": None}

                hud_info.append(f"H{display_id} Action: {action_text}")

                if box_color == (0, 0, 255) and not alert_msg:
                    alert_msg = f"{action_text.upper()} ALERT!!!"
                            
            # Global Fall Logic for all humans
            if any_human_falling:
                fall_counter += 2
                if fall_counter >= 10: 
                    alert_msg = "FALL DETECTED!"
            else:
                fall_counter = max(0, fall_counter - 1) # Flicker-ஐ தவிர்க்க
        else:
            hud_info.append("Status: Monitoring (AI Idle)")
            active_bboxes = [] # Clear bounding boxes when AI is idle
            tracked_persons = [] # Tracker-ayum clear pannu
            fall_counter = 0
            prev_wrists = {}
            # மெமரியை மிச்சப்படுத்த Pose Model-களை அழிக்கவும்
            for p in pose_estimators.values():
                p.close()
            pose_estimators.clear()
            person_histories.clear()
            violence_streak.clear()
            fall_streak.clear()
            recording_state = {"action": None, "frames": [], "person_id_to_record": None}

        # --- DRAW CLEAN UI AND ALERTS ---
        if hud_info:
            # Draw Solid Dark Background to make text readable (No clutter)
            hud_h = len(hud_info) * 30 + 15
            cv2.rectangle(frame, (10, 10), (350, hud_h), (0, 0, 0), -1)
            cv2.rectangle(normal_frame, (10, 10), (350, hud_h), (0, 0, 0), -1)
            for i, text in enumerate(hud_info):
                cv2.putText(frame, text, (20, 40 + i * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(normal_frame, text, (20, 40 + i * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
        # --- DYNAMIC ALERT LOGIC (IMMEDIATE START & STOP, PROLONGED WARNINGS) ---
        if force_dismiss_alerts.get(camera_url, False):
            # யூசர் திரையில் தோன்றும் Warning-ஐ Dismiss செய்தால் உடனே ரெக்கார்டிங்கை நிறுத்த
            if video_writer is not None:
                video_writer.release()
                video_writer = None
                print(f"🛑 [INFO] Recording stopped manually via Dashboard: {current_clip_name}")
            
            # அலர்ட் உடனடியாக மீண்டும் வராமல் இருக்க ஒரு சிறிய இடைவெளி (Cooldown)
            alert_msg = ""
            current_alert = ""
            no_alert_frames = 61
            fall_counter = -30
            for p_id in list(fall_streak.keys()): fall_streak[p_id] = -30
            for p_id in list(violence_streak.keys()): violence_streak[p_id] = -30
            
            camera_alerts[camera_url] = {"msg": "", "clip": ""}
            force_dismiss_alerts[camera_url] = False

        if alert_msg != "":
            no_alert_frames = 0
            if current_alert != alert_msg:
                current_alert = alert_msg
                alert_start_time = time.time()
                email_sent_1min = False
                popup_sent_2min = False
                
                # --- START RECORDING ACTUAL VIDEO CLIP ---
                if video_writer is None:
                    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    current_clip_name = f"alert_{timestamp_str}.mp4"
                    filepath = os.path.join(STORAGE_PATH, current_clip_name)
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v') # Universal MP4 format for browser
                    h_f, w_f = frame.shape[:2]
                    video_writer = cv2.VideoWriter(filepath, fourcc, 20.0, (w_f, h_f))
                    print(f"🎥 [REC] Started recording incident: {current_clip_name}")

            # --- CONTINUOUS DURATION CHECK FOR WARNINGS ---
            duration = time.time() - alert_start_time
            if duration >= 60.0 and not email_sent_1min:
                send_modern_email(current_alert, 1)
                email_sent_1min = True
            if duration >= 120.0 and not popup_sent_2min:
                show_os_popup(current_alert, 2)
                popup_sent_2min = True
                
            # --- MAX 3 MINUTES RECORDING LIMIT ---
            if duration >= 180.0 and video_writer is not None:
                video_writer.release()
                video_writer = None
                print(f"🛑 [INFO] Max 3 minutes reached. Video {current_clip_name} saved.")

        else:
            if current_alert != "":
                no_alert_frames += 1
                if no_alert_frames > 60: # ~2.0s buffer: AI லேசாக மிஸ் ஆனாலும் Alert உடனே நிற்காமல் இருக்க
                    current_alert = ""
                    # --- STOP RECORDING CLIP ---
                    if video_writer is not None:
                        video_writer.release()
                        video_writer = None
                        print(f"🛑 [REC] Stopped recording incident: {current_clip_name}")
                    # Action முடிந்தவுடன் மாடலை Refresh செய்ய Streak-களை அழிக்கிறோம்
                    fall_counter = 0
                    for p_id in list(fall_streak.keys()):
                        fall_streak[p_id] = 0
                    for p_id in list(violence_streak.keys()):
                        violence_streak[p_id] = 0

        display_alert = current_alert
        if display_alert:
            # Async Alert Sound (வீடியோ லேக் ஆகாமல் பேக்ரவுண்டில் அலர்ட் சத்தம் வர)
            if frame_count % 30 == 0: # 10 வினாடிகள் என்பதால் சத்தம் அளவாக கேட்க 30 ஆக மாற்றப்பட்டுள்ளது
                print(f"🚨 BEEP BEEP BEEP! Alert Sounding in Dashboard for: {display_alert} 🚨")

            # Save logic cleanly bundled with Alert print
            if frame_count % 10 == 0: # Throttle saves
                cv2.imwrite(os.path.join(STORAGE_PATH, f"alert_{frame_count}.jpg"), frame)
                
            # --- PROFESSIONAL ALERT UI DESIGN ---
            # 1. Flashing Border Effect (Red & Yellow)
            border_color = (0, 0, 255) if frame_count % 10 < 5 else (0, 255, 255)
            cv2.rectangle(frame, (0, 0), (frame.shape[1], frame.shape[0]), border_color, 8)
            cv2.rectangle(normal_frame, (0, 0), (normal_frame.shape[1], normal_frame.shape[0]), border_color, 8)

            # 2. Black Banner at the bottom
            banner_y = frame.shape[0] - 70
            cv2.rectangle(frame, (0, banner_y), (frame.shape[1], frame.shape[0]), (0, 0, 0), -1)
            cv2.rectangle(normal_frame, (0, banner_y), (normal_frame.shape[1], normal_frame.shape[0]), (0, 0, 0), -1)

            # 3. 3D Glowing Text Effect (Center Aligned)
            text_str = f"!!! {display_alert} !!!"
            text_size = cv2.getTextSize(text_str, cv2.FONT_HERSHEY_DUPLEX, 1.1, 3)[0]
            text_x = (frame.shape[1] - text_size[0]) // 2
            text_y = frame.shape[0] - 20
            
            # Shadow Text (3D Effect)
            cv2.putText(frame, text_str, (text_x+3, text_y+3), cv2.FONT_HERSHEY_DUPLEX, 1.1, (0, 0, 100), 3)
            cv2.putText(normal_frame, text_str, (text_x+3, text_y+3), cv2.FONT_HERSHEY_DUPLEX, 1.1, (0, 0, 100), 3)
            # Main Text
            cv2.putText(frame, text_str, (text_x, text_y), cv2.FONT_HERSHEY_DUPLEX, 1.1, border_color, 3)
            cv2.putText(normal_frame, text_str, (text_x, text_y), cv2.FONT_HERSHEY_DUPLEX, 1.1, border_color, 3)

        # --- DRAW RECORDING UI ---
        if recording_state["action"]:
            rec_text = f"REC: {recording_state['action'].upper()} ({len(recording_state['frames'])}/{SEQUENCE_LENGTH})"
            cv2.putText(frame, rec_text, (frame.shape[1] - 400, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.putText(normal_frame, rec_text, (normal_frame.shape[1] - 400, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # --- DRAW TIME AND DATE ---
        current_time = datetime.datetime.now().strftime("%d-%b-%Y %I:%M:%S %p")
        (tw, th), _ = cv2.getTextSize(current_time, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.putText(frame, current_time, (frame.shape[1] - tw - 15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(normal_frame, current_time, (normal_frame.shape[1] - tw - 15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # --- Send Data to FastAPI ---
        camera_alerts[camera_url] = {"msg": display_alert, "clip": current_clip_name if display_alert else ""}
        
        # --- RECORD VIDEO FRAME (WITH ALL UI & BORDERS) ---
        if video_writer is not None and display_alert != "":
            video_writer.write(frame)
        
        ret_encoded, buffer = cv2.imencode('.jpg', frame)
        if ret_encoded:
            latest_frames[camera_url] = buffer.tobytes()
            
        ret_encoded_clean, buffer_clean = cv2.imencode('.jpg', raw_frame)
        if ret_encoded_clean:
            latest_clean_frames[camera_url] = buffer_clean.tobytes()
            
        # --- AUTO LOG RETENTION CHECK ---
        if frame_count % 1800 == 0: # தோராயமாக ஒவ்வொரு 1 நிமிடத்திற்கும் (30fps x 60s) செக் செய்ய
            threading.Thread(target=auto_cleanup_logs, daemon=True).start()
            
        time.sleep(0.01) # CPU Overload ஆகாமல் தடுக்க

    cap.release()
    for p in pose_estimators.values():
        p.close()
        
    if camera_url in active_threads:
        del active_threads[camera_url]
    if camera_url in running_cameras:
        del running_cameras[camera_url]

def start_background_camera(camera_url):
    if camera_url not in active_threads:
        running_cameras[camera_url] = True
        t = threading.Thread(target=_run_camera_loop, args=(camera_url,), daemon=True)
        t.start()
        active_threads[camera_url] = t

def stop_camera(camera_url):
    """கேமராவை பேக்ரவுண்டில் நிறுத்துவதற்கான ஃபங்ஷன்"""
    if camera_url in running_cameras:
        running_cameras[camera_url] = False # Flag-ஐ False ஆக்கினால் While loop நின்றுவிடும்

def generate_frames(camera_url=0, feed_type="processed"):
    start_background_camera(camera_url) # வீடியோவை பார்க்கும்போது கேமரா ஆன் ஆகவில்லை என்றால் ஆன் செய்ய
    while True:
        if feed_type == "clean":
            frame_bytes = latest_clean_frames.get(camera_url)
        else:
            frame_bytes = latest_frames.get(camera_url)
            
        if frame_bytes:
            try:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            except GeneratorExit:
                break
        time.sleep(0.03) # ~30 FPS Browser limit (Lag-ஐ குறைக்க)

if __name__ == "__main__":
    print("[INFO] AI is now running via FastAPI.")
    print("Run 'uvicorn api:app --host 0.0.0.0 --port 8000 --reload' to start!")