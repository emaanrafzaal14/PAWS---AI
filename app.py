import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import numpy as np
import cv2
import requests
import time

# Branded Application Title
st.set_page_config(page_title="PAWS", layout="centered")
st.title("🐾 PAWS - Proactive Animal Welfare System")
st.write("Real-time live video tracking for animal classification.")

# --- CONFIGURATION ---
# Your permanent, automated background Production URL
N8N_WEBHOOK_URL = "https://emaanafzaal.app.n8n.cloud/webhook-test/2b6aab9e-413c-4388-a72d-c055be3d7701"
COOLDOWN_SECONDS = 30  

def load_labels(path="label.txt"):
    with open(path, 'r') as f:
        return [line.strip() for line in f.readlines()]

try:
    labels = load_labels()
except Exception as e:
    st.error(f"Error loading label.txt: {e}")
    labels = ["injured_cat", "uninjured_cat", "other"]

# Load TFLite Model using OpenCV's built-in native reader (Super light!)
@st.cache_resource
def load_model(model_path="model.tflite"):
    net = cv2.dnn.readNetFromModelOptimizer(model_path)
    return net

try:
    # Read the raw tflite model directly using standard OpenCV structures
    interpreter = cv2.dnn.readNet(model_path="model.tflite")
except Exception as e:
    st.error(f"Failed to load model.tflite: {e}")
    st.stop()

if "last_injured_email_time" not in st.session_state:
    st.session_state.last_injured_email_time = 0
if "last_uninjured_email_time" not in st.session_state:
    st.session_state.last_uninjured_email_time = 0

def trigger_n8n_alert(status, confidence):
    payload = {
        "animal": "Cat",
        "status": status,
        "confidence": f"{confidence:.2f}%",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "address": "Live Stream Environment Camera Location"
    }
    try:
        requests.post(N8N_WEBHOOK_URL, json=payload, timeout=2)
    except Exception:
        pass 

class PAWSVideoProcessor(VideoTransformerBase):
    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        
        # Automatic input shape resolution detection via blob conversion
        blob = cv2.dnn.blobFromImage(img, 1.0/255.0, (96, 96), swapRB=True, crop=False)
        interpreter.setInput(blob)
        output_data = interpreter.forward()
        
        # Handle flat vector or multi-dimensional array outputs
        scores = output_data.flatten()
        max_idx = np.argmax(scores)
        prediction_label = labels[max_idx] if max_idx < len(labels) else "Scanning..."
        confidence_score = scores[max_idx] * 100 if scores[max_idx] <= 1.0 else scores[max_idx]
        
        current_time = time.time()
        
        if confidence_score > 70.0:  
            if prediction_label == "injured_cat":
                display_text = f"ALERT: Injured Cat Detected ({confidence_score:.1f}%)"
                color = (0, 0, 255) 
                
                if current_time - st.session_state.last_injured_email_time > COOLDOWN_SECONDS:
                    st.session_state.last_injured_email_time = current_time
                    trigger_n8n_alert("Injured", confidence_score)
                    
            elif prediction_label == "uninjured_cat":
                display_text = f"Status: Uninjured Cat Spotted ({confidence_score:.1f}%)"
                color = (0, 255, 0) 
                
                if current_time - st.session_state.last_uninjured_email_time > COOLDOWN_SECONDS:
                    st.session_state.last_uninjured_email_time = current_time
                    trigger_n8n_alert("Uninjured", confidence_score)
            else:
                display_text = "Scanning..."
                color = (255, 255, 255)
        else:
            display_text = "Scanning..."
            color = (255, 255, 255)
            
        cv2.putText(img, display_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        return frame.from_ndarray(img, format="bgr24")

webrtc_streamer(
    key="paws-streamer",
    video_transformer_factory=PAWSVideoProcessor,
    rtc_configuration={"iceServers": [{"urls": ["stun:://google.com"]}]},
    media_stream_constraints={"video": True, "audio": False}
)
