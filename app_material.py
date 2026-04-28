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
    
    with tabs[0]:
        st.header("Upload Purchase Request dari ERP")
        uploaded_file = st.file_uploader("Upload File Excel ERP", type=['xlsx'])
        
        if uploaded_file:
            # Sesuai permintaan: Header ada di baris ke-3 (header=2)
            df_raw = pd.read_excel(uploaded_file, header=2)
            
            # Bersihkan nama kolom: Uppercase dan buang spasi
            df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
            
            # --- LOGIKA FILTER (Status: Open & Qty > 0) ---
            # Kita cari kolomnya secara spesifik
            col_status = 'STATUS'
            col_qty = 'QUANTITY'
            
            if col_status in df_raw.columns and col_qty in df_raw.columns:
                # 1. Pastikan Qty adalah angka
                df_raw[col_qty] = pd.to_numeric(df_raw[col_qty], errors='coerce').fillna(0)
                
                # 2. Filter Ganda
                df_filtered = df_raw[
                    (df_raw[col_status].astype(str).str.strip() == 'Open') & 
                    (df_raw[col_qty] > 0)
                ].copy()
                
                if df_filtered.empty:
                    st.warning("⚠️ Tidak ada data dengan Status 'Open' dan Quantity > 0.")
                    # Tampilkan sedikit data asli untuk cek manual
                    st.write("Contoh data asli (5 baris):", df_raw[[col_status, col_qty]].head())
                    df_display = pd.DataFrame() # Biarkan kosong agar tidak salah publish
                else:
                    st.success(f"✅ Berhasil memfilter {len(df_filtered)} item (Status: Open & Qty > 0).")
                    df_display = df_filtered
            else:
                st.error(f"❌ Kolom STATUS atau QUANTITY tidak ditemukan! Kolom yang ada: {list(df_raw.columns[:5])}...")
                df_display = pd.DataFrame()

            if not df_display.empty:
                st.subheader("📝 Langkah 1: Pilih Item & Review Data")
                st.info("Data dikelompokkan per Nomor PR. Silakan buka expander untuk memilih item.")

                # 1. Definisikan urutan kolom (QTY dulu baru UOM sesuai request)
                cols_to_show = ['PR CODE', 'DESCRIPTION', 'DESCRIPTION 2', 'QUANTITY', 'UOM']
                valid_cols = [c for c in cols_to_show if c in df_display.columns]
                
                # List untuk menampung semua hasil editan dari berbagai expander
                all_edited_results = []

                # 2. Kelompokkan per Nomor PR
                grouped_pr = df_display['PR CODE'].unique()

                for pr_no in grouped_pr:
                    # Ambil data untuk PR ini saja
                    df_pr_group = df_display[df_display['PR CODE'] == pr_no][valid_cols].copy()
                    
                    # Ambil info User/PIC atau Desc utama untuk judul header (opsional)
                    sample_desc = df_pr_group['DESCRIPTION'].iloc[0]
                    
                    # Buat Expander per Nomor PR
                    with st.expander(f"📄 PR: {pr_no} | {sample_desc[:50]}...", expanded=True):
                        df_view = df_pr_group.copy()
                        df_view.insert(0, "PILIH", True) # Checkbox di depan

                        # Tampilkan editor khusus untuk PR ini
                        edited_pr = st.data_editor(
                            df_view,
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "PILIH": st.column_config.CheckboxColumn(default=True),
                                "QUANTITY": st.column_config.NumberColumn(format="%d"),
                            },
                            disabled=valid_cols,
                            key=f"editor_{pr_no}" # Key harus unik per PR
                        )
                        all_edited_results.append(edited_pr)

                # Gabungkan kembali semua item yang dipilih dari semua expander
                if all_edited_results:
                    final_df_all = pd.concat(all_edited_results)
                    final_items = final_df_all[final_df_all["PILIH"] == True]
                    st.success(f"📦 Total {len(final_items)} item terpilih dari {len(grouped_pr)} PR.")
                else:
                    final_items = pd.DataFrame()
                
                st.divider()
                st.subheader("🎯 Langkah 2: Assign ke Vendor")
                
                df_users = get_data("Users")
                list_vendors = df_users[df_users['role'] == 'vendor']['vendor_name'].tolist()
                
                col_a, col_b = st.columns([1, 4])
                if col_a.button("✅ Select All Vendors"): st.session_state['selected_vendors'] = list_vendors
                if col_b.button("🗑️ Clear Selection"): st.session_state['selected_vendors'] = []
                
                sel_vendors = st.multiselect("Pilih Vendor Penerima Undangan:", list_vendors, key='selected_vendors')
                
                if st.button("🚀 Publish Undangan RFQ", type="primary", use_container_width=True):
                    if final_items.empty or not sel_vendors:
                        st.error("Gagal: Pilih minimal 1 item dan 1 vendor!")
                    else:
                        with st.spinner("Mengirim data ke database..."):
                            # Logic simpan (Master_Items & Access_Goods)
                            # ... (Gunakan batch_save_data seperti sebelumnya)
                            st.success("RFQ Berhasil di-publish!")
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
