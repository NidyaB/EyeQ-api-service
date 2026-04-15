import cv2
import numpy as np
import mediapipe as mp

mp_pose = mp.solutions.pose

# --- Body Part Landmarks Mapping ---
HEAD_LMS = list(range(0, 11))
HAND_LMS = list(range(11, 23))
TRUNK_LMS = [11, 12, 23, 24]
LEG_LMS = list(range(23, 33))

# Hand landmarks for detailed drawing
LEFT_HAND_LMS_DETAILED = [mp_pose.PoseLandmark.LEFT_WRIST.value, mp_pose.PoseLandmark.LEFT_PINKY.value, mp_pose.PoseLandmark.LEFT_INDEX.value, mp_pose.PoseLandmark.LEFT_THUMB.value]
RIGHT_HAND_LMS_DETAILED = [mp_pose.PoseLandmark.RIGHT_WRIST.value, mp_pose.PoseLandmark.RIGHT_PINKY.value, mp_pose.PoseLandmark.RIGHT_INDEX.value, mp_pose.PoseLandmark.RIGHT_THUMB.value]

def draw_detailed_face(frame, landmarks, roi_dims, roi_offset):
    """
    Draws specific lines and highlights for Eyes, Nose, and Lips using Pose landmarks.
    """
    h_roi, w_roi = roi_dims
    x1, y1 = roi_offset
    
    def get_pt(idx):
        lm = landmarks[idx]
        if lm.visibility > 0.5:
            return (int(lm.x * w_roi) + x1, int(lm.y * h_roi) + y1)
        return None

    # 1. Nose (Cyan Point)
    nose = get_pt(mp_pose.PoseLandmark.NOSE.value)
    if nose: 
        cv2.circle(frame, nose, 6, (255, 255, 0), -1)
        cv2.putText(frame, "Nose", (nose[0]-15, nose[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

    # 2. Eyes (Yellow Connected Lines)
    re1, re2, re3 = get_pt(1), get_pt(2), get_pt(3) # Right Eye
    if re1 and re2 and re3:
        cv2.polylines(frame, [np.array([re1, re2, re3])], False, (0, 255, 255), 2)
    le1, le2, le3 = get_pt(4), get_pt(5), get_pt(6) # Left Eye
    if le1 and le2 and le3:
        cv2.polylines(frame, [np.array([le1, le2, le3])], False, (0, 255, 255), 2)

    # 3. Lips (Orange Line connecting mouth points)
    lip1, lip2 = get_pt(9), get_pt(10)
    if lip1 and lip2:
        cv2.line(frame, lip1, lip2, (0, 165, 255), 3)

def draw_detailed_hand(frame, landmarks, hand_indices, wrist_index, roi_dims, roi_offset):
    """
    Draws a detailed visualization for a hand (bbox, contour, points, lines to wrist).
    """
    h_roi, w_roi = roi_dims
    x1, y1 = roi_offset
    
    hand_points = []
    for i in hand_indices:
        if landmarks[i].visibility > 0.6: # Hand points need higher confidence
            cx = int(landmarks[i].x * w_roi) + x1
            cy = int(landmarks[i].y * h_roi) + y1
            hand_points.append([cx, cy])

    if len(hand_points) < 3: # Need at least 3 points for a contour
        return

    hand_points = np.array(hand_points, dtype=np.int32)

    # 1. Bounding Box (Pink)
    x, y, w, h = cv2.boundingRect(hand_points)
    cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 192, 203), 1)

    # 2. Hand Contour (Convex Hull - Purple)
    hull = cv2.convexHull(hand_points)
    cv2.drawContours(frame, [hull], -1, (128, 0, 128), 2)

    # 3. Points on each landmark (White)
    for pt in hand_points:
        cv2.circle(frame, tuple(pt), 3, (255, 255, 255), -1)

    # 4. Lines from fingers to wrist (Gray)
    if landmarks[wrist_index].visibility > 0.6:
        wrist_x = int(landmarks[wrist_index].x * w_roi) + x1
        wrist_y = int(landmarks[wrist_index].y * h_roi) + y1
        
        for pt in hand_points:
            # Draw line from each point to the wrist
            cv2.line(frame, tuple(pt), (wrist_x, wrist_y), (200, 200, 200), 1)