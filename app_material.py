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
            return pd.DataFrame(data)
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
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.button("Masuk", type="primary", use_container_width=True):
                df_users = get_data("Users")
                if not df_users.empty:
                    user = df_users[(df_users['email'] == email) & (df_users['password'].astype(str) == password)]
                    if not user.empty:
                        st.session_state['user_info'] = user.iloc[0].to_dict()
                        st.rerun()
                    else:
                        st.error("Email atau Password salah.")

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

# --- ADMIN PORTAL ---
def admin_portal():
    tabs = st.tabs(["📥 Import PR", "📊 Monitoring & Comparison", "🔍 History Search"])
    
    # --- TAB 1: IMPORT PR ---
    with tabs[0]:
        st.header("Upload Purchase Request dari ERP")
        uploaded_file = st.file_uploader("Upload File Excel ERP", type=['xlsx'])
        
        if uploaded_file:
            # 1. Baca data (header=2 untuk baris ke-3)
            df_raw = pd.read_excel(uploaded_file, header=2)
            
            # 2. Standarisasi Nama Kolom (Uppercase & Strip)
            df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
            
            # 3. Fungsi Cari Kolom Dinamis (Hanya perlu satu fungsi)
            def find_col_dynamic(keywords, df_cols):
                for col in df_cols:
                    if any(key in col for key in keywords):
                        return col
                return None

            # Identifikasi Kolom Utama
            c_status = find_col_dynamic(['STATUS'], df_raw.columns)
            c_qty = find_col_dynamic(['QUANTITY', 'QTY'], df_raw.columns)
            c_pr = find_col_dynamic(['PR CODE', 'NO. PR', 'PURCHASE REQUEST'], df_raw.columns)
            c_desc = find_col_dynamic(['DESCRIPTION', 'NAMA BARANG', 'ITEM'], df_raw.columns)
            c_desc2 = find_col_dynamic(['DESCRIPTION 2', 'SPEK'], df_raw.columns)
            c_uom = find_col_dynamic(['UOM', 'SATUAN'], df_raw.columns)
            c_loc = find_col_dynamic(['LOCATION', 'LOKASI'], df_raw.columns)
            c_prio = find_col_dynamic(['PRIORITY'], df_raw.columns)
            c_date = find_col_dynamic(['CREATE DATE', 'TANGGAL'], df_raw.columns)

            # 4. PROSES FILTER (Status Open & Qty > 0)
            df_filtered = df_raw.copy()

            if c_status:
                df_filtered = df_filtered[df_filtered[c_status].astype(str).str.contains('Open', case=False, na=False)]
            
            if c_qty:
                df_filtered[c_qty] = pd.to_numeric(df_filtered[c_qty], errors='coerce').fillna(0)
                df_filtered = df_filtered[df_filtered[c_qty] > 0]

            # 5. CEK APAKAH HASIL FILTER KOSONG
            if df_filtered.empty:
                st.warning("⚠️ Data kosong setelah filter (Cek Status 'Open' & Qty > 0). Menampilkan 10 data asli untuk cek.")
                df_display_base = df_raw.head(10)
            else:
                st.success(f"✅ Terdeteksi {len(df_filtered)} item valid.")
                df_display_base = df_filtered

            st.subheader("📝 Langkah 1: Pilih Item & Review Data")
            
            # Ambil kolom yang ditemukan saja untuk ditampilkan
            display_cols = [c for c in [c_pr, c_desc, c_desc2, c_qty, c_uom] if c is not None]
            
            if not display_cols:
                st.error("❌ Kolom tidak dikenali. Pastikan Header di baris ke-3.")
                with st.expander("Lihat Kolom yang Terdeteksi"):
                    st.write(df_raw.columns.tolist())
            else:
                # Buat DataFrame View
                df_view = df_display_base[display_cols].copy()
                df_view.insert(0, "PILIH", True) 

                edited_items = st.data_editor(
                    df_view,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "PILIH": st.column_config.CheckboxColumn(default=True),
                    },
                    disabled=display_cols,
                    key="editor_pr_goods"
                )
                
                final_items = edited_items[edited_items["PILIH"] == True]
                st.info(f"💡 {len(final_items)} item terpilih.")
            
                st.divider()
                st.subheader("🎯 Langkah 2: Assign ke Vendor")
                
                df_users = get_data("Users")
                list_vendors = df_users[df_users['role'] == 'vendor']['vendor_name'].tolist()
                
                c1, c2 = st.columns([1, 4])
                if c1.button("✅ Select All"): st.session_state['selected_vendors'] = list_vendors
                if c2.button("🗑️ Clear"): st.session_state['selected_vendors'] = []
                
                sel_vendors = st.multiselect("Pilih Vendor Penerima:", list_vendors, key='selected_vendors')
                
                if st.button("🚀 Publish Undangan RFQ", type="primary"):
                    if final_items.empty or not sel_vendors:
                        st.warning("Mohon pilih minimal 1 item dan 1 vendor.")
                    else:
                        with st.spinner("Publishing..."):
                            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            master_rows = []
                            access_rows = []
                            
                            # Ambil mapping email vendor
                            vendor_emails = {v['vendor_name']: v['email'] for _, v in df_users.iterrows() if v['role'] == 'vendor'}
                            
                            for _, row in final_items.iterrows():
                                u_id = str(uuid.uuid4())[:8]
                                pr_val = row.get(c_pr, "")
                                item_val = row.get(c_desc, "")
                                
                                # Data untuk Master_Items
                                master_rows.append([
                                    u_id, pr_val, 
                                    df_filtered.loc[_, c_loc] if c_loc in df_filtered.columns else "",
                                    df_filtered.loc[_, c_prio] if c_prio in df_filtered.columns else "",
                                    "", "", "", # Budget, User, PIC (Kosongkan dulu)
                                    item_val, 
                                    row.get(c_desc2, ""), 
                                    row.get(c_uom, ""), 
                                    row.get(c_qty, 0), 
                                    str(df_filtered.loc[_, c_date]) if c_date in df_filtered.columns else "",
                                    "Open", ts
                                ])
                                
                                # Data untuk Access_Goods
                                for v_name in sel_vendors:
                                    v_email = vendor_emails.get(v_name)
                                    if v_email:
                                        access_rows.append([v_email, pr_val, u_id, "Active"])
                            
                            # Simpan
                            if batch_save_data("Master_Items", master_rows) and batch_save_data("Access_Goods", access_rows):
                                st.success(f"Berhasil! RFQ telah dikirim ke {len(sel_vendors)} vendor.")
                                st.balloons()

    # --- TAB 2: COMPARISON ---
    with tabs[1]:
        st.header("Price Comparison Analysis")
        df_prices = get_data("Price_Goods")
        if df_prices.empty:
            st.info("Belum ada penawaran masuk.")
        else:
            df_master = get_data("Master_Items")
            # Gabungkan harga dengan detail nama barang
            df_merged = pd.merge(df_prices, df_master[['id_unique', 'item_name', 'specification', 'qty', 'uom']], on='id_unique', how='left')
            
            pr_list = df_merged['pr_number'].unique()
            sel_pr = st.selectbox("Pilih Nomor PR:", pr_list)
            
            sub_comp = df_merged[df_merged['pr_number'] == sel_pr]
            
            pivot_df = sub_comp.pivot_table(
                index=['item_name', 'specification', 'qty', 'uom'],
                columns='vendor_email',
                values='unit_price',
                aggfunc='min'
            ).reset_index()
            
            st.dataframe(pivot_df.style.highlight_min(axis=1, color='#d1fae5'), use_container_width=True)
            
            # Fitur Download
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                pivot_df.to_excel(writer, index=False)
            st.download_button("📥 Download Report Excel", output.getvalue(), f"Comparison_{sel_pr}.xlsx")

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
