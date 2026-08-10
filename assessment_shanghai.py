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

period_df["开始时间"] = (
    pd.to_datetime(
        period_df["开始时间"].astype(str)
    )
    .dt.strftime("%H:%M")
)


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
        "两部制"
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



total_energy = (
    jianfeng+
    feng+
    ping+
    gu
)



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
# 生成96点负荷
# ============================


load = pd.DataFrame(
    {
        "时间":time_list
    }
)



# 匹配峰谷类型

period = period_df[
    (period_df["月份"]==month)
    &
    (period_df["计价方式"]==price_type)
]


load = load.merge(
    period[
        [
            "开始时间",
            "峰谷类型"
        ]
    ],
    left_on="时间",
    right_on="开始时间",
    how="left"
)


load.rename(
    columns={
        "峰谷类型":"类型"
    },
    inplace=True
)



# ============================
# 分配尖峰平谷电量
# ============================


energy_dict={

    "尖峰":
    jianfeng,

    "高峰":
    feng,

    "平":
    ping,

    "低谷":
    gu
}



load["电量"]=0.0



for p,e in energy_dict.items():


    count = len(
        load[
            (load["时间"].isin(work_times))
            &
            (load["类型"]==p)
        ]
    )


    if count>0:

        avg=e/count


        load.loc[
            (
                load["时间"].isin(work_times)
            )
            &
            (
                load["类型"]==p
            ),
            "电量"
        ]=avg



# ============================
# 展示96点负荷
# ============================


st.subheader(
    "用户96点分时电量"
)


st.dataframe(
    load[
        [
            "时间",
            "类型",
            "电量"
        ]
    ],
    height=500
)



# ============================
# 匹配交易数据（按日计算）
# ============================


# 筛选当月交易数据
trade_month = (
    trade_df[
        trade_df["月份"]==month
    ]
    .copy()
)

# 当月天数
n_days = trade_month["日期"].nunique()

# 月度96点电量均分到每日
load["日电量"] = load["电量"] / n_days

# 合并每日负荷与每日交易数据（按时间展开到日）
result = load[[
    "时间","类型","电量","日电量"
]].merge(
    trade_month[[
        "日期","时间",
        "中长期曲线","中长期均价","现货均价"
    ]],
    on="时间",
    how="left"
)



# ============================
# 中长期电量（每日每点计算）
# ============================


# 中长期电量 = (总电量/天数) * 0.8 * 每日中长期曲线
result["中长期电量"] = (
    (total_energy)
    * 0.8
    * result["中长期曲线"]
)

# 现货电量 = 日电量 - 中长期电量
result["现货电量"] = (
    result["日电量"]
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