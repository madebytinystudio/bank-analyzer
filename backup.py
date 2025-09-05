
import re
import camelot
import pandas as pd
import json
from collections import defaultdict
from datetime import datetime

column_map = {
    "date": ["Дата", "Date"],
    "amount": ["Сумма", "Amount"],
    "currency": ["Валюта", "Transaction currency"],
    "description": ["Описание", "Description", "Операция", "Operation"],
    "details": ["Детализация", "Детали", "Details"]   
}

def load_categories(file_path="categories.json"):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def categorize(description: str, categories: dict) -> str:
    desc = description.lower()
    for cat, keywords in categories.items():
        if any(k.lower() in desc for k in keywords):
            return cat
    return "Без категории"

def normalize_date(date_str: str) -> str:
    date_str = date_str.strip()
    for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d %m %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            continue
    digits = re.sub(r"[^\d]", "", date_str)
    if len(digits) == 8:
        try:
            dt = datetime.strptime(digits, "%d%m%Y")
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            pass
    return date_str

def parse_pdf(file_path: str, categories: dict):
    rows = []
    saved_indices = {}  # сохраняем индексы колонок после первой страницы

    # Пробуем сначала "lattice", если таблиц нет — переключаемся на "stream"
    tables = camelot.read_pdf(file_path, pages="all", flavor="lattice")
    if not tables or len(tables) == 0:
        print(f"Для файла {file_path} не найдено таблиц в режиме lattice, пробуем stream...")
        tables = camelot.read_pdf(file_path, pages="all", flavor="stream")

    print(f"Файл {file_path}: найдено {len(tables)} таблиц")

    for table_number, table in enumerate(tables, start=1):
        df = table.df
        print(f"\nТаблица {table_number}, первые 5 строк:")
        print(df.head(5))
        if df.empty:
            continue

        if not saved_indices:
            # проверяем первую строку как потенциальный заголовок
            headers = [str(h).strip().lower() for h in df.iloc[0]]
            found = False
            for i, h in enumerate(headers):
                if any(x.lower() in h for x in column_map["date"]):
                    saved_indices["date"] = i
                    found = True
                elif any(x.lower() in h for x in column_map["amount"]):
                    saved_indices["amount"] = i
                    found = True
                elif any(x.lower() in h for x in column_map["description"]):
                    saved_indices["desc"] = i
                    found = True
                elif any(x.lower() in h for x in column_map["currency"]):
                    saved_indices["currency"] = i
                    found = True
                elif any(x.lower() in h for x in column_map["details"]):
                    saved_indices["details"] = i
                    found = True

            if found:
                # если таблица действительно с нужными колонками — берём данные без заголовка
                data_rows = df.iloc[1:]
            else:
                continue  # таблица не содержит нужных колонок
        else:
            # все последующие таблицы после первой с заголовками обрабатываем целиком
            data_rows = df

        for _, row in data_rows.iterrows():
            row = row.fillna("")
            try:
                idx_date = saved_indices.get("date")
                idx_desc = saved_indices.get("desc")
                idx_amount = saved_indices.get("amount")
                idx_currency = saved_indices.get("currency")
                idx_details = saved_indices.get("details")

                if idx_date is None or idx_desc is None or idx_amount is None:
                    continue

                date_raw = row[idx_date]
                desc = row[idx_desc]
                amount_str = row[idx_amount]

                if date_raw is None or desc is None or amount_str is None:
                    continue

                date = normalize_date(date_raw)
                amount_str = str(amount_str).replace("₸", "").replace(" ", "")
                matches = re.findall(r"[+-]?\d[\d,.]*", amount_str)
                amount = None
                if matches:
                    try:
                        normalized = matches[0].replace(",", ".")
                        amount = round(abs(float(normalized)))
                    except ValueError:
                        pass

                details = ""
                if idx_details is not None and len(row) > idx_details:
                    details = str(row[idx_details]).strip()

                desc_val = str(desc).strip() if desc else None
                details_val = str(details).strip() if details else None

                entry = {
                    "date": date,
                    "description": desc_val,
                    "details": details_val,
                    "amount": amount,
                    "category": categorize(" ".join(filter(None, [desc_val, details_val])), categories)
                }

                if idx_currency is not None and len(row) > idx_currency:
                    currency = row[idx_currency]
                    if currency:
                        entry["currency"] = str(currency).strip()

                rows.append(entry)
            except Exception as e:
                print(f"Ошибка на таблице {table_number}: {e}")
                continue

    # Суммы по категориям
    totals = defaultdict(float)
    for r in rows:
        if r.get("amount") is not None:
            totals[r["category"]] += r["amount"]

    print("\nСуммы по категориям:")
    for cat, total in totals.items():
        print(f"{cat}: {total:,.2f}")

    # Сохранение в CSV
    df_result = pd.DataFrame(rows)
    df_result.to_csv("parsed_transactions.csv", index=False, encoding="utf-8-sig")
    print("Файл сохранён: parsed_transactions.csv")

    return rows