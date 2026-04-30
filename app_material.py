import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime
import io
import uuid

# --- CONFIG ---
st.set_page_config(page_title="TACO Procurement", layout="wide", page_icon="🏢")
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
        else:
            return None
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
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def batch_save_data(sheet_name, data_list):
    sh = connect_to_gsheet()
    if sh:
        ws = sh.worksheet(sheet_name)
        ws.append_rows(data_list)
        return True
    return False
    
# --- HELPER ---
def create_match_key(pr, desc, desc2):
    """Fungsi untuk membuat kunci pencocokan status terkirim menggunakan parameter yang dipassing"""
    p = str(pr).strip()
    d1 = str(desc).strip()
    d2 = "" if not desc2 or str(desc2).lower() == 'nan' else str(desc2).strip()
    return f"{p}_{d1}_{d2}".lower()

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
    # --- HEADER DENGAN LOGO ---
    col_logo, col_title = st.columns([1, 8])
    with col_logo:
        # Pastikan file image_logo.png ada di folder yang sama dengan app.py
        if os.path.exists("image_logo.png"):
            st.image("image_logo.png", width=80)
        else:
            st.write("🏢") # Fallback jika file gambar tidak ditemukan
    with col_title:
        st.title("🏢 TACO Procurement RFQ")
    st.subheader("Pilih Portal:")
    st.write("---")
    
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 🛠️ Sparepart")
            st.write("Pengadaan sparepart mesin dan maintenance.")
            if st.button("Masuk", use_container_width=True, type="primary"):
                st.session_state['app_mode'] = "mat_Login"
                st.rerun()
                
    with c2:
        with st.container(border=True):
            st.markdown("### 🚛 Transport")
            st.write("Pengadaan transport dan logistik.")
            # Link ke Apps Transport
            st.link_button("Masuk", "https://taco-transport.streamlit.app", use_container_width=True)

def show_login():
      
    # --- HEADER LOGIN DENGAN LOGO ---
    col_logo, col_title = st.columns([1, 8])
    with col_logo:
        if os.path.exists("image_logo.png"):
            st.image("image_logo.png", width=60)
        else:
            st.write("🔐")
    with col_title:
        st.title("🛠️ TACO Sparepart RFQ")

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
    
    # --- TOP BAR (MENGGANTIKAN SIDEBAR) ---
    col_u, col_sp, col_lo = st.columns([3, 5, 1])
    with col_u:
        st.title(f"👋 Welcome, **{user.get('vendor_name', 'User')}**")
    with col_lo:
        if st.button("Log Out", type="secondary", use_container_width=True):
            st.session_state['user_info'] = None
            st.session_state['selected_items_dict'] = {}
            st.rerun()
    st.divider()

    if user['role'] == 'admin':
        admin_portal()
    else:
        vendor_portal(user['email'])

# --- CALLBACK TETAP SAMA TAPI PAKAI ID DARI KOLOM NO ---
def sync_checkbox(id_sistem, widget_key):
    st.session_state['selected_items_dict'][id_sistem] = st.session_state[widget_key]

def admin_portal():
    tabs = st.tabs(["📥 Import PR List", "📊 Monitoring & Comparison", "🔍 History"])
    df_access = get_data("Access_Goods")
    already_published_keys = set()
    if not df_access.empty:
        # Kita asumsikan ada kolom pr_number, item_name, specification di sheet Access_Goods
        for _, row in df_access.iterrows():
            key = create_match_key(row.get('pr_number', ''), row.get('item_name', ''), row.get('specification', ''))
            already_published_keys.add(key)
    

    with tabs[0]:
        st.header("Upload Purchase Request Taconnect")
        uploaded_file = st.file_uploader("Upload File Excel", type=['xlsx'])
        if uploaded_file:
            # Baca Excel, header ada di baris ke-3 (index 2)
            df_raw = pd.read_excel(uploaded_file, header=2)
            df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
            df_raw['ID_SISTEM'] = df_raw.apply(lambda row: create_match_key(row.get('PR CODE', ''), row.get('DESCRIPTION', ''), row.get('DESCRIPTION 2', '')), axis=1)   

            if 'selected_items_dict' not in st.session_state:
                st.session_state['selected_items_dict'] = {}

            df_display = df_raw.copy()
            if 'STATUS' in df_raw.columns and 'QUANTITY' in df_raw.columns:
                df_raw['QUANTITY'] = pd.to_numeric(df_raw['QUANTITY'], errors='coerce').fillna(0)
                df_display = df_raw[
                    (df_raw['STATUS'].astype(str).str.strip() == 'Open') &
                    (df_raw['QUANTITY'] > 0)
                ].copy()

            if not df_display.empty:
                st.subheader("📝Pilih Item / PR")
                search_query = st.text_input("🔍 Cari No. PR atau Nama Item...", placeholder="Ketik di sini...")

                df_to_show = df_display.copy()
                if search_query:
                    q = search_query.lower()
                    mask = (
                        df_to_show['PR CODE'].astype(str).str.lower().str.contains(q, regex=False, na=False) |
                        df_to_show['DESCRIPTION'].astype(str).str.lower().str.contains(q, regex=False, na=False)
                    )
                    df_to_show = df_to_show[mask]

                with st.container(height=550, border=True):
                    for pr_no in df_to_show['PR CODE'].unique():
                        df_group = df_to_show[df_to_show['PR CODE'] == pr_no].copy().reset_index(drop=True)
                        loc = df_group['LOCATION'].iloc[0] if 'LOCATION' in df_group.columns else "-"
                        prio_raw = str(df_group['PRIORITY STATUS'].iloc[0]) if 'PRIORITY STATUS' in df_group.columns else "-"
                        prio = prio_raw[:6]

                        if "URGENT" in prio:
                            header_label = f"📄 PR: {pr_no} | 📍 {loc} | 🚨 [URGENT] "
                        else:
                            header_label = f"📄 PR: {pr_no} | 📍 {loc}"
                        
                        with st.expander(header_label):
                            c1, c2, _ = st.columns([1, 1, 3])

                            if c1.button("✅ Pilih Semua", key=f"all_btn_{pr_no}"):
                                for k in df_group['ID_SISTEM']:
                                    st.session_state['selected_items_dict'][k] = True
                                    st.session_state[f"chk_{k}"] = True                                    
                                st.rerun()

                            if c2.button("🗑️ Hapus Semua", key=f"none_btn_{pr_no}"):
                                for k in df_group['ID_SISTEM']:
                                    st.session_state['selected_items_dict'][k] = False
                                    st.session_state[f"chk_{k}"] = False  
                                st.rerun()

                            h1, h2, h3, h4, h5 = st.columns([0.5, 3, 3, 1, 1])
                            h1.markdown("**✓**")
                            h2.markdown("**Description**")
                            h3.markdown("**Description 2**")
                            h4.markdown("**Qty**")
                            h5.markdown("**UOM**")

                            for idx, item_row in df_group.iterrows():
                                id_sistem = item_row['ID_SISTEM']
                                row_key = id_sistem
                                match_key = create_match_key(pr_no, item_row.get('DESCRIPTION', ''), item_row.get('DESCRIPTION 2', ''))

                                widget_key = f"chk_{id_sistem}"
                                
                                is_published = match_key in already_published_keys
                                bg_color = "#d1fae5" if is_published else "transparent" # Warna hijau muda jika sudah dipublish
                                
                                # Render Baris dengan Style
                                container = st.container()
                                with container:
                                    # Gunakan HTML/CSS minimal untuk warna background per baris
                                    st.markdown(
                                        f"""<div style="background-color:{bg_color}; padding:5px; border-radius:5px; margin-bottom:2px;">""", 
                                        unsafe_allow_html=True
                                    )
                                    c1, c2, c3, c4, c5= st.columns([0.5, 3, 3, 1, 1])
                                    
                                    widget_key = f"chk_{row_key}"
                                    c1.checkbox("select", key=widget_key, 
                                                value=st.session_state['selected_items_dict'].get(row_key, False),
                                                on_change=sync_checkbox, args=(row_key, widget_key),
                                                label_visibility="collapsed")
                                    
                                    c2.write(item_row.get('DESCRIPTION', ''))
                                    c3.write(item_row.get('DESCRIPTION 2', ''))
                                    c4.write(item_row.get('QUANTITY', ''))
                                    c5.write(item_row.get('UOM', ''))
                                    

                # --- LANGKAH 2 (Review) ---
                st.divider()
                st.subheader("🎯 Review & Assign Vendor")
                
                selected_keys = [k for k, v in st.session_state['selected_items_dict'].items() if v]
                
                # Filter final_items pakai ID_SISTEM (Kolom NO)
                final_items = df_display[df_display['ID_SISTEM'].isin(selected_keys)].copy()

                if not final_items.empty:
                    with st.expander(f"📋 Item Terpilih ({len(final_items)} item)", expanded=True):
                        st.dataframe(
                            final_items[['PR CODE', 'DESCRIPTION', 'DESCRIPTION 2', 'QUANTITY', 'UOM']],
                            hide_index=True,
                            use_container_width=True
                        )
                        if st.button("🚨 Reset Semua Pilihan"):
                            st.session_state['selected_items_dict'] = {}
                            for k in list(st.session_state.keys()):
                                if k.startswith("chk_"): del st.session_state[k]
                            st.rerun()
                    

                    df_u = get_data("Users")
                    vendors = df_u[df_u['role'] == 'vendor']['vendor_name'].tolist() if not df_u.empty else []
                    sel_v = st.multiselect("Pilih Vendor Penerima RFQ:", vendors)

                    if st.button("🚀 Publish Undangan RFQ", type="primary", use_container_width=True):
                        if not sel_v:
                            st.error("Silakan pilih minimal satu vendor.")
                        else:
                            with st.spinner("Sedang memproses database..."):
                                # 1. SIAPKAN DATA UNTUK Access_Goods (Hak akses vendor)
                                access_data = []
                                master_data = []
                                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                
                                # Loop setiap item yang dicentang
                                for _, item in final_items.iterrows():
                                    pr_no = str(item['PR CODE'])
                                    i_name = str(item['DESCRIPTION'])
                                    i_spec = str(item.get('DESCRIPTION 2',''))
                                    loc = str(item.get('LOCATION',''))
                                    
                                    # ID Unique untuk Master (Kunci Utama)
                                    id_unique = create_match_key(pr_no, i_name, i_spec)

                                    # Tambahkan ke list Master_Items (Database Induk)
                                    # Format: id_unique, pr_number, location, item_name, specification, qty, uom, category
                                    master_data.append([
                                        id_unique, pr_no, loc, i_name, i_spec
                                    ])

                                    # Tambahkan ke list Access_Goods untuk setiap vendor yang dipilih
                                    for v_email in sel_v:
                                        access_data.append([
                                            id_unique, pr_no, loc, i_name, i_spec, qty, uom, v_email, "Open", ts
                                        ])
                                
                                # 2. EKSEKUSI SIMPAN BATCH
                                # Simpan ke Access_Goods
                                success_access = batch_save_data("Access_Goods", access_data)
                                
                                success_master = batch_save_data("Master_Items", master_data)
                                
                                if success_access and success_master:
                                    st.success(f"✅ Berhasil! Data tersimpan di Master & RFQ dikirim ke {len(sel_v)} vendor.")
                                    
                                    # Reset UI
                                    st.session_state['selected_items_dict'] = {}
                                    for k in list(st.session_state.keys()):
                                        if k.startswith("chk_"):
                                            del st.session_state[k]
                                    st.rerun()
                                else:
                                    st.error("Gagal menyimpan data ke salah satu sheet. Periksa koneksi.")

    # --- TAB LAINNYA ---
    with tabs[1]:
        st.header("Price Comparison Analysis")
        df_prices = get_data("Price_Goods")
        if df_prices.empty:
            st.info("Belum ada penawaran masuk dari vendor.")
        else:
            df_master = get_data("Master_Items")
            df_merged = pd.merge(df_prices, df_master[['id_unique', 'item_name', 'specification', 'qty', 'uom']], on='id_unique', how='left')
            if 'pr_number' in df_merged.columns:
                pr_list = df_merged['pr_number'].unique()
                sel_pr = st.selectbox("Pilih Nomor PR:", pr_list)
                sub_comp = df_merged[df_merged['pr_number'] == sel_pr]
                pivot_df = sub_comp.pivot_table(index=['item_name', 'specification', 'qty', 'uom'], columns='vendor_email', values='unit_price', aggfunc='min').reset_index()
                st.write(f"### Perbandingan Harga PR: {sel_pr}")
                identitas_cols = ['item_name', 'specification', 'qty', 'uom']
                harga_cols = [c for c in pivot_df.columns if c not in identitas_cols]
                if harga_cols:
                    st.dataframe(pivot_df.style.highlight_min(axis=1, color='#d1fae5', subset=harga_cols), use_container_width=True)
                else:
                    st.dataframe(pivot_df, use_container_width=True)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    pivot_df.to_excel(writer, index=False)
                st.download_button("📥 Download Report Excel", output.getvalue(), f"Comparison_{sel_pr}.xlsx")

def vendor_portal(email):
    st.header("📝 Form Penawaran Harga")
    df_acc = get_data("Access_Goods")
    my_acc = df_acc[df_acc['vendor_email'] == email]
    if my_acc.empty:
        st.info("Tidak ada permintaan RFQ untuk Anda.")
        return
    df_master = get_data("Master_Items")
    df_my_items = df_master[df_master['id_unique'].isin(my_acc['id_unique'])]
    display_cols = ['id_unique', 'pr_number', 'location', 'item_name', 'specification', 'uom', 'qty']
    for pr in df_my_items['pr_number'].unique():
        with st.expander(f"📋 PR: {pr}", expanded=True):
            sub_items = df_my_items[df_my_items['pr_number'] == pr][display_cols].copy()
            sub_items['Unit_Price'] = 0.0
            sub_items['Brand'] = "-"
            sub_items['Lead_Time_Days'] = 7
            edited = st.data_editor(sub_items, key=f"edit_{pr}", hide_index=True, use_container_width=True, disabled=display_cols)
            if st.button(f"Kirim Penawaran PR {pr}", key=f"save_{pr}"):
                price_rows = []
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for _, r in edited.iterrows():
                    price_rows.append([f"P-{uuid.uuid4().hex[:6]}", pr, email, r['id_unique'], r['Unit_Price'], r['Brand'], r['Lead_Time_Days'], ts, "Open"])
                if batch_save_data("Price_Goods", price_rows):
                    st.success("Berhasil mengirim penawaran!")

if __name__ == "__main__":
    main()
