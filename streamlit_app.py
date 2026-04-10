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
def get_year_str(dt): return f"{dt.year}/{dt.year+1}" if dt.month >= 4 else f"{dt.year-1}/{dt.year}"
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
    try: st.image("dale_logo.png", width=250)
    except: st.write("") 
    st.title("FHD Employee Portal")
    eid, pin = st.text_input("Employee ID"), st.text_input("PIN", type="password")
    if st.button("Login"):
        r = db.table("employees").select("*").eq("employee_id", eid).execute()
        if r.data and str(r.data[0].get('pin')) == str(pin):
            st.session_state['auth'], st.session_state['user'] = True, r.data[0]
            st.rerun()

# --- 5. AUTHENTICATED VIEW ---
else:
    u = db.table("employees").select("*").eq("employee_id", st.session_state['user']['employee_id']).execute().data[0]
    mid, role = u['employee_id'], u.get('role', 'Office')
    cur_yr = get_year_str(datetime.now())

    # Header
    col_a, col_b, col_c = st.columns([1,3,1])
    with col_a:
        try: st.image("dale_logo.png", width=80)
        except: st.subheader("FHD")
    with col_b: st.subheader(f"Hi, {u.get('full_name')}")
    with col_c:
        if st.button("Logout"):
            st.session_state['auth'] = False
            st.rerun()

    # Sickness Alert (Employee Side)
    os = db.table("bookings").select("*").eq("employee_id", mid).eq("leave_type", "Sickness").eq("sickness_closed_by_emp", False).execute()
    if os.data:
        st.warning(f"⚠️ Sickness Active (Started: {os.data[0]['start_date']})")
        if st.button("I have returned to work today"):
            db.table("bookings").update({"end_date": str(datetime.now().date()), "sickness_closed_by_emp": True}).eq("id", os.data[0]['id']).execute()
            st.rerun()

    reports_res = db.table("employees").select("employee_id, full_name, role").eq("manager_id", mid).execute()
    t_titles = ["Dashboard", "Request Leave", "Calendar"]
    if role == "Office": t_titles.append("Flexi-Time")
    if reports_res.data: t_titles.append("Team Management")
    tabs = st.tabs(t_titles)

    with tabs[0]: # DASHBOARD
        p_res = db.table("purchased_leave").select("*").eq("employee_id", mid).eq("year", cur_yr).execute()
        p_pot = p_res.data[0] if p_res.data else {"total_purchased": 0, "amount_used": 0}
        mult = 7.5 if role == "Factory" else 1.0
        unit = "Hours" if role == "Factory" else "Days"

        st.subheader("Entitlement Overview")
        m_cols = st.columns(3 if role == "Office" else 2)
        m_cols[0].metric("Contractual", f"{float(u.get('contractual_allowance', 0)) * mult} {unit}")
        m_cols[1].metric("Purchased", f"{(float(p_pot['total_purchased']) - float(p_pot['amount_used'])) * mult} {unit}")
        
        if role == "Office":
            today = datetime.now().date()
            start_of_week = today - timedelta(days=today.weekday())
            w_flex = db.table("flexi_logs").select("hours_worked").eq("employee_id", mid).gte("date", str(start_of_week)).execute()
            weekly_bal = sum(float(item['hours_worked']) for item in w_flex.data)
            m_cols[2].metric("Weekly Flexi", f"{weekly_bal:+.2f}h")

        st.divider()
        st.subheader("Recent Activity")
        recent = db.table("bookings").select("*").eq("employee_id", mid).order("id", desc=True).limit(5).execute()
        if recent.data: st.table(pd.DataFrame(recent.data)[['start_date', 'leave_type', 'status']])

    with tabs[1]: # REQUEST LEAVE
        st.subheader("Book New Leave")
        lt = st.selectbox("Type", ["Annual Leave", "Purchased Holiday", "Unpaid Leave", "Other"], key="req_lt")
        dur = st.radio("Duration", ["Full Day", "AM Half Day", "PM Half Day"], horizontal=True, key="req_dur")
        d1 = st.date_input("Start Date", key="req_d1")
        d2 = st.date_input("End Date", key="req_d2") if dur == "Full Day" else d1
        if st.button("Submit Request", type="primary"):
            db.table("bookings").insert({"employee_id": mid, "start_date": str(d1), "end_date": str(d2), "status": "Pending", "day_type": dur, "holiday_year": get_year_str(d1), "leave_type": lt, "sickness_closed_by_emp": True}).execute()
            st.toast("Submitted!")
            st.rerun()

    with tabs[2]: # CALENDAR
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

        bk_list = db.table("bookings").select("*").eq("employee_id", mid).execute().data
        cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
        cols = st.columns(7)
        for i, wd in enumerate(["M","T","W","T","F","S","S"]): cols[i].write(wd)
        for week in cal:
            row = st.columns(7)
            for i, d in enumerate(week):
                if d != 0:
                    dt_s = f"{st.session_state.cal_year}-{st.session_state.cal_month:02d}-{d:02d}"
                    act = next((b for b in bk_list if b['start_date'] <= dt_s and (b.get('end_date') is None or dt_s <= b['end_date']) and b['status'] != 'Rejected'), None)
                    if act:
                        bg = "gold"
                        if act['status'] == "Approved":
                            if act['leave_type'] == "Annual Leave": bg = "#2e7d32"
                            elif act['leave_type'] == "Purchased Holiday": bg = "#661026"
                            elif act['leave_type'] == "Unpaid Leave": bg = "#1565c0"
                            elif act['leave_type'] == "Other": bg = "#fbc02d"
                        row[i].markdown(f'<div style="background:{bg}; color:white; text-align:center; border-radius:5px; padding:5px; font-weight:bold;">{d}</div>', unsafe_allow_html=True)
                    else: row[i].write(d)

    if role == "Office":
        with tabs[3]: # FLEXI-TIME
            st.subheader("Daily Flexi Calculator")
            f1, f2 = st.columns(2)
            st_t, en_t = f1.time_input("Start"), f2.time_input("Finish")
            br = st.number_input("Break (m)", 60)
            wk_h = (datetime.combine(datetime.today(), en_t) - datetime.combine(datetime.today(), st_t)).total_seconds()/3600 - (br/60)
            st.metric("Today's Change", f"{wk_h-7.5:+.2f}h")
            if st.button("Save to Log"):
                db.table("flexi_logs").insert({"employee_id": mid, "date": str(datetime.now().date()), "hours_worked": wk_h-7.5, "start_time": str(st_t), "end_time": str(en_t)}).execute()
                db.table("employees").update({"flexi_balance": float(u.get('flexi_balance', 0)) + (wk_h-7.5)}).eq("employee_id", mid).execute()
                st.rerun()

    if reports_res.data:
        with tabs[-1]: # TEAM MANAGEMENT
            r_l = reports_res.data
            r_ids = [str(r['employee_id']) for r in r_l]
            cl, cr = st.columns(2)
            with cl:
                st.subheader("Approvals")
                pen = db.table("bookings").select("*").in_("employee_id", r_ids).eq("status", "Pending").neq("leave_type", "Sickness").execute().data
                if not pen: st.info("No pending requests.")
                for p in pen:
                    nm = next(r['full_name'] for r in r_l if str(r['employee_id']) == str(p['employee_id']))
                    rep_r = next(r for r in r_l if str(r['employee_id']) == str(p['employee_id']))
                    h_impact = calc_deduct(datetime.strptime(p['start_date'],"%Y-%m-%d"), datetime.strptime(p['end_date'],"%Y-%m-%d"), p['day_type'], rep_r['role'])
                    u_label = "Hours" if rep_r['role'] == "Factory" else "Days"
                    
                    with st.expander(f"📌 {nm}: {p['start_date']}", expanded=True):
                        st.write(f"**Impact:** {h_impact} {u_label} ({p['leave_type']})")
                        b1, b2 = st.columns(2)
                        if b1.button("Approve", key=f"a{p['id']}", type="primary"):
                            f_u = (h_impact/7.5) if rep_r['role'] == "Factory" else h_impact
                            if p['leave_type'] == "Purchased Holiday":
                                p_rec = db.table("purchased_leave").select("*").eq("employee_id", p['employee_id']).eq("year", p['holiday_year']).execute().data[0]
                                db.table("purchased_leave").update({"amount_used": float(p_rec['amount_used']) + f_u}).eq("id", p_rec['id']).execute()
                            elif p['leave_type'] == "Annual Leave":
                                old_b = db.table("employees").select("contractual_allowance").eq("employee_id", p['employee_id']).execute().data[0]['contractual_allowance']
                                db.table("employees").update({"contractual_allowance": float(old_b)-f_u}).eq("employee_id", p['employee_id']).execute()
                            db.table("bookings").update({"status": "Approved"}).eq("id", p['id']).execute()
                            st.rerun()
                        if b2.button("Reject", key=f"r{p['id']}"):
                            db.table("bookings").update({"status": "Rejected"}).eq("id", p['id']).execute()
                            st.rerun()
            with cr:
                st.subheader("Sickness Management")
                tr = st.selectbox("Log Sickness For:", [r['full_name'] for r in r_l])
                if st.button("Log Sickness Start"):
                    rid = next(r['employee_id'] for r in r_l if r['full_name'] == tr)
                    db.table("bookings").insert({"employee_id": rid, "start_date": str(datetime.now().date()), "leave_type": "Sickness", "status": "Approved", "sickness_closed_by_emp": False, "rtw_completed": False}).execute()
                    st.rerun()
                
                st.divider()
                st.write("**RTW Interviews Required:**")
                rtw_data = db.table("bookings").select("*").in_("employee_id", r_ids).eq("leave_type", "Sickness").eq("sickness_closed_by_emp", True).eq("rtw_completed", False).execute().data
                for s in rtw_data:
                    sn = next(r['full_name'] for r in r_l if str(r['employee_id']) == str(s['employee_id']))
                    if st.button(f"Mark RTW Complete: {sn}", key=f"s{s['id']}"):
                        db.table("bookings").update({"rtw_completed": True}).eq("id", s['id']).execute()
                        st.rerun()