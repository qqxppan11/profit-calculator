import streamlit as st
import pandas as pd
import io

# --- Page Configuration ---
st.set_page_config(page_title="Miner Profitability Modeling", layout="wide")

st.title("⚡ Miner Profitability & Comparison Tool")
st.markdown("Global Baseline analysis with optional specific peer-to-peer comparison.")

# --- Session State ---
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame([
        {"Model": "S19 XP", "Profile": "Normal", "Hashrate (TH/s)": 140.0, "Power (W)": 3010.0},
        {"Model": "S21", "Profile": "Normal", "Hashrate (TH/s)": 200.0, "Power (W)": 3500.0},
        {"Model": "S19j Pro", "Profile": "Oc", "Hashrate (TH/s)": 104.0, "Power (W)": 3068.0},
    ])

# --- Sidebar: Global Settings ---
st.sidebar.header("1. Global Settings")
power_price = st.sidebar.number_input("Power Price ($/kWh)", value=0.05, format="%.4f")
hashprice = st.sidebar.number_input("Hashprice ($/PH/s/Day)", value=60.0)
fleet_size = st.sidebar.number_input("Fleet Size", value=100, step=1)

st.sidebar.markdown("---")
st.sidebar.header("2. Firmware Fees")
baseline_fee = st.sidebar.number_input("Baseline Fee (%)", value=1.5, format="%.2f")
target_fee = st.sidebar.number_input("Target Fee (%)", value=2.0, format="%.2f")

# --- Main Interface: Input Table ---
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
    # --- 1. DATA PROCESSING (NUMERIC) ---
    proc_df = edited_df.copy()
    proc_df["Hashrate (TH/s)"] = pd.to_numeric(proc_df["Hashrate (TH/s)"])
    proc_df["Power (W)"] = pd.to_numeric(proc_df["Power (W)"])
    proc_df["display_name"] = proc_df["Model"] + " (" + proc_df["Profile"] + ")"

    # Efficiency
    proc_df["Efficiency (J/TH)"] = proc_df.apply(lambda x: x["Power (W)"]/x["Hashrate (TH/s)"] if x["Hashrate (TH/s)"] > 0 else 0, axis=1)

    # Sidebar Baseline Selector
    st.sidebar.markdown("---")
    st.sidebar.header("3. Baseline Selection")
    model_options = proc_df["display_name"].tolist()
    global_baseline_name = st.sidebar.selectbox("Global Baseline", options=model_options)

    # Financials Calculation
    hashprice_per_th = hashprice / 1000
    proc_df["Rev/Miner ($)"] = proc_df["Hashrate (TH/s)"] * hashprice_per_th
    
    # Calculate Cost (Apply Baseline Fee to Baseline machine, Target fee to others)
    daily_power = (proc_df["Power (W)"] / 1000) * 24 * power_price
    
    def get_fee(row):
        return baseline_fee if row["display_name"] == global_baseline_name else target_fee

    proc_df["Applied Fee (%)"] = proc_df.apply(get_fee, axis=1)
    proc_df["Fee Cost ($)"] = proc_df["Rev/Miner ($)"] * (proc_df["Applied Fee (%)"] / 100)
    proc_df["Cost/Miner ($)"] = daily_power + proc_df["Fee Cost ($)"]
    proc_df["Profit/Miner ($)"] = proc_df["Rev/Miner ($)"] - proc_df["Cost/Miner ($)"]
    proc_df["Fleet Profit ($)"] = proc_df["Profit/Miner ($)"] * fleet_size

    # --- 2. GLOBAL COMPARISON DISPLAY ---
    st.divider()
    st.subheader("4. Global Results")
    st.caption(f"All values below are compared against global baseline: **{global_baseline_name}**")

    # Get Global Baseline Row (Numeric)
    global_base_row = proc_df[proc_df["display_name"] == global_baseline_name].iloc[0]

    # Helper to format "Value (+Diff)"
    def fmt_stat(val, base, is_money=False):
        diff = val - base
        # Format string
        f_val = f"${val:,.2f}" if is_money else f"{val:,.1f}"
        if abs(diff) < 0.001: return f_val # No diff
        
        sign = "+" if diff > 0 else ""
        f_diff = f"{sign}${diff:,.2f}" if is_money else f"{sign}{diff:,.1f}"
        return f"{f_val} ({f_diff})"

    # Create Display DF (String formatted)
    display_df = pd.DataFrame()
    display_df["Model"] = proc_df["Model"]
    display_df["Profile"] = proc_df["Profile"]
    display_df["Hashrate"] = proc_df["Hashrate (TH/s)"].apply(lambda x: fmt_stat(x, global_base_row["Hashrate (TH/s)"]))
    display_df["Power"] = proc_df["Power (W)"].apply(lambda x: fmt_stat(x, global_base_row["Power (W)"]))
    display_df["Efficiency"] = proc_df["Efficiency (J/TH)"].apply(lambda x: fmt_stat(x, global_base_row["Efficiency (J/TH)"]))
    display_df["Rev/Miner"] = proc_df["Rev/Miner ($)"].apply(lambda x: fmt_stat(x, global_base_row["Rev/Miner ($)"], True))
    display_df["Profit/Miner"] = proc_df["Profit/Miner ($)"].apply(lambda x: fmt_stat(x, global_base_row["Profit/Miner ($)"], True))
    display_df["Fleet Profit"] = proc_df["Fleet Profit ($)"].apply(lambda x: fmt_stat(x, global_base_row["Fleet Profit ($)"], True))

    # Show Table with Selection
    selection = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row"
    )

    # --- 3. SPECIFIC COMPARISON (PEER TO PEER) ---
    selected_indices = selection.selection.rows
    
    if len(selected_indices) == 2:
        st.divider()
        st.subheader("⚖️ Peer-to-Peer Comparison")
        
        # Get the two selected rows from the NUMERIC dataframe (proc_df)
        row_a = proc_df.iloc[selected_indices[0]]
        row_b = proc_df.iloc[selected_indices[1]]
        
        col_comp_1, col_comp_2 = st.columns(2)
        with col_comp_1:
            st.info(f"**Baseline (A):** {row_a['display_name']}")
        with col_comp_2:
            st.success(f"**Target (B):** {row_b['display_name']}")

        # Build Comparison Data
        metrics = [
            ("Hashrate (TH/s)", "higher"),
            ("Power (W)", "lower"),
            ("Efficiency (J/TH)", "lower"),
            ("Profit/Miner ($)", "higher"),
            ("Fleet Profit ($)", "higher")
        ]
        
        comp_rows = []
        for metric, better in metrics:
            val_a = row_a[metric]
            val_b = row_b[metric]
            diff = val_b - val_a
            
            # Color Logic
            is_good = (diff > 0 and better == "higher") or (diff < 0 and better == "lower")
            color = "green" if is_good else "red"
            if abs(diff) < 0.001: color = "gray"
            
            comp_rows.append({
                "Metric": metric,
                "Baseline (A)": val_a,
                "Target (B)": val_b,
                "Difference": f":{color}[{diff:+.2f}]"
            })
            
        st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
        
    elif len(selected_indices) > 2:
        st.warning("Please select exactly 2 rows to enable Peer-to-Peer comparison.")

    # --- EXCEL EXPORT ---
    st.divider()
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        proc_df.to_excel(writer, sheet_name='Model Data', index=False)
    
    st.download_button("📥 Download Excel", data=buffer.getvalue(), file_name="mining_model.xlsx")

else:
    st.warning("Add data to start.")
