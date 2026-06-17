import streamlit as st
import numpy as np
import datetime
import time
from zoneinfo import ZoneInfo
from supabase import create_client

# --- Setup ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

# --- Logic Functions ---
def raw_to_norm(x, cutoff=1.0):
    if x <= 0: return 0.0
    if x >= 5 * cutoff: return 1.0
    if x <= cutoff: return 0.8 * x / cutoff
    else: return 0.8 + 0.2 * (x - cutoff) / (4 * cutoff)

CANCER_CONFIG = {
    "--select--": {"names": []},
    "lung": {"names": ["CEA", "CA125", "NSE", "CYFRA21-1", "Pro-GRP"], "cutoffs": [5.0, 35.0, 16.0, 3.5, 65.0]},
    "breast": {"names": ["CA15-3", "CA125", "CEA", "HER2", "ER"], "cutoffs": [30.0, 35.0, 5.0, 2.5, 2.5]},
    "prostate": {"names": ["PSA", "Free-PSA", "PSA-Density", "DRE", "Gleason"], "cutoffs": [4.0, 0.25, 0.10, 1.5, 6.0]}
}

st.set_page_config(page_title="Clinical Risk Assessment", layout="centered")
st.title("🏥 Clinical Risk Assessment Tool")

patient_name = st.text_input("Patient Full Name")
cancer = st.selectbox("Select Cancer Type", list(CANCER_CONFIG.keys()))
info = CANCER_CONFIG[cancer]
X_raw = [st.number_input(f"{name} value:", value=0.0, format="%.2f") for name in info["names"]]

if st.button("Generate Diagnostic Report"):
    if not patient_name or cancer == "--select--":
        st.error("Please fill in all fields.")
    else:
        X_norm = np.array([raw_to_norm(X_raw[i], info["cutoffs"][i]) for i in range(len(info["cutoffs"]))])
        y_final = 0.5 
        formatted_time = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).strftime('%d-%m-%Y/%H:%M')
        
        db_record = {
            "timestamp": formatted_time,
            "patient_name": patient_name,
            "cancer_type": cancer,
            "risk_score": f"{y_final:.2%}",
            "raw_data": str(dict(zip(info["names"], X_raw)))
        }
        
        try:
            supabase.table("patient_history").insert(db_record).execute()
            st.success("✅ Report saved!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Save error: {e}")

# --- Sidebar History Log ---
with st.sidebar:
    st.title("📜 Patient History Log")
    try:response = supabase.table("patient_history").select("*").execute()
        history = response.data
        if not history:
            st.info("No records found.")
        else:
            for entry in history:
                with st.expander(f"Patient: {entry.get('patient_name', 'Unknown')}"):
                    st.write(f"**Date:** {entry.get('timestamp')}")
                    st.write(f"**Risk Score:** {entry.get('risk_score')}")
    except Exception as e:
        st.error(f"DB Load Error: {e}")
