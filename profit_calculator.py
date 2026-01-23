import streamlit as st
import pandas as pd
import io

# --- Page Configuration ---
st.set_page_config(page_title="Miner Profitability Modeling", layout="wide")

st.title("⚡ Miner Profitability & Comparison Tool")
st.markdown("Global Baseline analysis with specific peer-to-peer comparison.")

# --- Session State ---
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame([
        {"Model": "S19 XP", "Profile": "Normal", "Hashrate (TH/s)": 140.0, "Power (W)": 3010.0},
        {"Model": "S21", "Profile": "Normal", "Hashrate (TH/s)": 200.0, "Power (W)": 3500.0},
        {"Model": "S19j Pro", "Profile": "Oc", "Hashrate (TH/s)": 104.0, "Power (W)": 3068.0},
    ])

# --- Sidebar: Settings ---
st.sidebar.header("1. Global Settings")
power_price = st.sidebar.number_input("Power Price ($/kWh)", value=0.05, format="%.4f")
hashprice = st.sidebar.number_input("Hashprice ($/PH/s/Day)", value=60.0)
fleet_size = st.sidebar.number_input("Fleet Size", value=100, step=1)

st.sidebar.markdown("---")
st.sidebar.header("2. Fee Structure")
st.sidebar.caption("Define distinct fees for different scenarios.")
# 3 Specific Fees as requested
fee_global_base = st.sidebar.number_input("Global Baseline Fee (%)", value=1.0, format="%.2f")
fee_dual_base   = st.sidebar.number_input("Dual Compare Baseline Fee (%)", value=1.5, format="%.2f", help="Fee for Machine A in comparison")
fee_target      = st.sidebar.number_input("Target Fee (%)", value=2.0, format="%.2f", help="Fee for Machine B (and general fleet)")

# --- Main Interface ---
st.subheader("3. Machine Configurations")
edited_df = st.data_editor(
    st.session_state.data,
    num_rows="dynamic",
    use_container_width=True,
    key="editor",
    column_config={
        "Hashrate (TH/s)": st.column_config.NumberColumn(format="%.2f"),
        "Power (W)": st.column_config.NumberColumn(format="%.0f"),
        "Model": st.column_config.TextColumn(required=True),
    }
)

if not edited_df.empty:
    # --- 1. DATA PREP ---
    proc_df = edited_df.copy()
    proc_df["Hashrate (TH/s)"] = pd.to_numeric(proc_df["Hashrate (TH/s)"])
    proc_df["Power (W)"] = pd.to_numeric(proc_df["Power (W)"])
    proc_df["display_name"] = proc_df["Model"] + " (" + proc_df["Profile"] + ")"

    # Sidebar: Global Baseline Selector
    st.sidebar.markdown("---")
    st.sidebar.header("3. Baseline Selection")
    model_options = proc_df["display_name"].tolist()
    global_baseline_name = st.sidebar.selectbox("Global Baseline", options=model_options)

    # --- 2. GLOBAL CALCULATIONS ---
    # We apply fees based on "Global Logic" here (Global Base vs Target)
    hashprice_per_th = hashprice / 1000
    
    # Revenue
    proc_df["Rev/Miner ($)"] = proc_df["Hashrate (TH/s)"] * hashprice_per_th
    
    # Power Cost
    proc_df["Daily Power ($)"] = (proc_df["Power (W)"] / 1000) * 24 * power_price
    
    # Fee Calculation (Global Logic)
    def get_global_fee_pct(row):
        return fee_global_base if row["display_name"] == global_baseline_name else fee_target

    proc_df["Global Fee %"] = proc_df.apply(get_global_fee_pct, axis=1)
    proc_df["Fee ($)"] = proc_df["Rev/Miner ($)"] * (proc_df["Global Fee %"] / 100)
    
    # Profit
    proc_df["Cost/Miner ($)"] = proc_df["Daily Power ($)"] + proc_df["Fee ($)"]
    proc_df["Profit/Miner ($)"] = proc_df["Rev/Miner ($)"] - proc_df["Cost/Miner ($)"]
    proc_df["Fleet Profit ($)"] = proc_df["Profit/Miner ($)"] * fleet_size
    
    # Efficiency
    proc_df["Efficiency (J/TH)"] = proc_df.apply(lambda x: x["Power (W)"]/x["Hashrate (TH/s)"] if x["Hashrate (TH/s)"] > 0 else 0, axis=1)

    # --- 3. GLOBAL DISPLAY ---
    st.divider()
    st.subheader("4. Global Results")
    st.caption(f"Global Baseline: **{global_baseline_name}** ({fee_global_base}%) vs Others ({fee_target}%)")

    # Get Global Baseline Row
    global_base_row = proc_df[proc_df["display_name"] == global_baseline_name].iloc[0]

    # Helper for String Formatting
    def fmt_stat(val, base, is_money=False):
        diff = val - base
        f_val = f"${val:,.2f}" if is_money else f"{val:,.1f}"
        if abs(diff) < 0.001: return f_val
        sign = "+" if diff > 0 else ""
        f_diff = f"{sign}${diff:,.2f}" if is_money else f"{sign}{diff:,.1f}"
        return f"{f_val} ({f_diff})"

    # Display DF
    display_df = pd.DataFrame()
    display_df["Model"] = proc_df["Model"]
    display_df["Profile"] = proc_df["Profile"]
    display_df["Hashrate"] = proc_df["Hashrate (TH/s)"].apply(lambda x: fmt_stat(x, global_base_row["Hashrate (TH/s)"]))
    display_df["Power"] = proc_df["Power (W)"].apply(lambda x: fmt_stat(x, global_base_row["Power (W)"]))
    display_df["Efficiency"] = proc_df["Efficiency (J/TH)"].apply(lambda x: fmt_stat(x, global_base_row["Efficiency (J/TH)"]))
    display_df["Rev/Miner"] = proc_df["Rev/Miner ($)"].apply(lambda x: fmt_stat(x, global_base_row["Rev/Miner ($)"], True))
    display_df["Profit/Miner"] = proc_df["Profit/Miner ($)"].apply(lambda x: fmt_stat(x, global_base_row["Profit/Miner ($)"], True))
    display_df["Fleet Profit"] = proc_df["Fleet Profit ($)"].apply(lambda x: fmt_stat(x, global_base_row["Fleet Profit ($)"], True))

    selection = st.dataframe(display_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row")

    # --- 4. DUAL COMPARISON (With Specific Fees & Fixed Colors) ---
    selected_indices = selection.selection.rows
    
    if len(selected_indices) == 2:
        st.divider()
        st.subheader("⚖️ Peer-to-Peer Comparison")
        
        # Get raw data for the two selected rows
        # We must re-calculate financials because the fees might change in this specific comparison view
        row_a_raw = proc_df.iloc[selected_indices[0]].copy()
        row_b_raw = proc_df.iloc[selected_indices[1]].copy()
        
        # --- RECALCULATE A (Use Dual Baseline Fee) ---
        rev_a = row_a_raw["Rev/Miner ($)"] # Revenue doesn't change based on fee
        cost_a = row_a_raw["Daily Power ($)"] + (rev_a * (fee_dual_base / 100))
        profit_a = rev_a - cost_a
        
        # --- RECALCULATE B (Use Target Fee) ---
        rev_b = row_b_raw["Rev/Miner ($)"]
        cost_b = row_b_raw["Daily Power ($)"] + (rev_b * (fee_target / 100))
        profit_b = rev_b - cost_b
        
        col_comp_1, col_comp_2 = st.columns(2)
        with col_comp_1:
            st.info(f"**Baseline (A):** {row_a_raw['display_name']} @ {fee_dual_base}% Fee")
        with col_comp_2:
            st.success(f"**Target (B):** {row_b_raw['display_name']} @ {fee_target}% Fee")

        # Comparison Logic
        metrics = [
            {"name": "Hashrate (TH/s)", "val_a": row_a_raw["Hashrate (TH/s)"], "val_b": row_b_raw["Hashrate (TH/s)"], "better": "higher", "is_money": False},
            {"name": "Power (W)",       "val_a": row_a_raw["Power (W)"],       "val_b": row_b_raw["Power (W)"],       "better": "lower",  "is_money": False},
            {"name": "Efficiency (J/TH)","val_a": row_a_raw["Efficiency (J/TH)"],"val_b": row_b_raw["Efficiency (J/TH)"],"better": "lower",  "is_money": False},
            {"name": "Profit/Miner ($)","val_a": profit_a,                     "val_b": profit_b,                     "better": "higher", "is_money": True},
            {"name": "Fleet Profit ($)","val_a": profit_a * fleet_size,        "val_b": profit_b * fleet_size,        "better": "higher", "is_money": True},
        ]
        
        # Build HTML Table manually to guarantee color rendering
        html_rows = ""
        for m in metrics:
            val_a, val_b = m['val_a'], m['val_b']
            diff = val_b - val_a
            
            # Formatting
            fmt = "${:,.2f}" if m['is_money'] else "{:,.1f}"
            val_a_str = fmt.format(val_a)
            val_b_str = fmt.format(val_b)
            
            # Color & Sign logic
            if abs(diff) < 0.001:
                color = "gray"
                diff_str = "0.0"
            else:
                is_good = (diff > 0 and m['better'] == "higher") or (diff < 0 and m['better'] == "lower")
                color = "green" if is_good else "red"
                sign = "+" if diff > 0 else ""
                diff_str = f"{sign}{fmt.format(diff)}"

            html_rows += f"""
            <tr style="border-bottom: 1px solid #e0e0e0;">
                <td style="padding: 8px;">{m['name']}</td>
                <td style="padding: 8px;">{val_a_str}</td>
                <td style="padding: 8px;">{val_b_str}</td>
                <td style="padding: 8px; color: {color}; font-weight: bold;">{diff_str}</td>
            </tr>
            """
            
        st.markdown(f"""
        <table style="width:100%; text-align: left; border-collapse: collapse;">
            <thead>
                <tr style="background-color: #f0f2f6;">
                    <th style="padding: 8px;">Metric</th>
                    <th style="padding: 8px;">Baseline (A)</th>
                    <th style="padding: 8px;">Target (B)</th>
                    <th style="padding: 8px;">Difference</th>
                </tr>
            </thead>
            <tbody>
                {html_rows}
            </tbody>
        </table>
        """, unsafe_allow_html=True)

    elif len(selected_indices) > 2:
        st.warning("Please select exactly 2 rows to enable Peer-to-Peer comparison.")

    # --- 5. EXCEL EXPORT WITH FORMULAS ---
    st.divider()
    
    # 1. Setup Buffer
    buffer = io.BytesIO()
    
    # 2. Use XlsxWriter
    workbook = _writer = pd.ExcelWriter(buffer, engine='xlsxwriter')
    # We create the writer but we will access the workbook object directly
    # to write formulas manually.
    
    # Create Sheet
    workbook = workbook.book
    ws = workbook.add_worksheet("Model Data")
    
    # Formats
    fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
    fmt_money = workbook.add_format({'num_format': '$#,##0.00'})
    fmt_number = workbook.add_format({'num_format': '#,##0.0'})
    fmt_pct = workbook.add_format({'num_format': '0.00%'})
    
    # Write Headers
    headers = ["Model", "Profile", "Hashrate (TH)", "Power (W)", "Hashprice ($/PH)", "Power Cost ($/kWh)", "Fee (%)", "Rev ($)", "Daily Power ($)", "Fee Cost ($)", "Total Cost ($)", "Profit ($)"]
    for col_num, header in enumerate(headers):
        ws.write(0, col_num, header, fmt_header)
        
    # Write Data Loop (With Formulas)
    # We iterate through the processed dataframe to get inputs, but we write FORMULAS for calcs
    for i, row in enumerate(proc_df.itertuples(), start=1):
        # Python row index starts at 0, Excel row starts at 1. 
        # But we used row 0 for header, so data starts at row 1 (0-indexed in writer) or Row 2 (1-indexed in Excel logic).
        # Xlsxwriter uses 0-indexed rows/cols.
        
        # Determine Fee based on logic (Using the column we calculated earlier)
        fee_val = row._10 / 100 # _10 is "Global Fee %" column index approx, safer to use name lookup if possible, but itertuples is fast.
        # Let's use direct access for clarity
        model = row.Model
        profile = row.Profile
        hr = row._3 # Hashrate column index in itertuples (Model=1, Profile=2, Hashrate=3...)
        pwr = row._4 # Power
        
        # Excel Row Number (for formula string, 1-based)
        xl_row = i + 1 
        
        # Write Static Inputs
        ws.write(i, 0, model)
        ws.write(i, 1, profile)
        ws.write(i, 2, hr, fmt_number)
        ws.write(i, 3, pwr, fmt_number)
        ws.write(i, 4, hashprice)
        ws.write(i, 5, power_price)
        ws.write(i, 6, row._10/100, fmt_pct) # Fee %
        
        # Write Formulas
        # Revenue = Hashrate (C) * Hashprice (E) / 1000
        ws.write_formula(i, 7, f"=C{xl_row}*E{xl_row}/1000", fmt_money)
        
        # Daily Power = Power (D) / 1000 * 24 * PowerPrice (F)
        ws.write_formula(i, 8, f"=(D{xl_row}/1000)*24*F{xl_row}", fmt_money)
        
        # Fee Cost = Revenue (H) * Fee (G)
        ws.write_formula(i, 9, f"=H{xl_row}*G{xl_row}", fmt_money)
        
        # Total Cost = Power Cost (I) + Fee Cost (J)
        ws.write_formula(i, 10, f"=I{xl_row}+J{xl_row}", fmt_money)
        
        # Profit = Revenue (H) - Total Cost (K)
        ws.write_formula(i, 11, f"=H{xl_row}-K{xl_row}", fmt_money)

    # Adjust Widths
    ws.set_column('A:B', 20)
    ws.set_column('C:L', 15)
    
    # Close Writer
    workbook.close()
    
    st.download_button(
        label="📥 Download Excel (With Formulas)",
        data=buffer.getvalue(),
        file_name="miner_model_formulas.xlsx",
        mime="application/vnd.ms-excel"
    )

else:
    st.warning("Add data to start.")
