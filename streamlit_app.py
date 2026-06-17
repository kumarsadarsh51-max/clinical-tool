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

# Initialize session state for the report
if "report_content" not in st.session_state:
    st.session_state.report_content = None
    
if st.button("Generate Diagnostic Report"):
    if not patient_name or cancer == "--select--":
        st.error("Please fill in all fields.")
    else:
        # 1. Define current entry data
        current_data = {
            "patient_name": patient_name,
            "cancer_type": cancer,
            "raw_data": str(dict(zip(info["names"], X_raw)))
        }
        
        # 2. Fetch existing history to check for duplicates
        response = supabase.table("patient_history").select("*").execute()
        existing_records = response.data
        
        # 3. Check for exact match
        duplicate = next(
            (item for item in existing_records 
             if item['patient_name'] == current_data['patient_name'] 
             and item['cancer_type'] == current_data['cancer_type']
             and item['raw_data'] == current_data['raw_data']), 
            None
        )
        
        if duplicate:
            st.warning("⚠️ Duplicate entry detected!")
            st.write("The following matching entry already exists in the system:")
            with st.expander("View Original Entry Details", expanded=True):
                st.write(f"**Patient:** {duplicate.get('patient_name')}")
                st.write(f"**Date:** {duplicate.get('timestamp')}")
                st.write(f"**Risk Score:** {duplicate.get('risk_score')}")
                st.write(f"**Raw Data:** {duplicate.get('raw_data')}")
        else:
            # Proceed with normal save logic
            # 1. Normalize data
            X_norm = np.array([raw_to_norm(X_raw[i], info["cutoffs"][i]) for i in range(len(info["cutoffs"]))])
            
            # 2. Update Risk Calculation Logic
            # Example: A simple average of normalized markers. 
            # You can apply weights here if some markers are more significant.
            # To set a 5% baseline, you might adjust the calculation like this:
            base_risk = 0.05
            calculated_risk = np.mean(X_norm) 
            y_final = base_risk + (calculated_risk * 0.95) # Scales risk up from the 5% base
            
            formatted_time = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).strftime('%d-%m-%Y/%H:%M')

            # --- Hospital Bill Format ---
            # Store report in session state
            st.session_state.report_content = f"""
==================================================
           HOSPITAL CLINICAL LABORATORY           
==================================================
Patient Name : {patient_name}
Date/Time    : {formatted_time}
Test Type    : {cancer.upper()} RISK ASSESSMENT
--------------------------------------------------
Clinical Markers:
{chr(10).join([f'- {name}: {val}' for name, val in zip(info["names"], X_raw)])}
--------------------------------------------------
FINAL RISK SCORE: {y_final:.2%}
--------------------------------------------------
Result Interpretation: 
Risk level calculated based on clinical markers.
Please consult an oncologist for verification.
==================================================
"""
            # 3. Save to Database
            db_record = {
                "timestamp": formatted_time, 
                "patient_name": patient_name, 
                "cancer_type": cancer, 
                "risk_score": f"{y_final:.2%}", 
                "raw_data": current_data["raw_data"]
            }
            
            try:
                supabase.table("patient_history").insert(db_record).execute()
                # 4. Trigger rerun to clear form inputs
                st.rerun()
            except Exception as e:
                st.error(f"Save error: {e}")

# --- Display the persistent bill (Place this AFTER the Generate button block) ---
if "report_content" in st.session_state and st.session_state.report_content:
    st.subheader("Diagnostic Report Preview")
    st.text(st.session_state.report_content)
    if st.button("Clear Preview"):
        st.session_state.report_content = None
        st.rerun()
# --- Sidebar History Log ---
with st.sidebar:
    st.title("📜 Patient History Log")
    try:
        response = supabase.table("patient_history").select("*").execute()
        history = response.data
        if not history:
            st.info("No records found.")
        else:
            for entry in history:
                # Update this line to include more context:
                title = f"{entry.get('patient_name')} ({entry.get('cancer_type')}) - {entry.get('timestamp')}"
                
                with st.expander(title):
                    st.write(f"**Date:** {entry.get('timestamp')}")
                    st.write(f"**Cancer Type:** {entry.get('cancer_type')}")
                    st.write(f"**Risk Score:** {entry.get('risk_score')}")
                    st.write(f"**Raw Data:** {entry.get('raw_data')}")
    except Exception as e:
        st.error(f"DB Load Error: {e}")
# --- Clear History Button ---
    if st.button("🗑️ Clear All History"):
        try:
            # Delete all rows in the table
            supabase.table("patient_history").delete().neq("id", 0).execute()
            st.success("History cleared!")
            st.rerun() # Refresh to update the UI
        except Exception as e:
            st.error(f"Error clearing history: {e}")
