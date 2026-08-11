import streamlit as st
import pandas as pd
import numpy as np


# ============================
# 页面设置
# ============================

st.set_page_config(
    page_title="用户电费测算工具",
    layout="wide"
)


st.title("⚡ 用户电费测算工具")


# ============================
# 文件读取
# ============================

period_file = "time.xlsx"
trade_file = "Tradingdata.xlsx"


period_df = pd.read_excel(
    period_file,
    sheet_name="Sheet1"
)


trade_df = pd.read_excel(
    trade_file,
    sheet_name="Sheet1"
)


# 时间格式统一
# period_df 的 "时点" 列已是 "HH:MM" 字符串，无需转换

trade_df["时间"] = (
    pd.to_datetime(
        trade_df["时间"].astype(str)
    )
    .dt.strftime("%H:%M")
)



# ============================
# 参数输入
# ============================

st.sidebar.header(
    "用户参数"
)


month = st.sidebar.selectbox(
    "账单月份",
    list(range(1,8))
)


price_type = st.sidebar.selectbox(
    "计价方式",
    [
        "单一制",
        "两部制（一般）",
        "两部制（大工业）",

    ]
)



jianfeng = st.sidebar.number_input(
    "尖峰电量(kWh)",
    min_value=0.0
)


feng = st.sidebar.number_input(
    "峰电量(kWh)",
    min_value=0.0
)


ping = st.sidebar.number_input(
    "平电量(kWh)",
    min_value=0.0
)


gu = st.sidebar.number_input(
    "谷电量(kWh)",
    min_value=0.0
)

shengu = st.sidebar.number_input(
    "深谷电量(kWh)",
    min_value=0.0
)

total_energy = (
    jianfeng+
    feng+
    ping+
    gu+
    shengu
)

# 保存用户输入的月度总电量，用于中长期合约电量计算
input_total_energy = total_energy



# ============================
# 生产时间
# ============================


time_list = [
    f"{h:02d}:{m:02d}"
    for h in range(24)
    for m in [0,15,30,45]
]


start_time = st.sidebar.selectbox(
    "开始生产时间",
    time_list,
    index=time_list.index("08:00")
)


end_time = st.sidebar.selectbox(
    "结束生产时间",
    time_list,
    index=time_list.index("18:00")
)



# ============================
# 获取生产时段
# ============================

def get_work_time(
    times,
    start,
    end
):

    s = times.index(start)

    e = times.index(end)


    if s < e:

        return times[s:e]

    else:

        return (
            times[s:]
            +
            times[:e]
        )


work_times = get_work_time(
    time_list,
    start_time,
    end_time
)



# ============================
# 构建日×时点负荷表
# ============================

# 从 time.xlsx 获取当月每日每时点的峰谷类型
month_period = period_df[period_df["月"] == month].copy()
month_period["类型"] = month_period[price_type]

# 统一类型标签：time.xlsx 使用 "平段"，代码使用 "平"
month_period["类型"] = month_period["类型"].replace({"平段": "平"})

# 获取当月天数（从 time.xlsx 取天数，与 Tradingdata 一致）
days_in_month = sorted(month_period["日"].unique())
n_days = len(days_in_month)

# 构建完整的日×时点负荷表
load_rows = []
for day in days_in_month:
    day_data = month_period[month_period["日"] == day]
    for t in time_list:
        match = day_data[day_data["时点"] == t]
        if len(match) > 0:
            ptype = match["类型"].iloc[0]
        else:
            # 兜底：若某时点缺失，默认设为 "平"
            ptype = "平"
        load_rows.append({"日": int(day), "时间": t, "类型": ptype})

load = pd.DataFrame(load_rows)


# ============================
# 分配尖峰平谷电量
# ============================

energy_dict = {
    "尖峰": jianfeng,
    "高峰": feng,
    "平": ping,
    "低谷": gu,
    "深谷": shengu
}

load["电量"] = 0.0

for p, e in energy_dict.items():
    mask = (
        load["时间"].isin(work_times)
        & (load["类型"] == p)
    )
    count = mask.sum()
    if count > 0:
        avg = e / count
        load.loc[mask, "电量"] = avg

# 更新总用电量为实际分配到各时点的电量之和
# （某些类型可能在选定工作时段内不存在，输入电量不会全部被分配）
total_energy = load["电量"].sum()

# 提示未分配的电量
unassigned = {}
for p, e in energy_dict.items():
    mask = (
        load["时间"].isin(work_times)
        & (load["类型"] == p)
    )
    if mask.sum() == 0 and e > 0:
        unassigned[p] = e

if unassigned:
    unassigned_list = "、".join(
        [f"{p}({v:.0f}kWh)" for p, v in unassigned.items()]
    )
    st.sidebar.warning(
        f"⚠️ 以下类型在选定工作时段内没有对应时段，"
        f"电量未被分配：{unassigned_list}"
    )



# ============================
# 展示96点负荷
# ============================


st.subheader(
    "用户96点分时电量（按日展开）"
)


st.dataframe(
    load[
        [
            "日",
            "时间",
            "类型",
            "电量"
        ]
    ],
    height=500
)



# ============================
# 匹配交易数据（按日匹配）
# ============================


# 筛选当月交易数据，提取日期中的"日"用于匹配
trade_month = (
    trade_df[
        trade_df["月份"] == month
    ]
    .copy()
)

trade_month["日"] = trade_month["日期"].dt.day

# 按 (日, 时间) 合并负荷与交易数据
result = load.merge(
    trade_month[
        [
            "日", "时间",
            "中长期曲线", "中长期均价", "现货均价"
        ]
    ],
    on=["日", "时间"],
    how="left"
)



# ============================
# 中长期电量（每日每点计算）
# ============================

# 中长期电量 = 月度总用电量 × 80% × 中长期曲线（每点曲线值直接使用，不汇总）
result["中长期电量"] = (
    input_total_energy
    * 0.8
    * result["中长期曲线"]
)

# 现货电量 = 每点实际电量 - 每点中长期电量（负值=向现货市场售出多余合约电量）
result["现货电量"] = (
    result["电量"]
    -
    result["中长期电量"]
)



# ============================
# 电费计算（按日加权）
# ============================


lt_energy = (
    result["中长期电量"]
    .sum()
)

# 中长期电费 = sum(每日每点 中长期电量 * 中长期均价)
lt_cost = (
    result["中长期电量"]
    * result["中长期均价"]
).sum()

# 现货电费 = sum(每日每点 现货电量 * 现货均价)
spot_cost = (
    result["现货电量"]
    * result["现货均价"]
).sum()


total_cost = (
    lt_cost+
    spot_cost
)



avg_price = (
    total_cost/
    total_energy
    if total_energy>0
    else 0
)



# ============================
# 输出结果
# ============================


summary=pd.DataFrame(
    {
        "月份":[month],
        "总用电量(kWh)":[total_energy],
        "中长期电量(kWh)":[lt_energy],
        "现货电量(kWh)":[
            result["现货电量"].sum()
        ],
        "电费(元)":[total_cost],
        "均价(元/kWh)":[avg_price/1000]
    }
)



st.subheader(
    "测算结果"
)


st.dataframe(
    summary
)



# ============================
# 曲线展示
# ============================


st.subheader(
    "用户负荷曲线"
)


st.line_chart(
    result.groupby("时间")
    ["电量"]
    .first()
)


st.subheader(
    "现货价格曲线"
)


st.line_chart(
    result.groupby("时间")
    ["现货均价"]
    .mean()
)



# ============================
# 明细下载
# ============================


csv = result.to_csv(
    index=False,
    encoding="utf-8-sig"
)


st.download_button(
    "下载测算明细",
    csv,
    "用户电费测算.csv"
)
