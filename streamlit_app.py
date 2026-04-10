import streamlit as st
import subprocess
import sys

# --- 1. DATABASE ENGINE ---
try:
    from supabase import create_client
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "supabase"])
    st.rerun()

import pandas as pd
from datetime import datetime, timedelta
import calendar

# --- 2. THE CONNECTION ---
URL = "https://vxddavmufabkftxinlhz.supabase.co" 
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ4ZGRhdm11ZmFia2Z0eGlubGh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU3ODUwODksImV4cCI6MjA5MTM2MTA4OX0.jt8XfoLeX0tikeGU1yQ3bzo-u4_KrSXC9dHrLza1ZW4"

@st.cache_resource
def get_db():
    return create_client(URL, KEY)

db = get_db()

# --- 3. CONFIG & BRANDING ---
st.set_page_config(page_title="DALE Staff Portal", layout="centered")
st.markdown("""
    <style>
    :root { --dale-burgundy: #661026; }
    .stButton>button { width: 100%; border-radius: 10px; background-color: var(--dale-burgundy); color: white; border: none; }
    .stMetric { background-color: #fcfcfc; padding: 15px; border-radius: 10px; border-left: 5px solid var(--dale-burgundy); box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
    .calendar-day { text-align: center; padding: 10px; border: 1px solid #eee; border-radius: 5px; min-height: 45px; font-size: 0.9rem; }
    .booked-day { background-color: var(--dale-burgundy); color: white; font-weight: bold; border: 1px solid gold; }
    .half-day-tag { font-size: 0.7rem; background: #ffd700; color: black; padding: 2px 5px; border-radius: 5px; }
    .manager-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 10px; background-color: white; border-left: 5px solid gold; }
    </style>
""", unsafe_allow_html=True)

# --- 4. LOGIC HELPERS ---
def get_holiday_year(date_obj):
    if date_obj is None: date_obj = datetime.now()
    if date_obj.month >= 4: return f"{date_obj.year}/{date_obj.year + 1}"
    return f"{date_obj.year - 1}/{date_obj.year}"

def calculate_working_days(start, end, day_type):
    if day_type != "Full Day":
        return 0.5 # Half days are only allowed for single-date requests usually
    
    days = 0
    curr = start
    while curr <= end:
        if curr.weekday() < 5: days += 1
        curr += timedelta(days=1)
    return float(days)

def get_target_hours(date, role):
    if role == "Factory" and date.weekday() == 4: return 6.5
    return 7.5

# --- 5. INITIALIZE STATE ---
if 'auth' not in st.session_state: st.session_state['auth'] = False
if 'cal_month' not in st.session_state: st.session_state['cal_month'] = datetime.now().month
if 'cal_year' not in st.session_state: st.session_state['cal_year'] = datetime.now().year

# --- 6. LOGIN VIEW ---
if not st.session_state['auth']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2: st.header("DALE Staff Portal")
    eid = st.text_input("Employee ID")
    pin = st.text_input("PIN", type="password")
    if st.button("Login"):
        res = db.table("employees").select("*").eq("employee_id", eid).execute()
        if res.data:
            user = res.data[0]
            if str(user.get('pin')) == str(pin):
                st.session_state['auth'] = True
                st.session_state['user'] = user
                st.rerun()
            else: st.error("Incorrect PIN")
        else: st.error("Employee ID not found")

# --- 7. MAIN DASHBOARD ---
else:
    res = db.table("employees").select("*").eq("employee_id", st.session_state['user']['employee_id']).execute()
    u = res.data[0]
    my_id = u['employee_id']
    
    reports_res = db.table("employees").select("employee_id, full_name").eq("manager_id", my_id).execute()
    report_data = {str(r['employee_id']): r['full_name'] for r in reports_res.data}
    is_a_manager = len(report_data) > 0

    h1, h2 = st.columns([3,1])
    h1.title(f"Hi, {u.get('full_name', 'Employee')}")
    if h2.button("Logout"):
        st.session_state['auth'] = False
        st.rerun()

    tabs = ["My Dashboard", "My Calendar", "My Flexi-Log"]
    if is_a_manager: tabs.append("Team Requests")
    t_list = st.tabs(tabs)
    
    with t_list[0]:
        st.subheader("Your Entitlements")
        m1, m2 = st.columns(2)
        m1.metric("Holiday", f"{u.get('contractual_allowance', 0)}d")
        m2.metric("Flexi", f"{u.get('flexi_balance', 0)}h")
        
        st.divider()
        st.subheader("Request Personal Leave")
        l_type = st.selectbox("Leave Type", ["Annual Leave", "Purchased Holiday", "Flexi-Leave", "Sickness"])
        
        # New: Day Type Selection
        d_type = st.radio("Duration", ["Full Day", "AM Half Day", "PM Half Day"], horizontal=True)
        
        c1, c2 = st.columns(2)
        if d_type == "Full Day":
            d1 = c1.date_input("Start Date")
            d2 = c2.date_input("End Date")
        else:
            d1 = st.date_input("Date")
            d2 = d1 # Half day is always same day

        if st.button("Submit Request", type="primary"):
            new_req = {
                "employee_id": my_id, "start_date": str(d1), "end_date": str(d2),
                "leave_type": l_type, "status": "Pending", 
                "holiday_year": get_holiday_year(d1), "day_type": d_type
            }
            db.table("bookings").insert(new_req).execute()
            st.success("Request submitted!")
            st.rerun()

    with t_list[1]:
        bk_res = db.table("bookings").select("*").eq("employee_id", my_id).execute()
        user_bookings = bk_res.data if bk_res.data else []
        # [Navigation logic remains same...]
        cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
        # [Header cols remain same...]
        # Update calendar to show half-day tag
        for week in cal:
            row_cols = st.columns(7)
            for i, day in enumerate(week):
                if day != 0:
                    dt_str = f"{st.session_state.cal_year}-{st.session_state.cal_month:02d}-{day:02d}"
                    # Find if this specific day is booked
                    booking = next((b for b in user_bookings if b.get('start_date') <= dt_str <= b.get('end_date') and b.get('status') == 'Approved'), None)
                    if booking:
                        tag = ""
                        if booking.get('day_type') != "Full Day":
                            tag = f"<br><span class='half-day-tag'>{booking.get('day_type')}</span>"
                        row_cols[i].markdown(f'<div class="calendar-day booked-day">{day}{tag}</div>', unsafe_allow_html=True)
                    else:
                        row_cols[i].markdown(f'<div class="calendar-day">{day}</div>', unsafe_allow_html=True)

    with t_list[2]:
        # [Flexi Calculator logic remains same...]
        pass

    if is_a_manager:
        with t_list[3]:
            st.subheader("Direct Report Approvals")
            pending = db.table("bookings").select("*").in_("employee_id", list(report_data.keys())).eq("status", "Pending").execute()
            
            for req in pending.data:
                name = report_data.get(str(req['employee_id']), "Employee")
                with st.container():
                    st.markdown(f"""<div class="manager-card">
                        <b>{name}</b><br>
                        {req['leave_type']} ({req['day_type']})<br>
                        {req['start_date']} to {req['end_date']}
                    </div>""", unsafe_allow_html=True)
                    b1, b2, _ = st.columns([1,1,2])
                    if b1.button("Approve", key=f"app_{req['id']}"):
                        # 1. Update Status
                        db.table("bookings").update({"status": "Approved"}).eq("id", req['id']).execute()
                        # 2. Smart Deduction
                        if req['leave_type'] in ["Annual Leave", "Purchased Holiday"]:
                            s = datetime.strptime(req['start_date'], "%Y-%m-%d")
                            e = datetime.strptime(req['end_date'], "%Y-%m-%d")
                            days_to_deduct = calculate_working_days(s, e, req['day_type'])
                            
                            rep = db.table("employees").select("contractual_allowance").eq("employee_id", req['employee_id']).execute()
                            new_bal = float(rep.data[0]['contractual_allowance']) - days_to_deduct
                            db.table("employees").update({"contractual_allowance": new_bal}).eq("employee_id", req['employee_id']).execute()
                        st.rerun()
                    if b2.button("Reject", key=f"rej_{req['id']}"):
                        db.table("bookings").update({"status": "Rejected"}).eq("id", req['id']).execute()
                        st.rerun()