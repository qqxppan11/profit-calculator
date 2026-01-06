import streamlit as st
import pandas as pd

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
        "Hashrate (TH/s)": st.column_config.NumberColumn(
            min_value=0, 
            step=0.1, 
            format="%.2f"
        ),
        # UPDATED: Power now accepts decimals
        "Power (W)": st.column_config.NumberColumn(
            min_value=0, 
            step=0.1, 
            format="%.1f" # Display 1 decimal place (e.g. 3010.5)
        ),
        "Model": st.column_config.TextColumn(required=True),
        "Profile": st.column_config.TextColumn()
    }
)

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

    # Rounding
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
            "Power (W)": st.column_config.NumberColumn(format="%.1f W") # Display format in results too
        }
    )

    # --- Comparison Logic ---
    selected_rows = selection.selection.rows
    
    if len(selected_rows) == 2:
        st.divider()
        st.subheader("⚖️ Comparison Mode")
        
        # Helper to get row name for dropdown
        def get_row_name(idx):
            # Safe access in case index is out of bounds
            if idx < len(display_df):
                r = display_df.iloc[idx]
                return f"{r['Model']} ({r['Profile']})"
            return "Unknown"

        # 1. Comparison Selectors
        col_sel_a, col_sel_b = st.columns(2)
        
        # Default: First selected is Baseline, Second is Target
        options_map = {idx: get_row_name(idx) for idx in selected_rows}
        
        with col_sel_a:
            idx_a = st.selectbox("Select Baseline (A)", options=selected_rows, format_func=lambda x: options_map.get(x, "Unknown"), key="a")
        with col_sel_b:
            default_b = selected_rows[1] if len(selected_rows) > 1 and idx_a == selected_rows[0] else selected_rows[0]
            # Ensure default_b is in selected_rows
            if default_b not in selected_rows: default_b = selected_rows[0]
                
            idx_b = st.selectbox("Select Target (B)", options=selected_rows, format_func=lambda x: options_map.get(x, "Unknown"), index=selected_rows.index(default_b), key="b")

        # 2. Extract Data
        row_a = display_df.iloc[idx_a]
        row_b = display_df.iloc[idx_b]

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
        
        comp_data = []
        
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
            
            # Determine Color Logic
            # Green if: (Higher is better AND diff > 0) OR (Lower is better AND diff < 0)
            is_positive_outcome = (is_higher_better and diff > 0) or (not is_higher_better and diff < 0)
            is_neutral = (diff == 0)

            if is_neutral:
                color = "gray"
            elif is_positive_outcome:
                color = "green"
            else:
                color = "red"

            # Format strings with colors for Streamlit Markdown
            diff_str = f"{diff:+.2f}"
            pct_str = f"{pct_diff:+.2f}%"
            
            colored_diff = f":{color}[{diff_str}]"
            colored_pct = f":{color}[{pct_str}]"
            
            comp_data.append({
                "Metric": metric,
                "Baseline (A)": val_a,
                "Target (B)": val_b,
                "Difference": colored_diff,
                "% Change": colored_pct
            })
            
        # 4. Render Table
        comp_df = pd.DataFrame(comp_data)
        
        # We use st.markdown to render the dataframe so the :green[] syntax works
        st.markdown(
            comp_df.to_markdown(index=False), 
            unsafe_allow_html=True
        )
        st.caption(f"Comparing **{options_map[idx_b]}** against baseline **{options_map[idx_a]}**")
            
    elif len(selected_rows) > 2:
        st.warning("Please select exactly 2 rows to compare.")
    
    # --- Export ---
    st.divider()
    csv = display_df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download CSV", data=csv, file_name="mining_calc.csv", mime="text/csv")

else:
    st.warning("Please add data to the table.")