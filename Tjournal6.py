import streamlit as st
import pandas as pd
import sqlite3

# ----------------------
# DATABASE SETUP
# ----------------------
conn = sqlite3.connect("trading_journal.db", check_same_thread=False)
c = conn.cursor()

# Trades table
c.execute('''
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    entry_time TEXT,
    exit_time TEXT,
    qty INTEGER,
    entry_price REAL,
    exit_price REAL,
    pnl REAL,
    UNIQUE(symbol, entry_time, exit_time, entry_price, exit_price)
)
''')

# Journal table (with VIX)
c.execute('''
CREATE TABLE IF NOT EXISTS journal (
    trade_id INTEGER PRIMARY KEY,
    vix REAL,
    setup TEXT,
    planned_entry REAL,
    sl REAL,
    target REAL,
    logic TEXT,
    rr REAL,
    position_size INTEGER,
    entry_quality TEXT,
    exit_type TEXT,
    rules_followed TEXT,
    emotion_before TEXT,
    emotion_during TEXT,
    emotion_after TEXT,
    confidence INTEGER
)
''')

conn.commit()

# ----------------------
# FUNCTIONS
# ----------------------
def process_trade_file(file):
    df = pd.read_csv(file, header=None)

    df = df.rename(columns={
        7: "symbol",
        12: "side",
        13: "qty",
        14: "price",
        19: "time"
    })

    df["symbol"] = df["symbol"].str.strip()
    df["side"] = df["side"].astype(int)
    df["qty"] = df["qty"].astype(int)
    df["price"] = df["price"].astype(float)
    df["time"] = pd.to_datetime(df["time"])

    df = df.sort_values("time")

    trades = []
    positions = {}

    for _, row in df.iterrows():
        sym = row["symbol"]
        side = row["side"]
        qty = row["qty"]
        price = row["price"]
        time = row["time"]

        if sym not in positions:
            positions[sym] = []

        if side == 1:
            positions[sym].append({
                "qty": qty,
                "price": price,
                "time": time
            })
        else:
            remaining = qty
            while remaining > 0 and positions[sym]:
                buy = positions[sym][0]
                matched_qty = min(remaining, buy["qty"])

                pnl = (price - buy["price"]) * matched_qty

                trades.append({
                    "symbol": sym,
                    "entry_time": buy["time"],
                    "exit_time": time,
                    "qty": matched_qty,
                    "entry_price": buy["price"],
                    "exit_price": price,
                    "pnl": pnl
                })

                buy["qty"] -= matched_qty
                remaining -= matched_qty

                if buy["qty"] == 0:
                    positions[sym].pop(0)

    return pd.DataFrame(trades)


def insert_trades(df):
    for _, row in df.iterrows():
        try:
            c.execute('''
                INSERT INTO trades 
                (symbol, entry_time, exit_time, qty, entry_price, exit_price, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                row.symbol,
                str(row.entry_time),
                str(row.exit_time),
                row.qty,
                row.entry_price,
                row.exit_price,
                row.pnl
            ))
        except:
            pass
    conn.commit()


# ----------------------
# UI
# ----------------------
st.title("📊 Trading Journal Dashboard")

with st.sidebar:
    st.markdown("## 👨‍💻 Author")
    st.markdown("""
    **Sohil Dabhi**  
    📊 Trading Journal System  
    
    📧 sohil.dabhi@gmail.com  
      
    """)

# Upload Section
st.header("Upload Trade File")
file = st.file_uploader("Upload broker file", type=["csv", "txt"])

if file:
    df = process_trade_file(file)
    st.write("Preview:", df.head())

    if st.button("Save Trades"):
        insert_trades(df)
        st.success("Trades saved (duplicates ignored)")

# Load trades
trades_df = pd.read_sql("SELECT * FROM trades", conn)


# Merge trades + journal
journal_df = pd.read_sql("SELECT * FROM journal", conn)

full_df = trades_df.merge(
    journal_df,
    left_on="id",
    right_on="trade_id",
    how="left"
)

if not trades_df.empty:

    # Convert time + add week
    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"])
    trades_df["year"] = trades_df["entry_time"].dt.year
    trades_df["month"] = trades_df["entry_time"].dt.month
    trades_df["month_name"] = trades_df["entry_time"].dt.strftime("%b")  # Jan, Feb...
    trades_df["week"] = trades_df["entry_time"].dt.day.apply(lambda x: (x - 1) // 7 + 1)

    # ----------------------
    # PERFORMANCE
    # ----------------------
    st.header("📈 Performance")

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Trades", len(trades_df))
    col2.metric("Total PnL", round(trades_df.pnl.sum(), 2))
    col3.metric("Win Rate %", round((trades_df.pnl > 0).mean() * 100, 2))

    st.line_chart(trades_df.pnl.cumsum())

    # ----------------------
    # JOURNAL UI
    # ----------------------
    st.header("⚡ Quick Journal Entry")

    
    # ----------------------
    # MULTI-STEP TRADE SELECTION
    # ----------------------

    # Step 1: Select Year
   
    selected_year = st.selectbox(
        "Select Year",
        sorted(trades_df["year"].unique()),
        key="year_select"
    )


    df_year = trades_df[trades_df["year"] == selected_year]

    # Step 2: Select Month
    month_options = df_year[["month", "month_name"]].drop_duplicates().sort_values("month")
    month_dict = dict(zip(month_options["month_name"], month_options["month"]))

    
    selected_month_name = st.selectbox(
        "Select Month",
        list(month_dict.keys()),
        key="month_select"
    )
        
    
    selected_month = month_dict[selected_month_name]

    df_month = df_year[df_year["month"] == selected_month]

    # Step 3: Select Week
    selected_week = st.selectbox(
        "Select Week",
        sorted(df_month["week"].unique()),
        key="week_select"
    )
    
   
    df_week = df_month[df_month["week"] == selected_week]
    
    if df_week.empty:
        st.warning("No trades found for this filter")
        st.stop()

    # Step 4: Select Trade
    
    # ----------------------
    # ELITE SELECTION UI
    # ----------------------

    # 🔍 Search
    search = st.text_input("🔍 Search (symbol / strike / CE / PE)")

    if search:
        df_week = df_week[df_week["symbol"].str.contains(search, case=False, na=False)]

    # 🔽 Sorting
    sort_option = st.selectbox(
        "Sort Trades By",
        ["Time", "PnL High → Low", "PnL Low → High"]
    )

    if sort_option == "PnL High → Low":
        df_week = df_week.sort_values("pnl", ascending=False)
    elif sort_option == "PnL Low → High":
        df_week = df_week.sort_values("pnl", ascending=True)
    else:
        df_week = df_week.sort_values("entry_time")

    # 📊 Preview table (VERY useful)
    st.dataframe(
        df_week[["id", "symbol", "entry_time", "pnl"]],
        use_container_width=True
    )

    # 🎯 Color-coded trade selection
    # 🎯 Color formatting
    def format_trade(row):
        pnl = round(row["pnl"], 2)

        if pnl > 0:
            return f"🟢 {row['id']} | {row['symbol']} | +{pnl}"
        elif pnl < 0:
            return f"🔴 {row['id']} | {row['symbol']} | {pnl}"
        else:
            return f"⚪ {row['id']} | {row['symbol']} | {pnl}"

    # 🔗 Create mapping (IMPORTANT)
    options = {
        format_trade(row): row["id"]
        for _, row in df_week.iterrows()
    }

    # ✅ Selectbox (with key)
    selected_trade = st.selectbox(
        "Select Trade",
        list(options.keys()),
        key="trade_select"
    )

    # ✅ Get trade_id safely
    trade_id = options[selected_trade]
    
    

    # ✅ Show selected trade clearly
    selected_row = df_week[df_week["id"] == trade_id]

    if not selected_row.empty:
        st.success(
            f"Selected: {selected_row['symbol'].values[0]} | PnL: {round(selected_row['pnl'].values[0],2)}"
        )

    

    
    with st.expander("✍️ Fill Journal (simplified)", expanded=True):

        col1, col2 = st.columns(2)

        with col1:
            vix = st.number_input("VIX")
            setup = st.selectbox("Setup/Plan", ["Breakout", "Pullback", "Reversal"], key="setup")
            planned_entry = st.number_input("Planned Entry")
            sl = st.number_input("Stop Loss")
            target = st.number_input("Target")

        with col2:
            entry_quality = st.selectbox("Entry Quality", ["Early", "Perfect", "Late"], key="entry_quality")
            exit_type = st.selectbox("Exit Type", ["Target", "SL", "Early Exit"], key="exit_type")
            rules_followed = st.selectbox("Rules Followed", ["Yes", "No"], key="rules")
            confidence = st.slider("Confidence", 1, 10)

        logic = st.text_area("Logic")

        st.subheader("🧠 Mindset (Feelings/Emotions)")
        col3, col4, col5 = st.columns(3)

        with col3:
            emotion_before = st.selectbox("Before", ["Calm", "Fear", "Greed"], key="emo_before")
        with col4:
            emotion_during = st.selectbox("During", ["Calm", "Fear", "Greed"], key="emo_during")
        with col5:
            emotion_after = st.selectbox("After", ["Satisfied", "Regret"], key="emo_after")

        rr = (target - planned_entry) / (planned_entry - sl) if (planned_entry - sl) != 0 else 0
        position_size = trades_df[trades_df.id == trade_id]["qty"].values[0]

        st.info(f"Auto RR: {round(rr,2)} | Position Size: {position_size}")

        if st.button("💾 Save Journal"):
            c.execute('''
                REPLACE INTO journal VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                trade_id,
                vix,
                setup,
                planned_entry,
                sl,
                target,
                logic,
                rr,
                position_size,
                entry_quality,
                exit_type,
                rules_followed,
                emotion_before,
                emotion_during,
                emotion_after,
                confidence
            ))
            conn.commit()
            st.success("Journal saved / updated")

    st.header("📋 Trades Data")
    st.dataframe(trades_df)
    
    
    # ----------------------
    # EXPORT SECTION
    # ----------------------
    st.header("⬇️ Export Journal Data")

    # CSV export
    csv = full_df.to_csv(index=False).encode('utf-8')

    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name="trading_journal.csv",
        mime="text/csv"
    )

    # Excel export
    import io

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        full_df.to_excel(writer, index=False)

    excel_data = output.getvalue()

    st.download_button(
        label="📥 Download Excel",
        data=excel_data,
        file_name="trading_journal.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
st.markdown("---")
st.markdown("### 👨‍💻 Author")

st.markdown("""
**Name:** Sohil Dabhi  
**Project:** Trading Journal Dashboard  
**Version:** 1.0  

📧 Email: sohil.dabhi@gmail.com  

""")