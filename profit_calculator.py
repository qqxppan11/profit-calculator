import streamlit as st
import pandas as pd
import io  # Required for handling the Excel file in memory

# --- Page Configuration ---
st.set_page_config(page_title="Miner Profitability Modeling", layout="wide")

st.title("⚡ Miner Profitability & Comparison Tool")
st.markdown("Build fleet scenarios, set a Global Baseline, and compare performance.")

# --- Session State to store the table data ---
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame(
        [
            {"Model": "S19 XP", "Profile": "Normal", "Hashrate (TH/s)": 140.0, "Power (W)": 3010.0},
            {"Model": "S21", "Profile": "Normal", "Hashrate (TH/s)": 200.0, "Power (W)": 3500.0},
            {"Model": "S19j Pro", "Profile": "Oc", "Hashrate (TH/s)": 104.0, "Power (W)": 3068.0},
        ],
    )

# --- Sidebar: Global Settings ---
st.sidebar.header("1. Global Settings")
power_price = st.sidebar.number_input("Power Price ($/kWh)", value=0.05, format="%.4f")
hashprice = st.sidebar.number_input("Hashprice ($/PH/s/Day)", value=60.0, help="Revenue per PH/s per day")
fleet_size = st.sidebar.number_input("Fleet Size (num machines)", value=100, step=1)

st.sidebar.markdown("---")
st.sidebar.header("2. Firmware Fees")
baseline_firmware_fee = st.sidebar.number_input("Baseline Fee (%)", value=1.5, format="%.2f", help="Fee applied to the Baseline machine")
target_firmware_fee = st.sidebar.number_input("Target Fee (%)", value=2.0, format="%.2f", help="Fee applied to all other machines")

# --- Main Interface: Input Table ---
st.subheader("3. Machine Configurations")
st.info("Edit the table below to define your fleet options.")

# Editable Dataframe
edited_df = st.data_editor(
    st.session_state.data,
    num_rows="dynamic",
    use_container_width=True,
    key="editor",
    column_config={
        "Hashrate (TH/s)": st.column_config.NumberColumn(min_value=0, step=0.1, format="%.2f"),
        "Power (W)": st.column_config.NumberColumn(min_value=0, step=0.1, format="%.1f"),
        "Model": st.column_config.TextColumn(required=True),
        "Profile": st.column_config.TextColumn()
    }
)

# --- Calculation Engine ---
if not edited_df.empty:
    # 1. Prepare Data & Calculate Efficiency
    proc_df = edited_df.copy()
    proc_df["Hashrate (TH/s)"] = pd.to_numeric(proc_df["Hashrate (TH/s)"])
    proc_df["Power (W)"] = pd.to_numeric(proc_df["Power (W)"])
    
    # Create a unique ID for selection mapping
    proc_df["display_name"] = proc_df["Model"] + " (" + proc_df["Profile"] + ")"
    
    # --- Sidebar: Baseline Selector (Dependent on Data) ---
    st.sidebar.markdown("---")
    st.sidebar.header("3. Baseline Selection")
    
    # Get list of options for dropdown
    model_options = proc_df["display_name"].tolist()
    
    # Select Baseline
    baseline_name = st.sidebar.selectbox("Select Global Baseline", options=model_options)

    # 2. Calculate Metrics
    # Efficiency
    proc_df["Efficiency (J/TH)"] = proc_df.apply(
        lambda x: x["Power (W)"] / x["Hashrate (TH/s)"] if x["Hashrate (TH/s)"] > 0 else 0, axis=1
    )

    # Financials
    hashprice_per_th = hashprice / 1000
    proc_df["Rev/Miner ($)"] = proc_df["Hashrate (TH/s)"] * hashprice_per_th
    
    # Cost Logic: Baseline gets Baseline Fee, Others get Target Fee
    daily_power_cost = (proc_df["Power (W)"] / 1000) * 24 * power_price
    
    def calculate_fee(row):
        if row["display_name"] == baseline_name:
            return row["Rev/Miner ($)"] * (baseline_firmware_fee / 100)
        else:
            return row["Rev/Miner ($)"] * (target_firmware_fee / 100)

    proc_df["Firmware Cost ($)"] = proc_df.apply(calculate_fee, axis=1)
    proc_df["Cost/Miner ($)"] = daily_power_cost + proc_df["Firmware Cost ($)"]
    proc_df["Profit/Miner ($)"] = proc_df["Rev/Miner ($)"] - proc_df["Cost/Miner ($)"]
    proc_df["Fleet Profit ($)"] = proc_df["Profit/Miner ($)"] * fleet_size

    # 3. Prepare Comparison Data
    # Get Baseline Row Data
    baseline_row = proc_df[proc_df["display_name"] == baseline_name].iloc[0]

    # Function to format cell: "Value (Diff)"
    def format_comparison(val, baseline_val, is_currency=False, is_inverse=False):
        diff = val - baseline_val
        
        # Determine formatting
        fmt = "${:,.2f}" if is_currency else "{:,.1f}"
        
        # If values are essentially equal, just show value
        if abs(diff) < 0.001:
            return fmt.format(val)
        
        # Create Diff String
        sign = "+" if diff > 0 else ""
        diff_str = f"{sign}{fmt.format(diff)}"
        
        return f"{fmt.format(val)} ({diff_str})"

    # --- Display Logic ---
    st.divider()
    col_header, col_toggle = st.columns([3, 1])
    with col_header:
        st.subheader("4. Calculated Results")
        st.caption(f"Comparing against **{baseline_name}** | Baseline Fee: {baseline_firmware_fee}% | Target Fee: {target_firmware_fee}%")
    with col_toggle:
        show_comparison = st.toggle("Show Comparison Details", value=True)

    # Columns to display
    cols_order = ["Model", "Profile", "Hashrate (TH/s)", "Power (W)", "Efficiency (J/TH)", "Rev/Miner ($)", "Cost/Miner ($)", "Profit/Miner ($)", "Fleet Profit ($)"]
    
    if show_comparison:
        # Create a string-based dataframe for display
        display_df = pd.DataFrame()
        display_df["Model"] = proc_df["Model"]
        display_df["Profile"] = proc_df["Profile"]
        
        # Apply formatting with logic
        display_df["Hashrate (TH/s)"] = proc_df["Hashrate (TH/s)"].apply(lambda x: format_comparison(x, baseline_row["Hashrate (TH/s)"]))
        display_df["Power (W)"] = proc_df["Power (W)"].apply(lambda x: format_comparison(x, baseline_row["Power (W)"]))
        display_df["Efficiency (J/TH)"] = proc_df["Efficiency (J/TH)"].apply(lambda x: format_comparison(x, baseline_row["Efficiency (J/TH)"]))
        
        # Financials
        display_df["Rev/Miner ($)"] = proc_df["Rev/Miner ($)"].apply(lambda x: format_comparison(x, baseline_row["Rev/Miner ($)"], is_currency=True))
        display_df["Cost/Miner ($)"] = proc_df["Cost/Miner ($)"].apply(lambda x: format_comparison(x, baseline_row["Cost/Miner ($)"], is_currency=True))
        display_df["Profit/Miner ($)"] = proc_df["Profit/Miner ($)"].apply(lambda x: format_comparison(x, baseline_row["Profit/Miner ($)"], is_currency=True))
        display_df["Fleet Profit ($)"] = proc_df["Fleet Profit ($)"].apply(lambda x: format_comparison(x, baseline_row["Fleet Profit ($)"], is_currency=True))

        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
    else:
        # Show Raw Numbers (Clean Table)
        raw_display = proc_df[cols_order].copy()
        st.dataframe(
            raw_display, 
            use_container_width=True,
            column_config={
                "Hashrate (TH/s)": st.column_config.NumberColumn(format="%.1f"),
                "Power (W)": st.column_config.NumberColumn(format="%.0f"),
                "Efficiency (J/TH)": st.column_config.NumberColumn(format="%.1f J/TH"),
                "Rev/Miner ($)": st.column_config.NumberColumn(format="$%.2f"),
                "Cost/Miner ($)": st.column_config.NumberColumn(format="$%.2f"),
                "Profit/Miner ($)": st.column_config.NumberColumn(format="$%.2f"),
                "Fleet Profit ($)": st.column_config.NumberColumn(format="$%.2f"),
            }
        )

    # --- PROFESSIONAL EXCEL EXPORT ---
    st.divider()
    
    # 1. Create a buffer
    buffer = io.BytesIO()
    
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        
        # SHEET 1: MODEL SUMMARY
        settings_data = {
            "Parameter": ["Power Price", "Hashprice", "Baseline Machine", "Baseline Fee", "Target Fee", "Fleet Size"],
            "Value": [power_price, hashprice, baseline_name, f"{baseline_firmware_fee}%", f"{target_firmware_fee}%", fleet_size]
        }
        pd.DataFrame(settings_data).to_excel(writer, sheet_name='Report', startrow=0, index=False)
        
        # Write Clean Data (Use proc_df which has numbers, not strings)
        export_df = proc_df[cols_order].copy()
        export_df.to_excel(writer, sheet_name='Report', startrow=8, index=False)
        
        # Formatting
        workbook = writer.book
        worksheet = writer.sheets['Report']
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
        money_fmt = workbook.add_format({'num_format': '$#,##0.00'})
        
        # Auto-width
        worksheet.set_column('A:B', 20)
        worksheet.set_column('C:I', 15)
        
        # SHEET 2: DELTA ANALYSIS (New)
        # Create a dataframe of just the differences
        delta_df = pd.DataFrame()
        delta_df["Model"] = proc_df["Model"]
        delta_df["Profile"] = proc_df["Profile"]
        delta_df["Hashrate Delta"] = proc_df["Hashrate (TH/s)"] - baseline_row["Hashrate (TH/s)"]
        delta_df["Profit Delta"] = proc_df["Profit/Miner ($)"] - baseline_row["Profit/Miner ($)"]
        
        delta_df.to_excel(writer, sheet_name='Delta Analysis', index=False)

    st.download_button(
        label="📥 Download Excel Report",
        data=buffer.getvalue(),
        file_name="miner_comparison_model.xlsx",
        mime="application/vnd.ms-excel"
    )

else:
    st.warning("Please add data to the table.")
