import streamlit as st
import pandas as pd
import io  # Required for handling the Excel file in memory

# --- Page Configuration ---
st.set_page_config(page_title="Miner Profitability Modeling", layout="wide")

st.title("⚡ Miner Profitability & Comparison Tool")
st.markdown("Build fleet scenarios, calculate metrics, and compare specific configurations.")

# --- Sidebar: Global Settings ---
st.sidebar.header("1. Global Settings")
power_price = st.sidebar.number_input("Power Price ($/kWh)", value=0.05, format="%.4f")
pool_fee_percent = st.sidebar.number_input("Pool Fee (%)", value=1.5, format="%.2f")
hashprice = st.sidebar.number_input("Hashprice ($/PH/s/Day)", value=60.0, help="Revenue per PH/s per day")

st.sidebar.markdown("---")
st.sidebar.header("2. Fleet Settings")
fleet_size = st.sidebar.number_input("Fleet Size (num machines)", value=100, step=1)

# --- Session State to store the table data ---
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame(
        [{"Model": "S19 XP", "Profile": "Normal", "Hashrate (TH/s)": 140.0, "Power (W)": 3010.0}],
    )

# --- Main Interface: Input Table ---
st.subheader("3. Machine Configurations")
st.info("Edit the table below. You can now use decimals for both Hashrate and Power.")

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

# Initialize variables for export
comp_df_clean = None
comparison_title = ""

# --- Calculation Engine ---
if not edited_df.empty:
    # 1. Prepare Data & Calculate Efficiency
    edited_df["Hashrate (TH/s)"] = pd.to_numeric(edited_df["Hashrate (TH/s)"])
    edited_df["Power (W)"] = pd.to_numeric(edited_df["Power (W)"])
    
    # Calculate Efficiency (J/TH)
    edited_df["Efficiency (J/TH)"] = edited_df.apply(
        lambda x: x["Power (W)"] / x["Hashrate (TH/s)"] if x["Hashrate (TH/s)"] > 0 else 0, axis=1
    )

    # 2. Calculate Financials
    hashprice_per_th = hashprice / 1000
    
    # Revenue
    edited_df["Rev/Miner ($)"] = edited_df["Hashrate (TH/s)"] * hashprice_per_th
    
    # Cost
    daily_power_cost = (edited_df["Power (W)"] / 1000) * 24 * power_price
    pool_fee_cost = edited_df["Rev/Miner ($)"] * (pool_fee_percent / 100)
    edited_df["Cost/Miner ($)"] = daily_power_cost + pool_fee_cost
    
    # Profit
    edited_df["Profit/Miner ($)"] = edited_df["Rev/Miner ($)"] - edited_df["Cost/Miner ($)"]
    edited_df["Fleet Profit ($)"] = edited_df["Profit/Miner ($)"] * fleet_size

    # 3. Formatting Data for Display
    display_df = edited_df.copy()
    
    # Column Ordering
    cols_order = [
        "Model", "Profile", "Hashrate (TH/s)", "Power (W)", "Efficiency (J/TH)", 
        "Rev/Miner ($)", "Cost/Miner ($)", "Profit/Miner ($)", "Fleet Profit ($)"
    ]
    final_cols = [c for c in cols_order if c in display_df.columns]
    display_df = display_df[final_cols]

    # Rounding for UI
    display_df["Efficiency (J/TH)"] = display_df["Efficiency (J/TH)"].round(1)
    money_cols = ["Rev/Miner ($)", "Cost/Miner ($)", "Profit/Miner ($)", "Fleet Profit ($)"]
    display_df[money_cols] = display_df[money_cols].round(2)

    st.markdown("### 4. Calculated Results")
    
    # Selection Table
    selection = st.dataframe(
        display_df,
        use_container_width=True,
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Efficiency (J/TH)": st.column_config.NumberColumn(format="%.1f J/TH"),
            "Power (W)": st.column_config.NumberColumn(format="%.1f W")
        }
    )

    # --- Comparison Logic ---
    selected_rows = selection.selection.rows
    
    if len(selected_rows) == 2:
        st.divider()
        st.subheader("⚖️ Comparison Mode")
        
        def get_row_name(idx):
            if idx < len(display_df):
                r = display_df.iloc[idx]
                return f"{r['Model']} ({r['Profile']})"
            return "Unknown"

        # 1. Comparison Selectors
        col_sel_a, col_sel_b = st.columns(2)
        options_map = {idx: get_row_name(idx) for idx in selected_rows}
        
        with col_sel_a:
            idx_a = st.selectbox("Select Baseline (A)", options=selected_rows, format_func=lambda x: options_map.get(x, "Unknown"), key="a")
        with col_sel_b:
            default_b = selected_rows[1] if len(selected_rows) > 1 and idx_a == selected_rows[0] else selected_rows[0]
            if default_b not in selected_rows: default_b = selected_rows[0]
            idx_b = st.selectbox("Select Target (B)", options=selected_rows, format_func=lambda x: options_map.get(x, "Unknown"), index=selected_rows.index(default_b), key="b")

        # 2. Extract Data
        row_a = display_df.iloc[idx_a]
        row_b = display_df.iloc[idx_b]
        
        comparison_title = f"Comparison: {options_map[idx_b]} vs Baseline {options_map[idx_a]}"

        # 3. Build Comparison Logic
        metrics_config = [
            {"col": "Hashrate (TH/s)", "better": "higher"},
            {"col": "Power (W)", "better": "lower"},
            {"col": "Efficiency (J/TH)", "better": "lower"},
            {"col": "Rev/Miner ($)", "better": "higher"},
            {"col": "Cost/Miner ($)", "better": "lower"},
            {"col": "Profit/Miner ($)", "better": "higher"},
            {"col": "Fleet Profit ($)", "better": "higher"},
        ]
        
        comp_data_display = [] # For Streamlit (with colors)
        comp_data_clean = []   # For Excel (raw numbers)
        
        for item in metrics_config:
            metric = item['col']
            is_higher_better = item['better'] == "higher"
            
            val_a = row_a[metric]
            val_b = row_b[metric]
            diff = val_b - val_a
            
            if val_a != 0:
                pct_diff = (diff / val_a) * 100
            else:
                pct_diff = 0.0
            
            # --- Visual Logic (Green/Red) for Streamlit ---
            is_positive_outcome = (is_higher_better and diff > 0) or (not is_higher_better and diff < 0)
            is_neutral = (diff == 0)

            if is_neutral: color = "gray"
            elif is_positive_outcome: color = "green"
            else: color = "red"

            comp_data_display.append({
                "Metric": metric,
                "Baseline (A)": val_a,
                "Target (B)": val_b,
                "Difference": f":{color}[{diff:+.2f}]",
                "% Change": f":{color}[{pct_diff:+.2f}%]"
            })
            
            # --- Clean Logic for Excel ---
            comp_data_clean.append({
                "Metric": metric,
                "Baseline (A)": val_a,
                "Target (B)": val_b,
                "Diff": diff,
                "% Change": pct_diff / 100 # Store as decimal for Excel % formatting
            })
            
        # 4. Render Table in App
        comp_df = pd.DataFrame(comp_data_display)
        comp_df_clean = pd.DataFrame(comp_data_clean) # Save this for Export
        
        st.markdown(comp_df.to_markdown(index=False), unsafe_allow_html=True)
        st.caption(comparison_title)
            
    elif len(selected_rows) > 2:
        st.warning("Please select exactly 2 rows to compare.")
    
    # --- PROFESSIONAL EXCEL EXPORT ---
    st.divider()
    
    # 1. Create a buffer to hold the Excel file in memory
    buffer = io.BytesIO()
    
    # 2. Use xlsxwriter to create the file
    # We use 'xlsxwriter' because it allows nice formatting (column widths, etc.)
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        
        # --- SHEET 1: MODEL SUMMARY ---
        # Create a dataframe for the global settings
        settings_data = {
            "Parameter": ["Power Price ($/kWh)", "Hashprice ($/PH/Day)", "Pool Fee (%)", "Fleet Size"],
            "Value": [power_price, hashprice, pool_fee_percent, fleet_size]
        }
        settings_df = pd.DataFrame(settings_data)
        
        # Write Settings
        settings_df.to_excel(writer, sheet_name='Model Report', startrow=0, startcol=0, index=False)
        
        # Write Main Data (Leave a gap of 2 rows)
        display_df.to_excel(writer, sheet_name='Model Report', startrow=6, startcol=0, index=False)
        
        # Access the workbook/worksheet for formatting
        workbook = writer.book
        worksheet = writer.sheets['Model Report']
        
        # Add a Header Format
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
        money_fmt = workbook.add_format({'num_format': '$#,##0.00'})
        
        # Widen Columns for readability
        worksheet.set_column('A:A', 25) # Parameter / Model Name
        worksheet.set_column('B:I', 18) # Data columns
        
        # --- SHEET 2: COMPARISON (If Active) ---
        if comp_df_clean is not None:
            comp_df_clean.to_excel(writer, sheet_name='Comparison', startrow=2, index=False)
            ws_comp = writer.sheets['Comparison']
            
            # Write a title row
            ws_comp.write(0, 0, comparison_title, workbook.add_format({'bold': True, 'font_size': 12}))
            
            # Format % column (Column E is index 4)
            pct_fmt = workbook.add_format({'num_format': '0.00%'})
            ws_comp.set_column('E:E', 12, pct_fmt)
            ws_comp.set_column('A:A', 20)
            ws_comp.set_column('B:D', 15)

    # 3. Create the Download Button
    st.download_button(
        label="📥 Download Professional Excel Report",
        data=buffer.getvalue(),
        file_name="luxor_mining_model.xlsx",
        mime="application/vnd.ms-excel"
    )

else:
    st.warning("Please add data to the table.")
