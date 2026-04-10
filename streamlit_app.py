import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime, timedelta
import calendar

# --- 1. CONNECTION ---
URL = "https://vxddavmufabkftxinlhz.supabase.co" 
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ4ZGRhdm11ZmFia2Z0eGlubGh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU3ODUwODksImV4cCI6MjA5MTM2MTA4OX0.jt8XfoLeX0tikeGU1yQ3bzo-u4_KrSXC9dHrLza1ZW4"

@st.cache_resource
def get_db(): return create_client(URL, KEY)
db = get_db()

# --- 2. LOGIC HELPERS ---
def get_year(dt): return f"{dt.year}/{dt.year+1}" if dt.month >= 4 else f"{dt.year-1}/{dt.year}"
def get_hrs(dt, role): return (6.5 if dt.weekday() == 4 else 7.5) if role == "Factory" else 7.5

def calc_deduct(s, e, dtype, role):
    total, curr = 0.0, s
    while curr <= e:
        if curr.weekday() < 5:
            v = get_hrs(curr, role) if role == "Factory" else 1.0
            total += (v/2) if dtype != "Full Day" else v
        curr += timedelta(days=1)
    return float(total)

# --- 3. SESSION STATE ---
if 'auth' not in st.session_state: st.session_state['auth'] = False
if 'cal_month' not in st.session_state: st.session_state['cal_month'] = datetime.now().month
if 'cal_year' not in st.session_state: st.session_state['cal_year'] = datetime.now().year

st.set_page_config(page_title="FHD Employee Portal", layout="centered")

# --- 4. LOGIN VIEW ---
if not st.session_state['auth']:
    # Forces title to show if logo fails
    try:
        st.image("dale_logo.png", width=250)
    except:
        st.write("") # Spacer
    
    st.title("FHD Employee Portal")
        
    eid, pin = st.text_input("Employee ID"), st.text_input("PIN", type="password")
    if st.button("Login"):
        r = db.table("employees").select("*").eq("employee_id", eid).execute()
        if r.data and str(r.data[0].get('pin')) == str(pin):
            st.session_state['auth'], st.session_state['user'] = True, r.data[0]
            st.rerun()

# --- 5. AUTHENTICATED VIEW ---
else:
    u_res = db.table("employees").select("*").eq("employee_id", st.session_state['user']['employee_id']).execute()
    u = u_res.data[0]
    mid, role = u['employee_id'], u.get('role', 'Office')
    
    # Header with Logo & Logout
    col_a, col_b, col_c = st.columns([1,3,1])
    with col_a:
        try: st.image("dale_logo.png", width=80)
        except: st.subheader("FHD")
    with col_b: st.subheader(f"Hi, {u.get('full_name')}")
    with col_c:
        if st.button("Logout"):
            st.session_state['auth'] = False
            st.rerun()

    # Sickness Alert
    os = db.table("bookings").select("*").eq("employee_id", mid).eq("leave_type", "Sickness").eq("sickness_closed_by_emp", False).execute()
    if os.data:
        st.warning(f"⚠️ Sickness Active (Started: {os.data[0]['start_date']})")
        if st.button("I have returned to work today"):
            db.table("bookings").update({"end_date": str(datetime.now().date()), "sickness_closed_by_emp": True}).eq("id", os.data[0]['id']).execute()
            st.rerun()

    # Tab Setup
    reports_res = db.table("employees").select("employee_id, full_name, role").eq("manager_id", mid).execute()
    t_titles = ["Dashboard", "Calendar"]
    if role == "Office": t_titles.append("Flexi-Time")
    if reports_res.data: t_titles.append("Team Management")
    tabs = st.tabs(t_titles)

    with tabs[0]: # DASHBOARD
        raw_allowance = float(u.get('contractual_allowance', 0))
        disp_bal = raw_allowance * 7.5 if role == "Factory" else raw_allowance
        st.metric(f"Holiday Balance", f"{disp_bal} {'Hours' if role == 'Factory' else 'Days'}")
        st.divider()
        st.subheader("Request Personal Leave")
        lt = st.selectbox("Type", ["Annual Leave", "Purchased Holiday", "Flexi-Leave"], key="u_lt")
        dur = st.radio("Duration", ["Full Day", "AM Half Day", "PM Half Day"], horizontal=True, key="u_dur")
        c1, c2 = st.columns(2)
        d1 = c1.date_input("Start Date", key="u_d1")
        d2 = c2.date_input("End Date", key="u_d2") if dur == "Full Day" else d1
        if st.button("Submit Request"):
            db.table("bookings").insert({"employee_id": mid, "start_date": str(d1), "end_date": str(d2), "status": "Pending", "day_type": dur, "holiday_year": get_year(d1), "leave_type": lt}).execute()
            st.toast("Submitted!")

    with tabs[1]: # CALENDAR
        n1, n2, n3 = st.columns([1,3,1])
        if n1.button("◀"):
            st.session_state.cal_month -= 1
            if st.session_state.cal_month < 1: st.session_state.cal_month = 12; st.session_state.cal_year -= 1
            st.rerun()
        n2.markdown(f"<h3 style='text-align: center;'>{calendar.month_name[st.session_state.cal_month]} {st.session_state.cal_year}</h3>", unsafe_allow_html=True)
        if n3.button("▶"):
            st.session_state.cal_month += 1
            if st.session_state.cal_month > 12: st.session_state.cal_month = 1; st.session_state.cal_year += 1
            st.rerun()

        bk = db.table("bookings").select("*").eq("employee_id", mid).execute().data
        cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
        cols = st.columns(7)
        for i, wd in enumerate(["M","T","W","T","F","S","S"]): cols[i].write(wd)
        for week in cal:
            row = st.columns(7)
            for i, d in enumerate(week):
                if d != 0:
                    dt_s = f"{st.session_state.cal_year}-{st.session_state.cal_month:02d}-{d:02d}"
                    act = next((b for b in bk if b['start_date'] <= dt_s and (b.get('end_date') is None or dt_s <= b['end_date']) and b['status'] != 'Rejected'), None)
                    if act:
                        bg = "#661026" if act['status'] == "Approved" else "gold"
                        row[i].markdown(f'<div style="background:{bg}; color:white; text-align:center; border-radius:5px; padding:5px;">{d}</div>', unsafe_allow_html=True)
                    else: row[i].write(d)

    # FLEXI-TIME (Office Only)
    if role == "Office":
        with tabs[2]: 
            st.subheader("Daily Flexi Calculator")
            c_flex = float(u.get('flexi_balance', 0))
            f1, f2 = st.columns(2)
            st_t = f1.time_input("Start", value=datetime.strptime("08:00", "%H:%M"))
            en_t = f2.time_input("Finish", value=datetime.strptime("17:00", "%H:%M"))
            br = st.number_input("Break (m)", 60)
            wk_h = (datetime.combine(datetime.today(), en_t) - datetime.combine(datetime.today(), st_t)).total_seconds()/3600 - (br/60)
            diff = wk_h - 7.5
            st.metric("Today's Change", f"{diff:+.2f}h")
            if st.button("Save Entry to Flexi-Log"):
                db.table("flexi_logs").insert({"employee_id": mid, "date": str(datetime.now().date()), "hours_worked": diff, "start_time": str(st_t), "end_time": str(en_t)}).execute()
                db.table("employees").update({"flexi_balance": c_flex + diff}).eq("employee_id", mid).execute()
                st.success("Balance updated!")
                st.rerun()
            
            st.divider()
            st.subheader("Recent Entries")
            hist = db.table("flexi_logs").select("*").eq("employee_id", mid).order("date", desc=True).limit(5).execute()
            if hist.data:
                st.table(pd.DataFrame(hist.data)[['date', 'start_time', 'end_time', 'hours_worked']])

    # TEAM MANAGEMENT
    if reports_res.data:
        with tabs[-1]: 
            r_list = reports_res.data
            r_ids = [str(r['employee_id']) for r in r_list]
            cl, cr = st.columns(2)
            with cl:
                st.subheader("Holiday Approvals")
                pen = db.table("bookings").select("*").in_("employee_id", r_ids).eq("status", "Pending").neq("leave_type", "Sickness").execute().data
                for p in pen:
                    p_n = next(r['full_name'] for r in r_list if str(r['employee_id']) == str(p['employee_id']))
                    st.info(f"{p_n}: {p['start_date']}")
                    if st.button("Approve", key=f"a{p['id']}"):
                        rep_r = next(r for r in r_list if str(r['employee_id']) == str(p['employee_id']))
                        h = calc_deduct(datetime.strptime(p['start_date'],"%Y-%m-%d"), datetime.strptime(p['end_date'],"%Y-%m-%d"), p['day_type'], rep_r['role'])
                        f_d = (h/7.5) if rep_r['role'] == "Factory" else h
                        cur_b = db.table("employees").select("contractual_allowance").eq("employee_id", p['employee_id']).execute().data[0]['contractual_allowance']
                        db.table("employees").update({"contractual_allowance": float(cur_b)-f_d}).eq("employee_id", p['employee_id']).execute()
                        db.table("bookings").update({"status": "Approved"}).eq("id", p['id']).execute()
                        st.rerun()
            with cr:
                st.subheader("Sickness Management")
                tr = st.selectbox("Log Sickness For:", [r['full_name'] for r in r_list])
                if st.button("Log Sickness Start"):
                    rid = next(r['employee_id'] for r in r_list if r['full_name'] == tr)
                    db.table("bookings").insert({"employee_id": rid, "start_date": str(datetime.now().date()), "leave_type": "Sickness", "status": "Approved", "sickness_closed_by_emp": False, "rtw_completed": False}).execute()
                    st.rerun()
                rtw = db.table("bookings").select("*").in_("employee_id", r_ids).eq("leave_type", "Sickness").eq("sickness_closed_by_emp", True).eq("rtw_completed", False).execute().data
                for s in rtw:
                    sn = next(r['full_name'] for r in r_list if str(r['employee_id']) == str(s['employee_id']))
                    if st.button(f"Mark RTW Complete: {sn}", key=f"s{s['id']}"):
                        db.table("bookings").update({"rtw_completed": True}).eq("id", s['id']).execute()
                        st.rerun()