import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import tflite_runtime.interpreter as tflite
import numpy as np
import cv2
import requests
import time

# Branded Application Title
st.set_page_config(page_title="PAWS", layout="centered")
st.title("🐾 PAWS - Proactive Animal Welfare System")
st.write("Real-time live video tracking for animal classification.")

# --- CONFIGURATION ---
# Replace this placeholder link with your n8n Test URL
N8N_WEBHOOK_URL = "https://your-n8n-instance.com"
COOLDOWN_SECONDS = 30  

def load_labels(path="label.txt"):
    with open(path, 'r') as f:
        return [line.strip() for line in f.readlines()]

try:
    labels = load_labels()
except Exception as e:
    st.error(f"Error loading label.txt: {e}")
    labels = ["injured_cat", "uninjured_cat", "other"]

# Load TFLite Model using lightweight tflite_runtime framework
@st.cache_resource
def load_model(model_path="model.tflite"):
    interpreter = tflite.Interpreter(model_path=model_path)
    interpreter.allocate_tensors()
    return interpreter

try:
    interpreter = load_model()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    input_shape = input_details[0]['shape'] 
    input_height = input_shape[1]
    input_width = input_shape[2]
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
        
        resized = cv2.resize(img, (input_width, input_height))
        input_data = np.expand_dims(resized, axis=0).astype(np.float32) / 255.0
        
        interpreter.set_tensor(input_details[0]['index'], input_data)
        interpreter.invoke()
        output_data = interpreter.get_tensor(output_details[0]['index'])[0]
        
        max_idx = np.argmax(output_data)
        prediction_label = labels[max_idx]
        confidence_score = output_data[max_idx] * 100
        
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
