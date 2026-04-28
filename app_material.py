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
            df_raw = pd.read_excel(uploaded_file, header=2)
            
            # 1. STANDARISASI: Paksa semua nama kolom jadi huruf besar & tanpa spasi tambahan
            df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
            
            # 2. FILTER STATUS OPEN
            if 'STATUS' in df_raw.columns:
                df_filtered = df_raw[df_raw['STATUS'].astype(str).str.contains('Open', case=False, na=False)].copy()
            else:
                st.warning("⚠️ Kolom STATUS tidak ditemukan, menampilkan semua data.")
                df_filtered = df_raw.copy()

            st.subheader("📝 Langkah 1: Pilih Item & Review Data")
            
            # 3. MAPPING FLEXIBLE: Cari kolom yang mirip-mirip namanya
            # Ini biar kalau di Excel namanya 'PR CODE' atau 'NO. PR' tetap tertangkap
            def find_col(keywords, df):
                for col in df.columns:
                    if any(key in col for key in keywords):
                        return col
                return None

            col_pr = find_col(['PR CODE', 'NO. PR', 'PURCHASE REQUEST'], df_filtered)
            col_desc = find_col(['DESCRIPTION', 'NAMA BARANG', 'ITEM'], df_filtered)
            col_desc2 = find_col(['DESCRIPTION 2'], df_filtered)
            col_qty = find_col(['QUANTITY', 'QTY'], df_filtered)
            col_uom = find_col(['UOM', 'SATUAN'], df_filtered)

            # Buat DataFrame baru khusus untuk tampilan (View)
            # Kita hanya ambil kolom yang ketemu saja
            display_cols = [c for c in [col_pr, col_desc, col_desc2, col_qty, col_uom] if c is not None]
            
            if not display_cols:
                st.error("❌ Sistem tidak mengenali kolom di Excel Anda. Pastikan Header di baris ke-3.")
                st.write("Kolom yang terbaca:", df_raw.columns.tolist())
            else:
                df_view = df_filtered[display_cols].copy()
                df_view.insert(0, "PILIH", True) # Masukkan checkbox di awal

                # TAMPILKAN EDITOR
                edited_items = st.data_editor(
                    df_view,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "PILIH": st.column_config.CheckboxColumn(help="Centang untuk kirim ke vendor", default=True),
                        # Kolom lainnya diset disabled agar Admin tidak edit data dari ERP
                    },
                    disabled=[c for c in display_cols] 
                )
                
                # Simpan hasil pilihan ke session state untuk proses kirim vendor
                final_items = edited_items[edited_items["PILIH"] == True]
                st.info(f"💡 {len(final_items)} item terpilih untuk di-RFQ.")
            
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
                    st.warning("Mohon lengkapi pilihan Item dan Vendor.")
                else:
                    with st.spinner("Sedang memproses ribuan data..."):
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # A. Simpan ke Master_Items
                        master_rows = []
                        id_map = {} # Untuk tracking id_unique
                        for _, row in final_items.iterrows():
                            u_id = str(uuid.uuid4())[:8] # ID Unik per Item
                            id_map[row['Description']] = u_id
                            # Pastikan urutan kolom sesuai Sheet Master_Items
                            master_rows.append([
                                u_id, row.get('PR Code',''), row.get('Location',''), row.get('Priority Status',''),
                                '', '', '', row.get('Description',''), row.get('Description 2',''),
                                row.get('UoM',''), row.get('Quantity', 0), str(row.get('Create Date','')), 'Open', ts
                            ])
                        
                        # B. Simpan ke Access_Goods (Mapping Vendor vs Item)
                        access_rows = []
                        for v_name in sel_vendors:
                            v_email = df_users[df_users['vendor_name'] == v_name]['email'].iloc[0]
                            for _, item in final_items.iterrows():
                                access_rows.append([v_email, item['PR Code'], id_map[item['Description']], "Active"])
                        
                        # Eksekusi Simpan
                        batch_save_data("Master_Items", master_rows)
                        batch_save_data("Access_Goods", access_rows)
                        
                        st.success(f"Berhasil! {len(final_items)} item dikirim ke {len(sel_vendors)} vendor.")
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
