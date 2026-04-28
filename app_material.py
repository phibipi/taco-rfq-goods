import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime
import io
import uuid

# --- CONFIG ---
st.set_page_config(page_title="TACO Goods Procurement", layout="wide", page_icon="📦")
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
            
            # --- PENGAMAN HEADER ---
            # Ini akan mengubah 'Email', 'EMAIL', atau ' email ' jadi 'email' secara otomatis
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

# --- MAIN APP LOGIC ---
def main():
    if 'user_info' not in st.session_state:
        st.session_state['user_info'] = None
    if 'selected_vendors' not in st.session_state:
        st.session_state['selected_vendors'] = []

    if st.session_state['user_info'] is None:
        show_login()
    else:
        show_dashboard()

def show_login():
    st.title("🏢 TACO E-Procurement (Goods)")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.container(border=True):
            # Kita bersihkan input user (hapus spasi & paksa huruf kecil)
            email_input = st.text_input("Email").strip().lower()
            password_input = st.text_input("Password", type="password").strip()
            
            if st.button("Masuk", type="primary", use_container_width=True):
                df_users = get_data("Users")
                
                if not df_users.empty:
                    # Kita cari user tanpa peduli huruf besar/kecil di Sheets
                    # Karena get_data sudah memaksa kolom jadi kecil, kita cari 'email' dan 'password'
                    user = df_users[
                        (df_users['email'].astype(str).str.lower() == email_input) & 
                        (df_users['password'].astype(str) == password_input)
                    ]
                    
                    if not user.empty:
                        st.session_state['user_info'] = user.iloc[0].to_dict()
                        st.rerun()
                    else:
                        st.error("Email atau Password salah. Cek kembali data di sheet 'Users'.")
                else:
                    st.error("Data User tidak ditemukan atau koneksi bermasalah.")

def show_dashboard():
    user = st.session_state['user_info']
    role = user['role']
    
    st.sidebar.title(f"👋 {user.get('vendor_name', 'User')}")
    st.sidebar.info(f"Modul: **Rawmat & Sparepart**")
    
    if st.sidebar.button("Log Out"):
        st.session_state['user_info'] = None
        st.rerun()

    if role == 'admin':
        admin_portal()
    else:
        vendor_portal(user['email'])

def admin_portal():
    tabs = st.tabs(["📥 Import PR List", "📊 Monitoring & Comparison", "🔍 History Search"])
    
    with tabs[0]:
        st.header("Upload Purchase Request Taconnect")
        uploaded_file = st.file_uploader("Upload File Excel PR View dari Taconnect", type=['xlsx'])
        
        if uploaded_file:
            df_raw = pd.read_excel(uploaded_file, header=2)
            df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
            
            if 'selected_items_dict' not in st.session_state:
                st.session_state['selected_items_dict'] = {}
            
            col_status = 'STATUS'
            col_qty = 'QUANTITY'
            
            if col_status in df_raw.columns and col_qty in df_raw.columns:
                df_raw[col_qty] = pd.to_numeric(df_raw[col_qty], errors='coerce').fillna(0)
                df_display = df_raw[(df_raw[col_status].astype(str).str.strip() == 'Open') & (df_raw[col_qty] > 0)].copy()
            else:
                df_display = df_raw.copy()

            if not df_display.empty:
                st.subheader("📝 Langkah 1: Pilih Item & Review List")
                search_query = st.text_input("🔍 Cari No. PR, Nama Item, atau Lokasi...", placeholder="Ketik di sini...")
                
                # Filter Search
                df_to_show = df_display.copy()
                if search_query:
                    q = search_query.lower()
                    mask = (
                        df_to_show['PR CODE'].astype(str).str.lower().str.contains(q, regex=False, na=False) |
                        df_to_show['DESCRIPTION'].astype(str).str.lower().str.contains(q, regex=False, na=False) |
                        df_to_show['DESCRIPTION 2'].astype(str).str.lower().str.contains(q, regex=False, na=False) |
                        df_to_show['LOCATION'].astype(str).str.lower().str.contains(q, regex=False, na=False)
                    )
                    df_to_show = df_to_show[mask]

                grouped_pr = df_to_show['PR CODE'].unique()

                # --- LANGKAH 1 ---
                with st.container(height=500, border=True):
                    for pr_no in grouped_pr:
                        df_pr_group = df_to_show[df_to_show['PR CODE'] == pr_no].copy()
                        loc_val = df_pr_group['LOCATION'].iloc[0] if 'LOCATION' in df_pr_group.columns else "Unknown"
                        header_text = f"📄 {pr_no} | 📍 {loc_val} | {df_pr_group['DESCRIPTION'].iloc[0][:40]}..."
                        
                        with st.expander(header_text, expanded=False):
                            # Master Checkbox per PR
                            sel_all_key = f"all_{pr_no}"
                            select_all_pr = st.checkbox(f"Pilih Semua Item di PR {pr_no}", key=sel_all_key)
                            
                            display_table_cols = ['DESCRIPTION', 'DESCRIPTION 2', 'QUANTITY', 'UOM']
                            df_view = df_pr_group[display_table_cols].copy()
                            df_view['unique_key'] = str(pr_no) + "_" + df_view['DESCRIPTION'].astype(str)
                            
                            # Update dictionary jika "Select All" berubah
                            if select_all_pr:
                                for k in df_view['unique_key']:
                                    st.session_state['selected_items_dict'][k] = True
                            elif not select_all_pr and st.session_state.get(f"prev_{sel_all_key}", False):
                                # Hanya unselect jika sebelumnya select all aktif (biar ga tabrakan sama manual edit)
                                for k in df_view['unique_key']:
                                    st.session_state['selected_items_dict'][k] = False
                            
                            st.session_state[f"prev_{sel_all_key}"] = select_all_pr

                            # Siapkan data untuk editor
                            current_selections = [st.session_state['selected_items_dict'].get(k, False) for k in df_view['unique_key']]
                            df_view.insert(0, "PILIH", current_selections)

                            # Menampilkan editor
                            edited_df = st.data_editor(
                                df_view.drop(columns=['unique_key']),
                                hide_index=True,
                                use_container_width=True,
                                column_config={
                                    "PILIH": st.column_config.CheckboxColumn("PILIH", default=False),
                                    "QUANTITY": st.column_config.NumberColumn("QTY", format="%d"),
                                },
                                disabled=['DESCRIPTION', 'DESCRIPTION 2', 'QUANTITY', 'UOM'],
                                key=f"ed_{pr_no}"
                            )
                            
                            # SYNC: Update memori berdasarkan hasil edit manual di tabel
                            # Kita deteksi mana yang berubah dan update session_state
                            for i, row in edited_df.iterrows():
                                item_key = str(pr_no) + "_" + str(row['DESCRIPTION'])
                                if st.session_state['selected_items_dict'].get(item_key) != row['PILIH']:
                                    st.session_state['selected_items_dict'][item_key] = row['PILIH']
                                    st.rerun() # Rerun di sini aman karena berada di dalam interaksi widget

                # --- LANGKAH 2 (REVIEW) ---
                st.divider()
                st.subheader("🎯 Langkah 2: Review & Assign Vendor")
                
                # Ambil item yang terpilih (True)
                selected_keys = [k for k, v in st.session_state['selected_items_dict'].items() if v]
                
                # Buat filter dari dataset asli
                df_display['unique_key'] = df_display['PR CODE'].astype(str) + "_" + df_display['DESCRIPTION'].astype(str)
                final_items = df_display[df_display['unique_key'].isin(selected_keys)].copy()

                if not final_items.empty:
                    with st.expander("📋 Daftar PR/Item yang dipilih", expanded=True):
                        st.dataframe(
                            final_items[['PR CODE', 'LOCATION', 'DESCRIPTION', 'DESCRIPTION 2', 'QUANTITY', 'UOM']], 
                            hide_index=True, use_container_width=True
                        )
                        st.info(f"Total: **{len(final_items)} item** terpilih.")
                        if st.button("🗑️ Kosongkan Pilihan"):
                            st.session_state['selected_items_dict'] = {}
                            st.rerun()
                    
                    df_users = get_data("Users")
                    list_vendors = df_users[df_users['role'] == 'vendor']['vendor_name'].tolist()
                    sel_vendors = st.multiselect("Pilih Vendor Penerima Undangan:", list_vendors)
                    
                    if st.button("🚀 Publish Undangan RFQ", type="primary", use_container_width=True):
                        if not sel_vendors:
                            st.error("Pilih vendor!")
                        else:
                            with st.spinner("Publishing..."):
                                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                m_rows, a_rows = [], []
                                v_map = {r['vendor_name']: r['email'] for _, r in df_users.iterrows() if r['role'] == 'vendor'}
                                
                                for _, row in final_items.iterrows():
                                    u_id = str(uuid.uuid4())[:8]
                                    m_rows.append([u_id, row['PR CODE'], row['LOCATION'], '', '', '', '', row['DESCRIPTION'], row['DESCRIPTION 2'], row['UOM'], row['QUANTITY'], '', 'Open', ts])
                                    for vn in sel_vendors:
                                        if v_map.get(vn):
                                            a_rows.append([v_map[vn], row['PR CODE'], u_id, "Active"])
                                
                                if batch_save_data("Master_Items", m_rows) and batch_save_data("Access_Goods", a_rows):
                                    st.success("RFQ Berhasil Terkirim!")
                                    st.session_state['selected_items_dict'] = {}
                                    st.rerun()
                else:
                    st.warning("Belum ada PR/item yang dipilih.")
                

    # --- TAB 2: COMPARISON ---
    with tabs[1]:
        st.header("Price Comparison Analysis")
        df_prices = get_data("Price_Goods")
    
        if df_prices.empty:
            st.info("Belum ada penawaran masuk dari vendor.")
        else:
            df_master = get_data("Master_Items")
        

            df_merged = pd.merge(
                df_prices, 
                df_master[['id_unique', 'item_name', 'specification', 'qty', 'uom']], 
                on='id_unique', 
                how='left'
            )
        

        # (biasanya di sheet Price_Goods kamu pakai 'pr_number')
            if 'pr_number' in df_merged.columns:
                pr_list = df_merged['pr_number'].unique()
                sel_pr = st.selectbox("Pilih Nomor PR:", pr_list)
            
                sub_comp = df_merged[df_merged['pr_number'] == sel_pr]
            
            # Pivot table untuk perbandingan harga antar vendor
            # Sesuaikan index dengan kolom yang ada: item_name, specification, qty, uom
                pivot_df = sub_comp.pivot_table(
                    index=['item_name', 'specification', 'qty', 'uom'],
                    columns='vendor_email',
                    values='unit_price',
                    aggfunc='min'
                ).reset_index()
            
                st.write(f"### Perbandingan Harga PR: {sel_pr}")
                # Pisahkan kolom teks (identitas) dan kolom angka (harga dari vendor)
                identitas_cols = ['item_name', 'specification', 'qty', 'uom']
                harga_cols = [c for c in pivot_df.columns if c not in identitas_cols]

                if harga_cols:
                    # Tampilkan dataframe dengan highlight hanya pada kolom harga
                    st.dataframe(
                        pivot_df.style.highlight_min(
                            axis=1, 
                            color='#d1fae5', 
                            subset=harga_cols
                        ), 
                        use_container_width=True
                    )
                else:
                    st.dataframe(pivot_df, use_container_width=True)
                    
            # Fitur Download
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    pivot_df.to_excel(writer, index=False)
                st.download_button("📥 Download Report Excel", output.getvalue(), f"Comparison_{sel_pr}.xlsx")
            else:
                st.error("Kolom 'pr_number' tidak ditemukan di database. Silakan cek nama kolom di Google Sheets 'Price_Goods'.")
                st.write("Kolom yang tersedia:", df_merged.columns.tolist())

# --- VENDOR PORTAL ---
def vendor_portal(email):
    st.header("📝 Form Penawaran Harga")
    
    # 1. Ambil Akses
    df_acc = get_data("Access_Goods")
    my_acc = df_acc[df_acc['vendor_email'] == email]
    
    if my_acc.empty:
        st.info("Tidak ada permintaan RFQ untuk Anda.")
        return

    # 2. Ambil Item & Filter
    df_master = get_data("Master_Items")
    df_my_items = df_master[df_master['id_unique'].isin(my_acc['id_unique'])]
    
    # Masking Kolom Rahasia
    display_cols = ['id_unique', 'pr_number', 'location', 'item_name', 'specification', 'uom', 'qty']
    
    for pr in df_my_items['pr_number'].unique():
        with st.expander(f"📋 PR: {pr}", expanded=True):
            sub_items = df_my_items[df_my_items['pr_number'] == pr][display_cols].copy()
            
            # Siapkan kolom input
            sub_items['Unit_Price'] = 0.0
            sub_items['Brand'] = "-"
            sub_items['Lead_Time_Days'] = 7
            
            edited = st.data_editor(
                sub_items, key=f"edit_{pr}", hide_index=True, use_container_width=True,
                disabled=display_cols # Kunci data ERP
            )
            
            if st.button(f"Kirim Penawaran PR {pr}", key=f"save_{pr}"):
                price_rows = []
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for _, r in edited.iterrows():
                    price_rows.append([
                        f"P-{uuid.uuid4().hex[:6]}", pr, email, r['id_unique'],
                        r['Unit_Price'], r['Brand'], r['Lead_Time_Days'], ts, "Open"
                    ])
                
                if batch_save_data("Price_Goods", price_rows):
                    st.success("Berhasil mengirim penawaran!")

if __name__ == "__main__":
    main()
