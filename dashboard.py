import streamlit as st
import pandas as pd
import plotly.express as px
from analyzer import analyze
from io import StringIO
import datetime
import tempfile
import os


st.set_page_config(page_title="Анализ банковских выписок", layout="wide")

@st.cache_data
def cached_analyze(file_paths):
    return analyze(file_paths)

uploaded_files = st.file_uploader("Загрузите PDF банковских выписок", type="pdf", accept_multiple_files=True)

file_paths = []
if uploaded_files:
    temp_dir = tempfile.mkdtemp()
    for uploaded_file in uploaded_files:
        temp_path = os.path.join(temp_dir, uploaded_file.name)
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        file_paths.append(temp_path)
else:
    # Use existing PDFs from 'pdfs' folder
    pdf_folder = "pdfs"
    if os.path.exists(pdf_folder):
        file_paths = [os.path.join(pdf_folder, f) for f in os.listdir(pdf_folder) if f.lower().endswith(".pdf")]

df, summary = cached_analyze(file_paths)

# Преобразование типов
if df is not None and "amount" in df.columns:
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
if df is not None and "date" in df.columns:
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
if summary is not None and "amount" in summary.columns:
    summary["amount"] = pd.to_numeric(summary["amount"], errors="coerce")
if summary is not None:
    summary = summary.sort_values(by="amount", ascending=False)

if df is None:
    st.warning("Нет данных для анализа. Загрузите PDF банковских выписок.")
else:
    st.header("Анализ банковских выписок")

    # --- DATE FILTER (in main page) ---
    min_date = df["date"].min()
    max_date = df["date"].max()
    date_range = st.date_input(
        "Диапазон дат",
        value=(min_date.date() if pd.notnull(min_date) else datetime.date.today(),
               max_date.date() if pd.notnull(max_date) else datetime.date.today()),
        min_value=min_date.date() if pd.notnull(min_date) else datetime.date.today(),
        max_value=max_date.date() if pd.notnull(max_date) else datetime.date.today()
    )

    # --- APPLY FILTERS ---
    filtered_df = df.copy()
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        filtered_df = filtered_df[
            (filtered_df["date"] >= pd.to_datetime(start_date)) &
            (filtered_df["date"] <= pd.to_datetime(end_date))
        ]

    # --- SUMMARY STATISTICS ---
    st.subheader("Статистика")

    # Берём суммы по категориям из полного DataFrame df
    summary_by_category_full = df.groupby("category", as_index=False)["amount"].sum()
    
    total_replenishments = summary_by_category_full.loc[summary_by_category_full["category"] == "Пополнения", "amount"].sum()
    total_expenses = summary_by_category_full.loc[summary_by_category_full["category"] == "Списания", "amount"].sum()
    

    col1, col2 = st.columns(2)
    col1.metric("Пополнения", f"{int(round(total_replenishments)):,}".replace(",", " "))
    col2.metric("Списания", f"{int(round(abs(total_expenses))):,}".replace(",", " "))

    # --- CHARTS ---
    st.subheader("Визуализация расходов")
    chart_type = st.radio(
        "Тип графика",
        ("Круговая диаграмма", "Гистограмма по месяцам", "Тренд по категориям"),
        horizontal=True
    )

    # Для графиков нужна агрегированная/группированная таблица
    filtered_summary = (
        filtered_df.groupby("category", as_index=False)["amount"].sum()
        .sort_values(by="amount", ascending=False)
    )

    if chart_type == "Круговая диаграмма":
        fig_pie = px.pie(filtered_summary, names="category", values="amount", title="Распределение расходов по категориям")
        st.plotly_chart(fig_pie, use_container_width=True)
    elif chart_type == "Гистограмма по месяцам":
        filtered_df["year_month"] = filtered_df["date"].dt.to_period("M").astype(str)
        monthly = (
            filtered_df.groupby("year_month", as_index=False)["amount"].sum()
            .sort_values(by="year_month")
        )
        fig_bar = px.bar(monthly, x="year_month", y="amount", labels={"year_month": "Месяц", "amount": "Сумма"},
                         title="Гистограмма расходов по месяцам")
        st.plotly_chart(fig_bar, use_container_width=True)
    elif chart_type == "Тренд по категориям":
        filtered_df["year_month"] = filtered_df["date"].dt.to_period("M").astype(str)
        trend = (
            filtered_df.groupby(["year_month", "category"], as_index=False)["amount"].sum()
            .sort_values(by=["year_month", "category"])
        )
        fig_line = px.line(
            trend,
            x="year_month",
            y="amount",
            color="category",
            labels={"year_month": "Месяц", "amount": "Сумма", "category": "Категория"},
            title="Тренд расходов по категориям"
        )
        st.plotly_chart(fig_line, use_container_width=True)

    # --- DETAIL TABLE ---
    st.subheader("Детализация")
    # Фильтр по категориям для таблицы детализации
    categories = ["Все"] + sorted(filtered_df["category"].dropna().unique().tolist())
    selected_category = st.selectbox("Фильтр по категории (для таблицы детализации)", categories)
    detail_df = filtered_df.copy()
    if selected_category != "Все":
        detail_df = detail_df[detail_df["category"] == selected_category]

    # Стилизация: выделение больших расходов
    # highlight_threshold = detail_df["amount"].quantile(0.95) if not detail_df.empty else None
    # def highlight_large(val):
    #     try:
    #         v = float(val)
    #         if highlight_threshold is not None and v >= highlight_threshold:
    #             return "background-color: #ffcccc; color: #800000;"
    #     except:
    #         pass
    #     return ""

    detail_df = detail_df.sort_values(by="date", ascending=False)
    # Преобразуем дату в формат dd.mm.yyyy для отображения
    detail_df["date"] = detail_df["date"].dt.strftime("%d.%m.%Y")
    detail_df = detail_df.drop(columns=["currency"], errors="ignore")
    # Переименование и перестановка колонок
    rename_map = {
        "date": "Дата",
        "description": "Описание",
        "amount": "Сумма",
        "details": "Детали",
    }
    columns_order = ["Дата", "Сумма", "Описание", "Детали"]
    detail_df = detail_df.rename(columns=rename_map)
    # Собираем только нужные колонки
    detail_df = detail_df[[c for c in columns_order if c in detail_df.columns]]
    # Стилизация с форматированием суммы
    styled = detail_df.style.format({"Сумма": "{:,.0f}"})
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
    )

    # --- DOWNLOAD BUTTON ---
    csv_buffer = StringIO()
    detail_df.to_csv(csv_buffer, index=False, encoding="utf-8-sig", sep=";")
    st.download_button(
        label="Скачать таблицу в CSV",
        data=csv_buffer.getvalue(),
        file_name="bank_analyzer_export.csv",
        mime="text/csv"
    )

    # --- SUMMARY TABLE BY CATEGORY ---
    st.subheader("Суммы по категориям")
    summary_filtered = (
        filtered_df.groupby("category", as_index=False)["amount"].sum()
        .sort_values(by="amount", ascending=False)
    )
    summary_filtered = summary_filtered.rename(columns={"category": "Категория", "amount": "Сумма"})
    styled_summary = summary_filtered.style.format({"Сумма": "{:,.0f}"})
    st.dataframe(
        styled_summary,
        use_container_width=True,
        hide_index=True,
    )

    # client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # st.subheader("Рекомендации ChatGPT")
    # if not filtered_df.empty:
    #     prompt = f"Вот банковские транзакции: {filtered_df.to_dict(orient='records')}. Дай рекомендации по бюджету и выяви необычные расходы."
    #     response = client.chat.completions.create(
    #         model="gpt-4.1-mini",
    #         messages=[{"role": "user", "content": prompt}]
    #     )
    #     st.write(response.choices[0].message["content"])
    # else:
    #     st.info("Нет данных для анализа рекомендаций.")