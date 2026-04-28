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
    tabs = st.tabs(["📥 Import PR", "📊 Monitoring & Comparison", "🔍 History Search"])
    
    with tabs[0]:
        st.header("Upload Purchase Request dari ERP")
        uploaded_file = st.file_uploader("Upload File Excel ERP", type=['xlsx'])
        
        if uploaded_file:
            df_raw = pd.read_excel(uploaded_file, header=2)
            df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
            
            # --- 1. INISIALISASI MEMORI ---
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
                st.subheader("📝 Langkah 1: Pilih Item & Review Data")
                search_query = st.text_input("🔍 Cari PR, Barang, Spek, atau Lokasi...", placeholder="Ketik di sini...")
                
                # 2. Filter Search
                if search_query:
                    q = search_query.lower()
                    mask = (
                        df_display['PR CODE'].astype(str).str.lower().str.contains(q, regex=False, na=False) |
                        df_display['DESCRIPTION'].astype(str).str.lower().str.contains(q, regex=False, na=False) |
                        df_display['DESCRIPTION 2'].astype(str).str.lower().str.contains(q, regex=False, na=False) |
                        df_display['LOCATION'].astype(str).str.lower().str.contains(q, regex=False, na=False)
                    )
                    df_to_show = df_display[mask]
                else:
                    df_to_show = df_display

                all_edited_results = []
                grouped_pr = df_to_show['PR CODE'].unique()

                for pr_no in grouped_pr:
                    df_pr_group = df_to_show[df_to_show['PR CODE'] == pr_no].copy()
                    loc_val = df_pr_group['LOCATION'].iloc[0] if 'LOCATION' in df_pr_group.columns else "Unknown"
                    header_text = f"📄 {pr_no} | 📍 {loc_val} | {df_pr_group['DESCRIPTION'].iloc[0][:40]}..."
                    
                    with st.expander(header_text, expanded=False):
                        select_all_pr = st.checkbox(f"Pilih Semua Item di PR {pr_no}", key=f"all_{pr_no}")
                        
                        display_table_cols = ['DESCRIPTION', 'DESCRIPTION 2', 'QUANTITY', 'UOM']
                        df_view = df_pr_group[display_table_cols].copy()
                        
                        # --- PERBAIKAN DI SINI ---
                        df_view['unique_key'] = str(pr_no) + "_" + df_view['DESCRIPTION'].astype(str)
                        
                        current_selections = []
                        for key in df_view['unique_key']:
                            if select_all_pr:
                                st.session_state['selected_items_dict'][key] = True
                            status = st.session_state['selected_items_dict'].get(key, False)
                            current_selections.append(status)
                        
                        df_view.insert(0, "PILIH", current_selections)

                        edited_pr = st.data_editor(
                            df_view.drop(columns=['unique_key']),
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "PILIH": st.column_config.CheckboxColumn("PILIH", default=False),
                                "QUANTITY": st.column_config.NumberColumn("QTY", format="%d"),
                            },
                            disabled=display_table_cols,
                            key=f"editor_{pr_no}"
                        )
                        
                        for i, row in edited_pr.iterrows():
                            # --- DAN DI SINI ---
                            item_key = str(pr_no) + "_" + str(row['DESCRIPTION'])
                            st.session_state['selected_items_dict'][item_key] = row['PILIH']
                        
                        edited_pr['PR CODE'] = pr_no
                        edited_pr['LOCATION'] = loc_val
                        all_edited_results.append(edited_pr)

                st.divider()
                st.subheader("🎯 Langkah 2: Review & Assign Vendor")
                
                # Review items
                selected_keys = [k for k, v in st.session_state['selected_items_dict'].items() if v == True]
                df_display['unique_key'] = df_display['PR CODE'].astype(str) + "_" + df_display['DESCRIPTION'].astype(str)
                final_items = df_display[df_display['unique_key'].isin(selected_keys)].copy()

                if not final_items.empty:
                    with st.expander("📋 Lihat Daftar Item Terpilih", expanded=True):
                        summary_cols = ['PR CODE', 'LOCATION', 'DESCRIPTION', 'DESCRIPTION 2', 'QUANTITY', 'UOM']
                        st.dataframe(final_items[summary_cols], hide_index=True, use_container_width=True)
                        st.info(f"Total: **{len(final_items)} item** terpilih.")
                else:
                    st.warning("Belum ada item yang dipilih.")
                
                # Vendor Selection
                df_users = get_data("Users")
                list_vendors = df_users[df_users['role'] == 'vendor']['vendor_name'].tolist()
                
                c1, c2 = st.columns([1, 4])
                if c1.button("✅ Select All Vendors"): st.session_state['selected_vendors'] = list_vendors
                if c2.button("🗑️ Clear Selection"): st.session_state['selected_vendors'] = []
                
                sel_vendors = st.multiselect("Pilih Vendor:", list_vendors, key='selected_vendors')
                
                if st.button("🚀 Publish Undangan RFQ", type="primary", use_container_width=True):
                    if final_items.empty or not sel_vendors:
                        st.error("Gagal: Pilih minimal 1 item dan 1 vendor!")
                    else:
                        with st.spinner("Sedang memproses RFQ..."):
                            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            master_rows = []
                            access_rows = []
                            v_map = {r['vendor_name']: r['email'] for _, r in df_users.iterrows() if r['role'] == 'vendor'}
                            
                            for _, row in final_items.iterrows():
                                u_id = str(uuid.uuid4())[:8]
                                master_rows.append([
                                    u_id, row.get('PR CODE',''), row.get('LOCATION',''), '', 
                                    '', '', '', row.get('DESCRIPTION',''), row.get('DESCRIPTION 2',''),
                                    row.get('UOM',''), row.get('QUANTITY',0), '', 'Open', ts
                                ])
                                for v_name in sel_vendors:
                                    v_email = v_map.get(v_name)
                                    if v_email:
                                        access_rows.append([v_email, row.get('PR CODE',''), u_id, "Active"])
                            
                            if batch_save_data("Master_Items", master_rows) and batch_save_data("Access_Goods", access_rows):
                                # Notifikasi sukses yang bersih tanpa animasi balon
                                st.success(f"✅ RFQ Berhasil Terkirim: {len(final_items)} item telah dipublish ke {len(sel_vendors)} vendor.")
                                
                                # Reset keranjang memori agar siap untuk batch berikutnya
                                st.session_state['selected_items_dict'] = {} 
                                
                                # Opsional: Tambahkan tombol untuk refresh halaman jika perlu
                                if st.button("Refresh Halaman"):
                                    st.rerun()

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
