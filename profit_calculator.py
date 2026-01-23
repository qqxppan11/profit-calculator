import streamlit as st
import pandas as pd
import io
import xlsxwriter

# --- Page Configuration ---
st.set_page_config(page_title="Miner Profitability Modeling", layout="wide")

st.title("⚡ Miner Profitability & Comparison Tool")
st.markdown("Build fleet scenarios, calculate metrics, and compare specific configurations.")

# --- Session State ---
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame(
        [
            {"Model": "S19 XP", "Profile": "Normal", "Hashrate (TH/s)": 140.0, "Power (W)": 3010.0},
            {"Model": "S19j Pro", "Profile": "Normal", "Hashrate (TH/s)": 100.0, "Power (W)": 3050.0},
            {"Model": "S21", "Profile": "Boost", "Hashrate (TH/s)": 200.0, "Power (W)": 3500.0},
        ]
    )

# --- Sidebar: Global Settings ---
st.sidebar.header("1. Global Assumptions")
power_price = st.sidebar.number_input("Power Price ($/kWh)", value=0.05, format="%.4f")
hashprice = st.sidebar.number_input("Hashprice ($/PH/s/Day)", value=60.0)
fleet_size = st.sidebar.number_input("Fleet Size (num machines)", value=100, step=1)

st.sidebar.markdown("---")
st.sidebar.header("2. Fee Structures")
std_firmware_fee = st.sidebar.number_input("Standard Fleet Fee (%)", value=2.0, format="%.2f", help="Applied to the main table calculations.")

st.sidebar.caption("For Comparison Mode Only:")
col_fee_a, col_fee_b = st.sidebar.columns(2)
with col_fee_a:
    comp_fee_a = st.number_input("Scenario Fee A (%)", value=2.0, format="%.2f", help="Fee for Baseline in Comparison Mode")
with col_fee_b:
    comp_fee_b = st.number_input("Scenario Fee B (%)", value=3.0, format="%.2f", help="Fee for Target in Comparison Mode")

# --- Main Interface: Input Table ---
st.subheader("3. Machine Configurations")
edited_df = st.data_editor(
    st.session_state.data,
    num_rows="dynamic",
    use_container_width=True,
    key="editor",
    column_config={
        "Hashrate (TH/s)": st.column_config.NumberColumn(min_value=0, step=0.1, format="%.2f"),
        "Power (W)": st.column_config.NumberColumn(min_value=0, step=0.1, format="%.1f"),
        "Model": st.column_config.TextColumn(required=True),
    }
)

# --- Sidebar: Baseline Selector ---
st.sidebar.markdown("---")
st.sidebar.header("3. Table Display")

valid_indices = list(edited_df.index)
if not valid_indices:
    st.error("Table is empty.")
    st.stop()

def get_model_name(idx):
    if idx in edited_df.index:
        row = edited_df.loc[idx]
        return f"{row['Model']} ({row['Profile']})"
    return "Unknown"

baseline_index = st.sidebar.selectbox(
    "Select Global Baseline Model", 
    options=valid_indices, 
    format_func=get_model_name
)
show_baseline_comp = st.sidebar.toggle("Show vs Baseline Columns", value=True)

# Initialize export variable to prevent NameError
comp_df_clean = None

# --- Calculation Engine ---
if not edited_df.empty:
    st.session_state.data = edited_df

    # 1. Base Calculations
    calc_df = edited_df.copy()
    calc_df["Hashrate (TH/s)"] = pd.to_numeric(calc_df["Hashrate (TH/s)"])
    calc_df["Power (W)"] = pd.to_numeric(calc_df["Power (W)"])
    
    # Efficiency
    calc_df["Efficiency (J/TH)"] = calc_df.apply(lambda x: x["Power (W)"] / x["Hashrate (TH/s)"] if x["Hashrate (TH/s)"] > 0 else 0, axis=1)

    # Financials
    hp_per_th = hashprice / 1000
    calc_df["Rev/Day ($)"] = calc_df["Hashrate (TH/s)"] * hp_per_th
    
    daily_power_cost = (calc_df["Power (W)"] / 1000) * 24 * power_price
    fee_cost = calc_df["Rev/Day ($)"] * (std_firmware_fee / 100)
    calc_df["Cost/Day ($)"] = daily_power_cost + fee_cost
    
    calc_df["Profit/Day ($)"] = calc_df["Rev/Day ($)"] - calc_df["Cost/Day ($)"]
    calc_df["Fleet Profit ($)"] = calc_df["Profit/Day ($)"] * fleet_size

    # 2. Formatting & Delta Logic
    base_cols = ["Model", "Profile", "Hashrate (TH/s)", "Power (W)", "Efficiency (J/TH)", "Rev/Day ($)", "Cost/Day ($)", "Profit/Day ($)", "Fleet Profit ($)"]
    
    # Identify numeric columns for strict formatting (prevents ValueError)
    numeric_display_cols = ["Hashrate (TH/s)", "Power (W)", "Efficiency (J/TH)", "Rev/Day ($)", "Cost/Day ($)", "Profit/Day ($)", "Fleet Profit ($)"]
    money_cols = ["Rev/Day ($)", "Cost/Day ($)", "Profit/Day ($)", "Fleet Profit ($)"]

    if show_baseline_comp:
        base_r = calc_df.loc[baseline_index]
        
        # Helper to create "Delta (Pct%)" string
        def make_delta_str(val, base_val, is_money=False):
            diff = val - base_val
            if base_val == 0:
                pct = 0.0
            else:
                pct = (diff / base_val) * 100
            
            # Format
            fmt_diff = f"{diff:+,.2f}" if is_money else f"{diff:+.1f}"
            if is_money and diff == 0: fmt_diff = "$0.00"
            if is_money and diff != 0: fmt_diff = f"${diff:+,.2f}"
                
            return f"{fmt_diff} ({pct:+.1f}%)"

        # Create String Columns for Deltas
        calc_df["Δ Hash"] = calc_df["Hashrate (TH/s)"].apply(lambda x: make_delta_str(x, base_r["Hashrate (TH/s)"]))
        calc_df["Δ Power"] = calc_df["Power (W)"].apply(lambda x: make_delta_str(x, base_r["Power (W)"]))
        calc_df["Δ Eff"] = calc_df["Efficiency (J/TH)"].apply(lambda x: make_delta_str(x, base_r["Efficiency (J/TH)"]))
        calc_df["Δ Profit"] = calc_df["Profit/Day ($)"].apply(lambda x: make_delta_str(x, base_r["Profit/Day ($)"], is_money=True))

        ordered_cols = [
            "Model", "Profile", 
            "Hashrate (TH/s)", "Δ Hash",
            "Power (W)", "Δ Power",
            "Efficiency (J/TH)", "Δ Eff",
            "Profit/Day ($)", "Δ Profit",
            "Fleet Profit ($)"
        ]
        final_df = calc_df[ordered_cols].copy()
    else:
        final_df = calc_df[base_cols].copy()

    st.markdown("### 4. Calculated Results")
    
    # --- STYLING LOGIC ---
    # Function to color text based on string content ("+" is green/red, "-" is red/green)
    def color_delta_strings(val, mode='high_good'):
        if not isinstance(val, str): return ''
        # Check first character (ignoring '$' if present)
        clean_val = val.replace('$', '')
        if clean_val.startswith('+'):
            color = 'green' if mode == 'high_good' else 'red'
        elif clean_val.startswith('-'):
            color = 'red' if mode == 'high_good' else 'green'
        else:
            return 'color: gray' # For 0.00
            
        return f'color: {color}'

    # Apply Styler
    styler = final_df.style
    
    # 1. Format standard numeric columns (Safe subsetting)
    # Note: We filter strictly to columns that exist in final_df
    valid_numeric_cols = [c for c in numeric_display_cols if c in final_df.columns]
    valid_money_cols = [c for c in money_cols if c in final_df.columns]
    
    styler = styler.format("{:.1f}", subset=[c for c in valid_numeric_cols if "Efficiency" in c or "Hashrate" in c])
    styler = styler.format("{:.0f}", subset=[c for c in valid_numeric_cols if "Power" in c])
    styler = styler.format("${:.2f}", subset=valid_money_cols)

    # 2. Color Deltas (Only if columns exist)
    if show_baseline_comp:
        styler = styler.applymap(lambda v: color_delta_strings(v, 'high_good'), subset=["Δ Hash", "Δ Profit"])
        styler = styler.applymap(lambda v: color_delta_strings(v, 'low_good'), subset=["Δ Power", "Δ Eff"])

    # Selection Table
    selection = st.dataframe(
        styler,
        use_container_width=True,
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Δ Hash": st.column_config.TextColumn(help="Change vs Baseline"),
            "Δ Power": st.column_config.TextColumn(help="Change vs Baseline"),
            "Δ Eff": st.column_config.TextColumn(help="Change vs Baseline"),
            "Δ Profit": st.column_config.TextColumn(help="Change vs Baseline"),
        }
    )

    # --- Comparison Mode ---
    selected_rows = selection.selection.rows
    
    if len(selected_rows) == 2:
        st.divider()
        st.subheader("⚖️ Comparison Mode (Scenario Analysis)")
        
        idx_a = selected_rows[0]
        idx_b = selected_rows[1]
        
        col_sel_a, col_sel_b = st.columns(2)
        with col_sel_a:
            st.markdown(f"**Scenario A (Baseline)** - Uses {comp_fee_a}% Fee")
            st.info(get_model_name(idx_a))
        with col_sel_b:
            st.markdown(f"**Scenario B (Target)** - Uses {comp_fee_b}% Fee")
            st.success(get_model_name(idx_b))

        def calculate_scenario(idx, fee_pct):
            r = calc_df.loc[idx]
            rev = r["Hashrate (TH/s)"] * (hashprice / 1000)
            pwr_cost = (r["Power (W)"] / 1000) * 24 * power_price
            fee_c = rev * (fee_pct / 100)
            cost = pwr_cost + fee_c
            profit = rev - cost
            return {
                "Hashrate (TH/s)": r["Hashrate (TH/s)"],
                "Power (W)": r["Power (W)"],
                "Efficiency (J/TH)": r["Efficiency (J/TH)"],
                "Rev/Day ($)": rev,
                "Cost/Day ($)": cost,
                "Profit/Day ($)": profit,
                "Fleet Profit ($)": profit * fleet_size
            }

        res_a = calculate_scenario(idx_a, comp_fee_a)
        res_b = calculate_scenario(idx_b, comp_fee_b)
        
        comparison_title = f"Scenario: {get_model_name(idx_b)} ({comp_fee_b}%) vs {get_model_name(idx_a)} ({comp_fee_a}%)"

        metrics_order = ["Hashrate (TH/s)", "Power (W)", "Efficiency (J/TH)", "Rev/Day ($)", "Cost/Day ($)", "Profit/Day ($)", "Fleet Profit ($)"]
        better_direction = {"Hashrate (TH/s)": "high", "Power (W)": "low", "Efficiency (J/TH)": "low", "Rev/Day ($)": "high", "Cost/Day ($)": "low", "Profit/Day ($)": "high", "Fleet Profit ($)": "high"}
        
        comp_data_display = []
        comp_data_clean = []

        for m in metrics_order:
            val_a = res_a[m]
            val_b = res_b[m]
            diff = val_b - val_a
            pct = (diff / val_a * 100) if val_a != 0 else 0
            
            is_better = False
            if better_direction[m] == "high" and diff > 0: is_better = True
            if better_direction[m] == "low" and diff < 0: is_better = True
            
            color = "green" if is_better else "red"
            if diff == 0: color = "gray"

            comp_data_display.append({
                "Metric": m,
                "Scenario A": f"{val_a:,.2f}",
                "Scenario B": f"{val_b:,.2f}",
                "Difference": f":{color}[{diff:+,.2f}]",
                "% Change": f":{color}[{pct:+.2f}%]"
            })
            
            comp_data_clean.append({
                "Metric": m,
                "Scenario A": val_a,
                "Scenario B": val_b,
                "Difference": diff,
                "% Change": pct/100
            })

        st.markdown(pd.DataFrame(comp_data_display).to_markdown(index=False), unsafe_allow_html=True)
        comp_df_clean = pd.DataFrame(comp_data_clean)

    elif len(selected_rows) > 2:
        st.warning("Please select exactly 2 rows to enter Comparison Mode.")

    # --- EXCEL EXPORT ---
    st.divider()
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        workbook = writer.book
        ws = workbook.add_worksheet("Model Report")
        
        fmt_header = workbook.add_format({'bold': True, 'bg_color': '#EFEFEF', 'border': 1})
        fmt_money = workbook.add_format({'num_format': '$#,##0.00'})
        fmt_number = workbook.add_format({'num_format': '#,##0.00'})
        
        # Globals
        ws.write(0, 0, "Global Assumptions", fmt_header)
        ws.write(1, 0, "Power Price ($/kWh)")
        ws.write(1, 1, power_price)
        ws.write(2, 0, "Hashprice ($/PH/Day)")
        ws.write(2, 1, hashprice)
        ws.write(3, 0, "Fleet Size")
        ws.write(3, 1, fleet_size)
        ws.write(4, 0, "Standard Fee (%)")
        ws.write(4, 1, std_firmware_fee)
        
        # Main Data
        table_start_row = 7
        headers = ["Model", "Profile", "Hashrate (TH)", "Power (W)", "Efficiency (J/TH)", "Rev/Day ($)", "Cost/Day ($)", "Profit/Day ($)", "Fleet Profit ($)"]
        for col_num, h in enumerate(headers):
            ws.write(table_start_row, col_num, h, fmt_header)
            
        for i, row in calc_df.iterrows():
            r = table_start_row + 1 + i
            excel_row = r + 1 
            
            ws.write(r, 0, row["Model"])
            ws.write(r, 1, row["Profile"])
            ws.write(r, 2, row["Hashrate (TH/s)"]) 
            ws.write(r, 3, row["Power (W)"])       
            ws.write_formula(r, 4, f'=IF(C{excel_row}>0, D{excel_row}/C{excel_row}, 0)', fmt_number)
            ws.write_formula(r, 5, f'=C{excel_row}*($B$3/1000)', fmt_money)
            ws.write_formula(r, 6, f'=(D{excel_row}/1000*24*$B$2)+(F{excel_row}*($B$5/100))', fmt_money)
            ws.write_formula(r, 7, f'=F{excel_row}-G{excel_row}', fmt_money)
            ws.write_formula(r, 8, f'=H{excel_row}*$B$4', fmt_money)

        ws.set_column('A:B', 20)
        ws.set_column('C:I', 15)

        # Comparison (Safe check)
        if comp_df_clean is not None:
            ws_comp = workbook.add_worksheet("Comparison Mode")
            ws_comp.write(0, 0, comparison_title, fmt_header)
            
            comp_headers = list(comp_df_clean.columns)
            for col_num, h in enumerate(comp_headers):
                ws_comp.write(2, col_num, h, fmt_header)
            
            for i, row in comp_df_clean.iterrows():
                ws_comp.write(i+3, 0, row["Metric"])
                ws_comp.write(i+3, 1, row["Scenario A"], fmt_number)
                ws_comp.write(i+3, 2, row["Scenario B"], fmt_number)
                ws_comp.write(i+3, 3, row["Difference"], fmt_number)
                ws_comp.write(i+3, 4, row["% Change"], workbook.add_format({'num_format': '0.00%'}))
            
            ws_comp.set_column('A:A', 20)
            ws_comp.set_column('B:E', 15)

    st.download_button(
        label="📥 Download Excel (With Live Formulas)",
        data=buffer.getvalue(),
        file_name="miner_model_live.xlsx",
        mime="application/vnd.ms-excel"
    )

else:
    st.warning("Please add data to the table.")
