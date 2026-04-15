import cv2
import numpy as np

class MotionDetector:
    # 2. Dynamic Thresholding: var_threshold 70, motion_threshold area-a 5000-ku ethittom (chinnatha filter panna)
    def __init__(self, history=500, var_threshold=30, warmup_frames=120, motion_threshold=800):
        self.backSub = cv2.createBackgroundSubtractorMOG2(
            history=history, 
            varThreshold=var_threshold, 
            detectShadows=True
        )
        self.warmup_frames = warmup_frames
        self.warmup_counter = 0
        self.motion_threshold = motion_threshold

    def apply_roi_mask(self, frame, fg_mask):
        height, width = fg_mask.shape
        ignore_height = int(height * 0.20)
        fg_mask[0:ignore_height, :] = 0 
        return fg_mask

    def process_frame(self, frame):
        if self.warmup_counter < self.warmup_frames:
            fgMask = self.backSub.apply(frame, learningRate=0.5)
            self.warmup_counter += 1
            return [], fgMask, True 

        fgMask = self.backSub.apply(frame, learningRate=-1)
        
        # 1. Noise Reduction (Blur & Morphological Operations)
        fgMask = cv2.GaussianBlur(fgMask, (5, 5), 0)
        _, fgMask = cv2.threshold(fgMask, 200, 255, cv2.THRESH_BINARY)
        kernel = np.ones((15, 15), np.uint8) # Periya kernel size merge panna help pannum
        fgMask = cv2.morphologyEx(fgMask, cv2.MORPH_CLOSE, kernel)
        fgMask = cv2.dilate(fgMask, kernel, iterations=2)
        
        fgMask = self.apply_roi_mask(frame, fgMask)

        # 3. Human ROI Filter pannu
        contours, _ = cv2.findContours(fgMask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        bboxes = []
        for cnt in contours:
            if cv2.contourArea(cnt) > self.motion_threshold: 
                x, y, w, h = cv2.boundingRect(cnt)
                bboxes.append([x, y, w, h])
                
        return bboxes, fgMask, False