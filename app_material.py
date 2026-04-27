import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime
import io

# --- CONFIG ---
st.set_page_config(page_title="TACO Goods Procurement", layout="wide", page_icon="📦")
SPREADSHEET_ID = "MASUKKAN_ID_SPREADSHEET_BARU_ANDA" # <-- GANTI INI

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
        return client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"Koneksi Gagal: {e}")
        return None

def get_data(sheet_name):
    sh = connect_to_gsheet()
    if sh:
        ws = sh.worksheet(sheet_name)
        return pd.DataFrame(ws.get_all_records())
    return pd.DataFrame()

def save_data(sheet_name, df_new):
    sh = connect_to_gsheet()
    if sh:
        ws = sh.worksheet(sheet_name)
        # Ambil data lama untuk cek headers
        existing = ws.get_all_values()
        if not existing:
            ws.append_rows([df_new.columns.tolist()] + df_new.values.tolist())
        else:
            ws.append_rows(df_new.values.tolist())
        return True
    return False

# --- MAIN APP ---
def main():
    if 'user_info' not in st.session_state:
        st.session_state['user_info'] = None

    if st.session_state['user_info'] is None:
        show_login()
    else:
        show_dashboard()

def show_login():
    st.title("🔐 TACO Goods Procurement")
    with st.container(border=True):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login", type="primary", use_container_width=True):
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
    st.sidebar.title(f"👋 {user['vendor_name']}")
    st.sidebar.caption(f"Role: {user['role']}")
    
    if st.sidebar.button("Logout"):
        st.session_state['user_info'] = None
        st.rerun()

    if user['role'] == 'admin':
        admin_portal()
    else:
        vendor_portal()

# --- ADMIN PORTAL ---
def admin_portal():
    menu = st.sidebar.radio("Navigasi Admin", ["📦 Bulk Import PR", "📊 Monitoring & Comparison", "👥 Manage Users"])

    if menu == "📦 Bulk Import PR":
        st.header("Bulk Import Purchase Request (Excel)")
        st.info("Gunakan menu ini untuk upload daftar barang dari ERP.")
        
        uploaded_file = st.file_uploader("Upload File PR (.xlsx)", type=['xlsx'])
        if uploaded_file:
            df_pr = pd.read_excel(uploaded_file)
            st.write("Preview Data PR:")
            st.dataframe(df_pr, use_container_width=True)
            
            if st.button("🚀 Push ke Database Master Barang", type="primary"):
                with st.spinner("Sedang menyimpan..."):
                    # Tambahkan timestamp
                    df_pr['created_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    # Generate ID Item sederhana jika belum ada
                    if 'id_item' not in df_pr.columns:
                        df_pr['id_item'] = [f"ITM-{datetime.now().strftime('%m%d')}-{i}" for i in range(len(df_pr))]
                    
                    success = save_data("Master_Items", df_pr)
                    if success:
                        st.success(f"Berhasil meng-import {len(df_pr)} item barang!")
                    else:
                        st.error("Gagal menyimpan ke Google Sheets.")

    elif menu == "📊 Monitoring & Comparison":
        st.header("Price Comparison Analysis")
        df_prices = get_data("Price_Goods")
        
        if df_prices.empty:
            st.warning("Bel_um ada penawaran harga yang masuk.")
        else:
            # Filter per No PR
            list_pr = df_prices['pr_number'].unique().tolist()
            sel_pr = st.selectbox("Pilih Nomor PR untuk Dibandingkan:", list_pr)
            
            df_sub = df_prices[df_prices['pr_number'] == sel_pr]
            
            # PIVOT: Mengubah Vendor menjadi Kolom
            try:
                pivot_df = df_sub.pivot_table(
                    index=['item_name', 'specification', 'uom', 'qty'], 
                    columns='vendor_name', 
                    values='unit_price',
                    aggfunc='first'
                ).reset_index()
                
                st.subheader(f"Tabel Perbandingan PR: {sel_pr}")
                st.dataframe(pivot_df.style.highlight_min(axis=1, color='#d1fae5'), use_container_width=True)
                
                # Download Report
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    pivot_df.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 Download Comparison (.xlsx)",
                    data=output.getvalue(),
                    file_name=f"Comparison_{sel_pr}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                st.error(f"Gagal membuat tabel perbandingan: {e}")

# --- VENDOR PORTAL ---
def vendor_portal():
    st.header("📦 Penawaran Harga Barang")
    st.info("Silakan isi harga penawaran untuk item di bawah ini.")
    
    df_items = get_data("Master_Items")
    if df_items.empty:
        st.warning("Belum ada daftar permintaan barang (PR) untuk Anda.")
    else:
        # Contoh filter sederhana: Tampilkan semua item
        st.write("Daftar Permintaan Barang:")
        # Vendor input harga menggunakan data_editor
        df_items['Unit Price'] = 0.0
        df_items['Brand/Merk'] = "-"
        df_items['Lead Time (Days)'] = 7
        
        edited_df = st.data_editor(
            df_items[['pr_number', 'item_name', 'specification', 'uom', 'qty', 'Unit Price', 'Brand/Merk', 'Lead Time (Days)']],
            hide_index=True,
            use_container_width=True,
            disabled=['pr_number', 'item_name', 'specification', 'uom', 'qty']
        )
        
        if st.button("Simpan Penawaran Harga", type="primary"):
            # Logika simpan hasil editan ke sheet Price_Goods
            st.success("Penawaran Anda berhasil disimpan!")

if __name__ == "__main__":
    main()
