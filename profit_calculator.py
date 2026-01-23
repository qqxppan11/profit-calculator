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
# Fee 1: Global/Standard
std_firmware_fee = st.sidebar.number_input("Standard Fleet Fee (%)", value=2.0, format="%.2f", help="Applied to the main table calculations.")

# Fees 2 & 3: For Comparison Mode
st.sidebar.caption("For Comparison Mode Only:")
col_fee_a, col_fee_b = st.sidebar.columns(2)
with col_fee_a:
    comp_fee_a = st.number_input("Scenario Fee A (%)", value=2.0, format="%.2f", help="Fee for Baseline in Comparison Mode")
with col_fee_b:
    comp_fee_b = st.number_input("Scenario Fee B (%)", value=3.0, format="%.2f", help="Fee for Target in Comparison Mode")

st.sidebar.markdown("---")
st.sidebar.header("3. Table Display")

# Helper to get list of models for dropdown
model_options = st.session_state.data["Model"] + " - " + st.session_state.data["Profile"]
# Select Global Baseline
baseline_index = st.sidebar.selectbox(
    "Select Global Baseline Model", 
    options=range(len(st.session_state.data)), 
    format_func=lambda x: f"{st.session_state.data.iloc[x]['Model']} ({st.session_state.data.iloc[x]['Profile']})"
)
show_baseline_comp = st.sidebar.toggle("Show vs Baseline in Main Table", value=True)


# --- Main Interface: Input Table ---
st.subheader("4. Machine Configurations")
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

# Initialize variables
comp_df_clean = None
comparison_title = ""

# --- Calculation Engine ---
if not edited_df.empty:
    # 1. Base Calculations (Using Standard Fee)
    calc_df = edited_df.copy()
    calc_df["Hashrate (TH/s)"] = pd.to_numeric(calc_df["Hashrate (TH/s)"])
    calc_df["Power (W)"] = pd.to_numeric(calc_df["Power (W)"])
    
    # Efficiency
    calc_df["Efficiency (J/TH)"] = calc_df.apply(lambda x: x["Power (W)"] / x["Hashrate (TH/s)"] if x["Hashrate (TH/s)"] > 0 else 0, axis=1)

    # Financials
    hp_per_th = hashprice / 1000
    calc_df["Rev/Day ($)"] = calc_df["Hashrate (TH/s)"] * hp_per_th
    
    # Costs (Power + Standard Fee)
    daily_power_cost = (calc_df["Power (W)"] / 1000) * 24 * power_price
    fee_cost = calc_df["Rev/Day ($)"] * (std_firmware_fee / 100)
    calc_df["Cost/Day ($)"] = daily_power_cost + fee_cost
    
    calc_df["Profit/Day ($)"] = calc_df["Rev/Day ($)"] - calc_df["Cost/Day ($)"]
    calc_df["Fleet Profit ($)"] = calc_df["Profit/Day ($)"] * fleet_size

    # 2. Global Baseline Comparison Logic
    # Get the baseline profit from the selected index
    try:
        baseline_row = calc_df.iloc[baseline_index]
        baseline_profit = baseline_row["Profit/Day ($)"]
    except IndexError:
        baseline_profit = 0 # Fallback

    if show_baseline_comp:
        calc_df["Δ Profit ($)"] = calc_df["Profit/Day ($)"] - baseline_profit

    # 3. Formatting for Display
    display_cols = ["Model", "Profile", "Hashrate (TH/s)", "Power (W)", "Efficiency (J/TH)", "Rev/Day ($)", "Cost/Day ($)", "Profit/Day ($)"]
    if show_baseline_comp:
        display_cols.append("Δ Profit ($)")
    display_cols.append("Fleet Profit ($)")
    
    final_df = calc_df[display_cols].copy()
    
    # Rounding
    final_df["Efficiency (J/TH)"] = final_df["Efficiency (J/TH)"].round(1)
    money_cols = ["Rev/Day ($)", "Cost/Day ($)", "Profit/Day ($)", "Fleet Profit ($)"]
    final_df[money_cols] = final_df[money_cols].round(2)
    if show_baseline_comp:
        final_df["Δ Profit ($)"] = final_df["Δ Profit ($)"].round(2)

    st.markdown("### 5. Calculated Results")
    
    # Selection Table
    selection = st.dataframe(
        final_df,
        use_container_width=True,
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Efficiency (J/TH)": st.column_config.NumberColumn(format="%.1f J/TH"),
            "Power (W)": st.column_config.NumberColumn(format="%.1f W"),
            "Δ Profit ($)": st.column_config.NumberColumn(
                format="$%.2f",
                help="Daily profit difference vs Global Baseline",
            )
        }
    )

    # --- Comparison Mode (Logic remains similar, but uses specific fees) ---
    selected_rows = selection.selection.rows
    
    if len(selected_rows) == 2:
        st.divider()
        st.subheader("⚖️ Comparison Mode (Scenario Analysis)")
        
        # Determine A and B
        idx_a = selected_rows[0]
        idx_b = selected_rows[1]
        
        # Selectors to flip A/B if needed
        col_sel_a, col_sel_b = st.columns(2)
        with col_sel_a:
            st.markdown(f"**Scenario A (Baseline)** - Uses {comp_fee_a}% Fee")
            st.info(f"{calc_df.iloc[idx_a]['Model']} ({calc_df.iloc[idx_a]['Profile']})")
        with col_sel_b:
            st.markdown(f"**Scenario B (Target)** - Uses {comp_fee_b}% Fee")
            st.success(f"{calc_df.iloc[idx_b]['Model']} ({calc_df.iloc[idx_b]['Profile']})")

        # --- Recalculate A & B with SPECIFIC FEES ---
        def calculate_scenario(idx, fee_pct):
            r = calc_df.iloc[idx]
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
        
        comparison_title = f"Scenario: {calc_df.iloc[idx_b]['Model']} ({comp_fee_b}%) vs {calc_df.iloc[idx_a]['Model']} ({comp_fee_a}%)"

        # Build Comparison Data
        metrics_order = ["Hashrate (TH/s)", "Power (W)", "Efficiency (J/TH)", "Rev/Day ($)", "Cost/Day ($)", "Profit/Day ($)", "Fleet Profit ($)"]
        better_direction = {"Hashrate (TH/s)": "high", "Power (W)": "low", "Efficiency (J/TH)": "low", "Rev/Day ($)": "high", "Cost/Day ($)": "low", "Profit/Day ($)": "high", "Fleet Profit ($)": "high"}
        
        comp_data_display = []
        comp_data_clean = []

        for m in metrics_order:
            val_a = res_a[m]
            val_b = res_b[m]
            diff = val_b - val_a
            pct = (diff / val_a * 100) if val_a != 0 else 0
            
            # Color logic
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

    # --- EXCEL EXPORT WITH FORMULAS ---
    st.divider()
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        workbook = writer.book
        ws = workbook.add_worksheet("Model Report")
        
        # Formats
        fmt_header = workbook.add_format({'bold': True, 'bg_color': '#EFEFEF', 'border': 1})
        fmt_money = workbook.add_format({'num_format': '$#,##0.00'})
        fmt_number = workbook.add_format({'num_format': '#,##0.00'})
        
        # 1. Write Global Settings (Static)
        ws.write(0, 0, "Global Assumptions", fmt_header)
        ws.write(1, 0, "Power Price ($/kWh)")
        ws.write(1, 1, power_price)
        ws.write(2, 0, "Hashprice ($/PH/Day)")
        ws.write(2, 1, hashprice)
        ws.write(3, 0, "Fleet Size")
        ws.write(3, 1, fleet_size)
        ws.write(4, 0, "Standard Fee (%)")
        ws.write(4, 1, std_firmware_fee)
        
        # 2. Write Data Table with FORMULAS
        # Headers
        table_start_row = 7
        headers = ["Model", "Profile", "Hashrate (TH)", "Power (W)", "Efficiency (J/TH)", "Rev/Day ($)", "Cost/Day ($)", "Profit/Day ($)", "Fleet Profit ($)"]
        for col_num, h in enumerate(headers):
            ws.write(table_start_row, col_num, h, fmt_header)
            
        # Rows
        # Excel Formulas Logic:
        # We need to map row index to Excel row number.
        # Data starts at table_start_row + 1.
        # B2 reference for Power Price is $B$2
        # B3 reference for Hashprice is $B$3
        # B5 reference for Fee is $B$5
        
        for i, row in calc_df.iterrows():
            r = table_start_row + 1 + i
            excel_row = r + 1 # 1-based index for string representation
            
            # Static Inputs
            ws.write(r, 0, row["Model"])
            ws.write(r, 1, row["Profile"])
            ws.write(r, 2, row["Hashrate (TH/s)"]) # C
            ws.write(r, 3, row["Power (W)"])       # D
            
            # Formula: Efficiency = Power / Hashrate = D / C
            ws.write_formula(r, 4, f'=IF(C{excel_row}>0, D{excel_row}/C{excel_row}, 0)', fmt_number)
            
            # Formula: Rev = Hashrate * (Hashprice/1000) = C * ($B$3/1000)
            ws.write_formula(r, 5, f'=C{excel_row}*($B$3/1000)', fmt_money)
            
            # Formula: Cost = (Power/1000 * 24 * Price) + (Rev * Fee%)
            # Power Cost = D/1000 * 24 * $B$2
            # Fee Cost = F * ($B$5/100)
            ws.write_formula(r, 6, f'=(D{excel_row}/1000*24*$B$2)+(F{excel_row}*($B$5/100))', fmt_money)
            
            # Formula: Profit = Rev - Cost = F - G
            ws.write_formula(r, 7, f'=F{excel_row}-G{excel_row}', fmt_money)
            
            # Formula: Fleet = Profit * FleetSize = H * $B$4
            ws.write_formula(r, 8, f'=H{excel_row}*$B$4', fmt_money)

        # Widen columns
        ws.set_column('A:B', 20)
        ws.set_column('C:I', 15)

        # 3. Write Comparison Report (If active)
        if comp_df_clean is not None:
            ws_comp = workbook.add_worksheet("Comparison Mode")
            ws_comp.write(0, 0, comparison_title, fmt_header)
            
            # Write headers
            comp_headers = list(comp_df_clean.columns)
            for col_num, h in enumerate(comp_headers):
                ws_comp.write(2, col_num, h, fmt_header)
            
            # Write Data
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
