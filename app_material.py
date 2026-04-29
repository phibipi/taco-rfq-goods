import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime
import io
import uuid

# --- CONFIG ---
st.set_page_config(page_title="TACO Procurement Hub", layout="wide", page_icon="🏢")
SPREADSHEET_ID_GOODS = "1nuU8s1ahNfQsCV-zdIh5QiiLuMc8MgJQWxl1Op3eMD0"

# --- DATABASE CONNECTION ---
@st.cache_resource
def connect_to_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        elif os.path.exists("kunci_goods.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("kunci_goods.json", scope)
        else: return None
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID_GOODS)
    except Exception as e:
        st.error(f"Koneksi Gagal: {e}")
        return None

def get_data(sheet_name):
    sh = connect_to_gsheet()
    if sh:
        try:
            ws = sh.worksheet(sheet_name)
            data = ws.get_all_records()
            df = pd.DataFrame(data)
            df.columns = [str(c).strip().lower() for c in df.columns]
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

# --- CALLBACK UNTUK CHECKBOX (SMART UNIQUE ID) ---
def sync_checkbox(id_sistem, widget_key):
    st.session_state['selected_items_dict'][id_sistem] = st.session_state[widget_key]

# --- MAIN APP LOGIC ---
def main():
    # State Inisialisasi
    if 'user_info' not in st.session_state: st.session_state['user_info'] = None
    if 'app_mode' not in st.session_state: st.session_state['app_mode'] = "Landing"
    if 'selected_items_dict' not in st.session_state: st.session_state['selected_items_dict'] = {}
    if 'df_raw_draft' not in st.session_state: st.session_state['df_raw_draft'] = None

    # 1. Halaman Induk (Sebelum Login)
    if st.session_state['app_mode'] == "Landing":
        show_landing_page()
    
    # 2. Halaman Login (Setelah pilih Rawmat)
    elif st.session_state['user_info'] is None:
        show_login()
    
    # 3. Halaman Dashboard (Setelah Login)
    else:
        show_dashboard()

def show_landing_page():
    st.title("🏢 TACO Procurement Hub")
    st.subheader("Pilih Modul Kerja:")
    st.write("---")
    
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 📦 Rawmat & Sparepart")
            st.write("Pengadaan barang, sparepart mesin, dan bahan baku.")
            if st.button("Masuk Modul Rawmat", use_container_width=True, type="primary"):
                st.session_state['app_mode'] = "Rawmat_Login"
                st.rerun()
                
    with c2:
        with st.container(border=True):
            st.markdown("### 🚛 Transport")
            st.write("Pengadaan jasa angkutan dan logistik.")
            # Link ke Apps Transport
            st.link_button("Buka Modul Transport ↗️", "https://taco-transport.streamlit.app", use_container_width=True)

def show_login():
    if st.button("⬅️ Kembali"):
        st.session_state['app_mode'] = "Landing"
        st.rerun()
        
    st.title("🔐 Login Modul Rawmat")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.container(border=True):
            email_input = st.text_input("Email").strip().lower()
            password_input = st.text_input("Password", type="password").strip()
            if st.button("Masuk", type="primary", use_container_width=True):
                df_users = get_data("Users")
                user = df_users[(df_users['email'].astype(str).str.lower() == email_input) & 
                                (df_users['password'].astype(str) == password_input)]
                if not user.empty:
                    st.session_state['user_info'] = user.iloc[0].to_dict()
                    st.rerun()
                else:
                    st.error("Email atau Password salah.")

def show_dashboard():
    user = st.session_state['user_info']
    st.sidebar.title(f"👋 {user.get('vendor_name', 'User')}")
    st.sidebar.info(f"Modul: **Rawmat & Sparepart**")
    
    if st.sidebar.button("Log Out"):
        # Clear session tapi jangan hapus app_mode supaya balik ke landing
        st.session_state['user_info'] = None
        st.session_state['app_mode'] = "Landing"
        st.rerun()

    if user['role'] == 'admin':
        admin_portal()
    else:
        vendor_portal(user['email'])

def admin_portal():
    tabs = st.tabs(["📥 Import PR List", "📊 Monitoring", "🔍 History"])

    with tabs[0]:
        # --- FITUR RESUME UPLOAD ---
        if st.session_state['df_raw_draft'] is not None:
            with st.info("ℹ️ Kamu punya draft upload sebelumnya."):
                ca, cb = st.columns(2)
                if ca.button("✅ Gunakan File Terakhir", use_container_width=True):
                    uploaded_file = "RESUME"
                if cb.button("❌ Upload Baru", use_container_width=True):
                    st.session_state['df_raw_draft'] = None
                    st.session_state['selected_items_dict'] = {}
                    st.rerun()
        
        if st.session_state['df_raw_draft'] is None:
            raw_upload = st.file_uploader("Upload File Excel Taconnect", type=['xlsx'])
            if raw_upload:
                df = pd.read_excel(raw_upload, header=2)
                df.columns = [str(c).strip().upper() for c in df.columns]
                # Gunakan kolom NO sebagai ID unik (Ide cerdas kamu!)
                df['ID_SISTEM'] = df['NO'].astype(str) if 'NO' in df.columns else df.index.astype(str)
                st.session_state['df_raw_draft'] = df
                st.rerun()
            return

        df_display = st.session_state['df_raw_draft']
        
        # --- FITUR HIGHLIGHT RFQ (SUDAH PERNAH DIKIRIM) ---
        df_history = get_data("Master_Items")
        history_keys = []
        if not df_history.empty:
            # Gabungkan PR Code dan Nama Item untuk cek duplikasi history
            history_keys = (df_history['pr_number'].astype(str) + df_history['item_name'].astype(str)).tolist()

        st.subheader("📝 Langkah 1: Pilih Item")
        # Loop Expander per PR
        for pr_no in df_display['PR CODE'].unique():
            df_group = df_display[df_display['PR CODE'] == pr_no].copy().reset_index(drop=True)
            with st.expander(f"📄 PR: {pr_no}"):
                for idx, row in df_group.iterrows():
                    id_s = row['ID_SISTEM']
                    w_key = f"chk_{id_s}"
                    
                    # Cek apakah sudah pernah di RFQ (Highlight Hijau)
                    is_sent = (str(row['PR CODE']) + str(row['DESCRIPTION'])) in history_keys
                    bg_color = "#d1fae5" if is_sent else "transparent"
                    
                    st.markdown(f"""<div style="background-color:{bg_color}; padding:8px; border-radius:5px; margin-bottom:2px; border: 1px solid #eee;">""", unsafe_allow_html=True)
                    c1, c2, c3, c4 = st.columns([0.5, 4, 1, 1])
                    
                    c1.checkbox("ok", key=w_key, 
                                value=st.session_state['selected_items_dict'].get(id_s, False),
                                on_change=sync_checkbox, args=(id_s, w_key), label_visibility="collapsed")
                    
                    label_sent = " ✅ (SENT)" if is_sent else ""
                    c2.write(f"**{row['DESCRIPTION']}**{label_sent}")
                    c3.write(f"{row['QUANTITY']}")
                    c4.write(f"{row['UOM']}")
                    st.markdown("</div>", unsafe_allow_html=True)

        # --- LANGKAH 2: REVIEW ---
        st.divider()
        selected_ids = [k for k, v in st.session_state['selected_items_dict'].items() if v]
        df_final = df_display[df_display['ID_SISTEM'].isin(selected_ids)]

        if not df_final.empty:
            st.subheader(f"🎯 Langkah 2: Assign Vendor ({len(df_final)} item)")
            st.dataframe(df_final[['PR CODE', 'DESCRIPTION', 'QUANTITY', 'UOM']], hide_index=True)
            if st.button("🚀 Publish RFQ"):
                st.success("RFQ Berhasil Dikirim!")
                # Reset setelah sukses
                st.session_state['selected_items_dict'] = {}
                st.rerun()

def vendor_portal(email):
    st.write("Halaman Vendor")

if __name__ == "__main__":
    main()
