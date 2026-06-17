from supabase import create_client
import streamlit as st
import streamlit as st
import numpy as np
import datetime
import pandas as pd
import io
import datetime
from zoneinfo import ZoneInfo
import random 
import string 
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
    "--select--":{"names":[]},
    "lung": {"names": ["CEA", "CA125", "NSE", "CYFRA21-1", "Pro-GRP"], "cutoffs": [5.0, 35.0, 16.0, 3.5, 65.0]},
    "breast": {"names": ["CA15-3", "CA125", "CEA", "HER2", "ER"], "cutoffs": [30.0, 35.0, 5.0, 2.5, 2.5]},
    "prostate": {"names": ["PSA", "Free-PSA", "PSA-Density", "DRE", "Gleason"], "cutoffs": [4.0, 0.25, 0.10, 1.5, 6.0]}
}

# --- Session State Initialization ---
if 'patient_history' not in st.session_state:
    st.session_state.patient_history = []

st.set_page_config(page_title="Clinical Risk Assessment", layout="centered")

# --- Main Assessment UI ---
st.title("🏥 Clinical Risk Assessment Tool")
patient_name = st.text_input("Patient Full Name")
cancer = st.selectbox("Select Cancer Type", list(CANCER_CONFIG.keys()))
info = CANCER_CONFIG[cancer]
X_raw = [st.number_input(f"{name} value:", value=0.0, format="%.2f") for name in info["names"]]

if st.button("Generate Diagnostic Report"):
    if not patient_name:
        st.error("Please enter a patient name first.")
    elif cancer == "--select--":
        st.error("Please select a valid cancer type.")
    else:
        # Calculation Logic
        X_norm = np.array([raw_to_norm(X_raw[i], info["cutoffs"][i]) for i in range(len(info["cutoffs"]))])
        mu_low = np.clip(1.0 - X_norm / 0.5, 0.0, 1.0)
        mu_high = np.clip(X_norm / 1.2, 0.0, 1.0)
        # 2. Define the local time ONCE here
        local_now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
        formatted_time = local_now.strftime('%d-%m-%Y/%H:%M')

        rules = [
            {"ant_low": [True]*5, "offset": 0.05, "w": np.array([0.05]*5)},
            {"ant_low": [False, False, True, True, True], "offset": 0.2, "w": np.array([0.3, 0.2, 0.0, 0.0, 0.0])},
            {"ant_low": [False, True, False, True, True], "offset": 0.3, "w": np.array([0.3, 0.0, 0.25, 0.0, 0.0])},
            {"ant_low": [False]*5, "offset": 0.4, "w": np.array([0.15]*5)},
            {"ant_low": [True, True, True, True, True], "offset": 0.05, "w": np.array([0.01]*5)}]

        alpha, y_consequent = [], []
        for r in rules:
            mu_ri = [mu_low[i] if r["ant_low"][i] else mu_high[i] for i in range(5)]
            alpha.append(np.prod(mu_ri))
            y_consequent.append(r["offset"] + np.sum(r["w"] * X_norm))
        # Change your existing y_final calculation line to this:
        y_final = np.clip(np.sum(np.array(alpha) * np.array(y_consequent)) / (np.sum(alpha) + 1e-9), 0.05, 1.0)

        # Create Hospital Style Report
        report_content = f"""
==================================================
           HOSPITAL CLINICAL LABORATORY           
==================================================
Patient Name : {patient_name}
Date/Time    : {formatted_time}
Test Type    : {cancer.upper()} RISK ASSESSMENT
--------------------------------------------------
Clinical Markers:
"""
        for i, name in enumerate(info["names"]):
            report_content += f"- {name}: {X_raw[i]}\n"

        report_content += f"""
--------------------------------------------------
FINAL RISK SCORE: {y_final:.2%}
--------------------------------------------------
Result Interpretation: 
Risk level calculated based on clinical markers.
Please consult an oncologist for verification.
==================================================
"""
        # Display on Screen (Kept exactly as requested)
        st.subheader("Diagnostic Report Preview")
        st.text(report_content)
        # Generate a random ID like 'P-4X9B2'
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        unique_id = f"P-{random_suffix}"

        # Add to History (Internal logic)
        record = {
            "ID": unique_id, 
            "Timestamp": formatted_time,
            "Patient": patient_name,
            "CancerType": cancer,
            "RiskScore": f"{y_final:.2%}",
            **dict(zip(info["names"], X_raw))
        }
        is_duplicate = False
        for entry in st.session_state.patient_history:
            if (entry['Patient'] == record['Patient'] and 
                entry['CancerType'] == record['CancerType'] and
                all(entry.get(k) == record.get(k) for k in info["names"])):
                is_duplicate = True
                duplicate_time = entry['Timestamp']
                break

        if is_duplicate:
            st.toast("Couldnt save record. Duplicate Found!", icon="⚠️")
            st.warning(f"⚠️ Duplicate entry detected! This assessment was already recorded at {duplicate_time}.")
        # ... inside your 'else' block for the duplicate check ...
            st.subheader("Reference: Previous Clinical Output") # Clear distinction
            st.info("The output below corresponds to the previously saved record.")
            st.text(report_content)
       
        else:
            db_record = {
        "id": unique_id,
        "timestamp": formatted_time,
        "patient_name": patient_name,
        "cancer_type": cancer,
        "risk_score": f"{y_final:.2%}",
        "raw_data": str(dict(zip(info["names"], X_raw))) 
    }

    # 2. Insert into Supabase
    try:
        supabase.table("patient_history").insert(db_record).execute()
        st.toast("Report saved to database!", icon="✅")
        st.success("✅ Report generated and saved to history!")
    except Exception as e:
        st.error(f"Database error: {e}")
        
# --- Sidebar History Log ---
with st.sidebar:
    st.title("📜 Patient History Log")
    
    # Fetch data directly from Supabase
    response = supabase.table("patient_history").select("*").order("timestamp", desc=True).execute()
    history = response.data
    
    if not history:
        st.info("No records logged.")
    else:
        for entry in history:
            # Using the column names from your database
            with st.expander(f"Patient: {entry['patient_name']} ({entry['id']})"):
                st.write(f"**Date:** {entry['timestamp']}")
                st.write(f"**Risk Score:** {entry['risk_score']}")
                st.write(f"**Cancer Type:** {entry['cancer_type']}")
                st.json(entry['raw_data']) # Displays the dictionary clearly
                # Reconstruct the report content for this specific record
                report_text = f"Report for {entry['Patient']}\nID: {entry['ID']}\nScore: {entry['RiskScore']}\nMarkers: {entry}"

                # Individual Download Button for this specific record
                st.download_button(
                    label=f"📥 Download {entry['ID']}",
                    data=report_text,
                    file_name=f"{entry['Patient']}_{entry['ID']}.txt",
                    mime="text/plain"
                )


        # CSV Export
        col1, col2 = st.columns(2)
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        col1.download_button("📥 CSV", csv_buffer.getvalue(), "history.csv", "text/csv")

        # Clear History
        if col2.button("🗑️ Clear"):
            st.session_state.patient_history = []
            st.rerun()
