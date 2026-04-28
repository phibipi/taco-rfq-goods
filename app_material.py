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

def main():
    if 'user_info' not in st.session_state:
        st.session_state['user_info'] = None
    if st.session_state['user_info'] is None:
        show_login()
    else:
        show_dashboard()

def show_login():
    st.title("🏢 TACO E-Procurement (Goods)")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.container(border=True):
            email_input = st.text_input("Email").strip().lower()
            password_input = st.text_input("Password", type="password").strip()
            if st.button("Masuk", type="primary", use_container_width=True):
                df_users = get_data("Users")
                if not df_users.empty:
                    user = df_users[
                        (df_users['email'].astype(str).str.lower() == email_input) &
                        (df_users['password'].astype(str) == password_input)
                    ]
                    if not user.empty:
                        st.session_state['user_info'] = user.iloc[0].to_dict()
                        st.rerun()
                    else:
                        st.error("Email atau Password salah.")
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
        uploaded_file = st.file_uploader("Upload File Excel", type=['xlsx'])

        if uploaded_file:
            df_raw = pd.read_excel(uploaded_file, header=2)
            df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]

            if 'selected_items_dict' not in st.session_state:
                st.session_state['selected_items_dict'] = {}

            df_display = df_raw.copy()
            if 'STATUS' in df_raw.columns and 'QUANTITY' in df_raw.columns:
                df_raw['QUANTITY'] = pd.to_numeric(df_raw['QUANTITY'], errors='coerce').fillna(0)
                df_display = df_raw[
                    (df_raw['STATUS'].astype(str).str.strip() == 'Open') &
                    (df_raw['QUANTITY'] > 0)
                ].copy()

            df_display['ID_SISTEM'] = (
                df_display['PR CODE'].astype(str) + "_" + df_display['DESCRIPTION'].astype(str)
            )

            if not df_display.empty:
                st.subheader("📝 Langkah 1: Pilih Item")
                search_query = st.text_input(
                    "🔍 Cari No. PR atau Nama Item...", placeholder="Ketik di sini..."
                )

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
                        df_group = df_to_show[df_to_show['PR CODE'] == pr_no].copy()
                        df_group = df_group.reset_index(drop=True)  # index is now 0,1,2...
                        loc = df_group['LOCATION'].iloc[0] if 'LOCATION' in df_group.columns else "-"

                        with st.expander(f"📄 PR: {pr_no} | 📍 {loc}"):
                            c1, c2, _ = st.columns([1, 1, 3])

                            if c1.button("✅ Pilih Semua", key=f"all_btn_{pr_no}"):
                                for idx, k in enumerate(df_group['ID_SISTEM']):
                                    st.session_state['selected_items_dict'][k] = True
                                    st.session_state[f"chk_{pr_no}_{idx}"] = True
                                st.rerun()

                            if c2.button("🗑️ Hapus Semua", key=f"none_btn_{pr_no}"):
                                for idx, k in enumerate(df_group['ID_SISTEM']):
                                    st.session_state['selected_items_dict'][k] = False
                                    st.session_state[f"chk_{pr_no}_{idx}"] = False
                                st.rerun()

                            # Column headers
                            h1, h2, h3, h4, h5 = st.columns([0.5, 3, 3, 1, 1])
                            h1.markdown("**✓**")
                            h2.markdown("**Description**")
                            h3.markdown("**Description 2**")
                            h4.markdown("**Qty**")
                            h5.markdown("**UOM**")

                            # One checkbox per item row — key uses pr_no + row index
                            for idx, item_row in df_group.iterrows():
                                id_sistem = item_row['ID_SISTEM']
                                col1, col2, col3, col4, col5 = st.columns([0.5, 3, 3, 1, 1])

                                # --- PERBAIKAN DI SINI ---
                                checked = col1.checkbox(
                                    label="select",
                                    value=st.session_state['selected_items_dict'].get(id_sistem, False),
                                    key=f"chk_{pr_no}_{idx}",
                                    label_visibility="collapsed",
                                    on_change=st.rerun  # <--- TAMBAHKAN INI agar Langkah 2 langsung muncul
                                )
                                
                                # Update state setiap kali ada interaksi
                                st.session_state['selected_items_dict'][id_sistem] = checked
                                
                                col2.write(item_row.get('DESCRIPTION', ''))
                                col3.write(item_row.get('DESCRIPTION 2', ''))
                                col4.write(item_row.get('QUANTITY', ''))
                                col5.write(item_row.get('UOM', ''))

                                # Write checkbox state directly into dict — reliable every rerun
                                st.session_state['selected_items_dict'][id_sistem] = checked

                # --- LANGKAH 2 ---
                st.divider()
                col_title, col_btn = st.columns([4, 1])
                col_title.subheader("🎯 Langkah 2: Review & Assign Vendor")
                if col_btn.button("🔄 Refresh", use_container_width=True):
                    st.rerun()

                selected_keys = [
                    k for k, v in st.session_state['selected_items_dict'].items() if v
                ]
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
                            keys_to_del = [k for k in st.session_state if k.startswith("chk_")]
                            for k in keys_to_del:
                                del st.session_state[k]
                            st.rerun()

                    df_u = get_data("Users")
                    vendors = (
                        df_u[df_u['role'] == 'vendor']['vendor_name'].tolist()
                        if not df_u.empty else []
                    )
                    sel_v = st.multiselect("Pilih Vendor Penerima RFQ:", vendors)

                    if st.button("🚀 Publish Undangan RFQ", type="primary", use_container_width=True):
                        if not sel_v:
                            st.error("Silakan pilih minimal satu vendor.")
                        else:
                            st.success("✅ Berhasil! RFQ telah dipublish.")
                            st.session_state['selected_items_dict'] = {}
                            keys_to_del = [k for k in st.session_state if k.startswith("chk_")]
                            for k in keys_to_del:
                                del st.session_state[k]
                            st.rerun()
                else:
                    st.warning("Belum ada item yang dipilih dari Langkah 1.")

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
            if 'pr_number' in df_merged.columns:
                pr_list = df_merged['pr_number'].unique()
                sel_pr = st.selectbox("Pilih Nomor PR:", pr_list)
                sub_comp = df_merged[df_merged['pr_number'] == sel_pr]
                pivot_df = sub_comp.pivot_table(
                    index=['item_name', 'specification', 'qty', 'uom'],
                    columns='vendor_email',
                    values='unit_price',
                    aggfunc='min'
                ).reset_index()
                st.write(f"### Perbandingan Harga PR: {sel_pr}")
                identitas_cols = ['item_name', 'specification', 'qty', 'uom']
                harga_cols = [c for c in pivot_df.columns if c not in identitas_cols]
                if harga_cols:
                    st.dataframe(
                        pivot_df.style.highlight_min(axis=1, color='#d1fae5', subset=harga_cols),
                        use_container_width=True
                    )
                else:
                    st.dataframe(pivot_df, use_container_width=True)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    pivot_df.to_excel(writer, index=False)
                st.download_button(
                    "📥 Download Report Excel", output.getvalue(), f"Comparison_{sel_pr}.xlsx"
                )
            else:
                st.error("Kolom 'pr_number' tidak ditemukan.")
                st.write("Kolom tersedia:", df_merged.columns.tolist())

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
            edited = st.data_editor(
                sub_items, key=f"edit_{pr}", hide_index=True, use_container_width=True,
                disabled=display_cols
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
