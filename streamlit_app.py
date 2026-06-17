import streamlit as st
import numpy as np
import datetime
import time
from zoneinfo import ZoneInfo
from supabase import create_client

# CANCER CONFIGURATION:
CANCER_CONFIG = {
    "--select--": {"names": []},
    "lung": {"names": ["CEA", "CA125", "NSE", "CYFRA21-1", "Pro-GRP"], "cutoffs": [5.0, 35.0, 16.0, 3.5, 65.0]},
    "breast": {"names": ["CA15-3", "CA125", "CEA", "HER2", "ER"], "cutoffs": [30.0, 35.0, 5.0, 2.5, 2.5]},
    "prostate": {"names": ["PSA", "Free-PSA", "PSA-Density", "DRE", "Gleason"], "cutoffs": [4.0, 0.25, 0.10, 1.5, 6.0]}
}

# INITIALIZING INFO (ESCAPING ERROR MESSAGE)
if "info" not in locals():
    info = CANCER_CONFIG["--select--"]

# Reset trigger
if "reset_form" not in st.session_state:
    st.session_state.reset_form = False

# If the flag is set, clear the session state keys for the widgets
if st.session_state.reset_form:
    st.session_state.patient_name = ""
    for name in info["names"]:
        st.session_state[f"marker_{name}"] = 0.0
    st.session_state.reset_form = False # Reset the flag

# --- Setup ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

def clear_report():
    st.session_state.report_content = None

# CONVERT TO PDF
from fpdf import FPDF

def generate_pdf(entry):
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="HOSPITAL CLINICAL LABORATORY", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    
    # Patient Details
    pdf.cell(200, 10, txt=f"Patient Name: {entry['patient_name']}", ln=True)
    pdf.cell(200, 10, txt=f"Patient ID: {entry.get('patient_id', 'N/A')}", ln=True)
    pdf.cell(200, 10, txt=f"Date: {entry['timestamp']}", ln=True)
    pdf.ln(5)
    
    # Risk Assessment
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=f"Test Type: {entry['cancer_type'].upper()} RISK ASSESSMENT", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Final Risk Score: {entry['risk_score']}", ln=True)
    pdf.ln(10)
    
    # Raw Data
    pdf.cell(200, 10, txt="Clinical Markers:", ln=True)
    pdf.set_font("Courier", size=10)
    pdf.multi_cell(0, 10, txt=str(entry['raw_data']))
    
    return pdf.output(dest='S') # Returns the PDF as a string/bytes

# --- Logic Functions ---
def raw_to_norm(x, cutoff=1.0):
    if x <= 0: return 0.0
    if x >= 5 * cutoff: return 1.0
    if x <= cutoff: return 0.8 * x / cutoff
    else: return 0.8 + 0.2 * (x - cutoff) / (4 * cutoff)
        
# SETTING UI OF WEBSITE
st.set_page_config(page_title="Clinical Risk Assessment", layout="centered")
st.title("🏥 Clinical Risk Assessment Tool")

patient_name = st.text_input("Patient Full Name",key="patient_name")
cancer = st.selectbox("Select Cancer Type", list(CANCER_CONFIG.keys()))
info = CANCER_CONFIG[cancer]
X_raw = [st.number_input(f"{name} value:", value=0.0, format="%.2f", key=f"marker_{name}", on_change=clear_report) for name in info["names"]]

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
            marker_lines = []
            for i, name in enumerate(info["names"]):
                val = X_raw[i]
                cutoff = info["cutoffs"][i]
                # Flag if value exceeds cutoff
                if val > cutoff:
                    marker_lines.append(f"- {name}: {val} (HIGH - ALERT)")
                else:
                    marker_lines.append(f"- {name}: {val}")

            st.session_state.report_content = f"""
==================================================
           HOSPITAL CLINICAL LABORATORY           
==================================================
Patient Name : {patient_name}
Date/Time    : {formatted_time}
Test Type    : {cancer.upper()} RISK ASSESSMENT
--------------------------------------------------
Clinical Markers:
{chr(10).join(marker_lines)}
--------------------------------------------------
FINAL RISK SCORE: {y_final:.2%}
--------------------------------------------------
Result Interpretation: 
Risk level calculated based on clinical markers.
{f"⚠️ ALERT: One or more markers are above the clinical threshold." if any(X_raw[i] > info["cutoffs"][i] for i in range(len(X_raw))) else "All markers are within normal range."}
Please consult an oncologist for verification.
==================================================
"""            # 3. Save to Database
            db_record = {
                "timestamp": formatted_time, 
                "patient_name": patient_name, 
                "cancer_type": cancer, 
                "risk_score": f"{y_final:.2%}", 
                "raw_data": current_data["raw_data"]
            }
            
            try:
                supabase.table("patient_history").insert(db_record).execute()
                # Reset the inputs
                st.session_state.reset_form = True
                st.rerun()
            except Exception as e:
                st.error(f"Save error: {e}")

if "report_content" in st.session_state and st.session_state.report_content:
    st.subheader("Diagnostic Report Preview")
    st.text(st.session_state.report_content)
    if st.button("Clear Preview"):
        st.session_state.report_content = None
        st.rerun()

# --- Sidebar History Log ---
with st.sidebar:
    st.title("📜 Patient History Log")
    
    # --- 1. SEARCH & FILTER CONTROLS ---
    search_query = st.text_input("🔍 Search by Patient Name").lower()
    
    # Date filter: Default to the full range of your data
    st.write("Filter by Date Range:")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start", value=datetime.date(2026, 1, 1))
    with col2:
        end_date = st.date_input("End", value=datetime.date.today())

    try:
        response = supabase.table("patient_history").select("*").execute()
        history = response.data
        
        if not history:
            st.info("No records found.")
        else:
            # --- 2. APPLY FILTERS ---
            filtered_history = []
            for entry in history:
                # Filter by name
                name_match = search_query in entry.get('patient_name', '').lower()
                
                # Filter by date
                entry_date_str = entry.get('timestamp').split('/')[0] # Get '17-06-2026'
                entry_date = datetime.datetime.strptime(entry_date_str, '%d-%m-%Y').date()
                date_match = start_date <= entry_date <= end_date
                
                if name_match and date_match:
                    filtered_history.append(entry)

            # --- 3. RENDER FILTERED LIST ---
            if not filtered_history:
                st.warning("No records match these filters.")
            else:
                for entry in filtered_history:
                    title = f"{entry.get('patient_name')} ({entry.get('cancer_type')}) - {entry.get('timestamp')}"
                    with st.expander(title):
                        # ... (Keep your existing expander content code here) ...
                        st.write(f"**Date:** {entry.get('timestamp')}")
                        st.write(f"**Cancer Type:** {entry.get('cancer_type')}")
                        st.write(f"**Risk Score:** {entry.get('risk_score')}")
                        
                    
                    
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
