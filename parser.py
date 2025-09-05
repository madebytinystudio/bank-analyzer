import re
import pdfplumber
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
    # Try common date formats
    for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d %m %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            continue
    # Try to parse with regex for numbers only and assume DDMMYYYY or similar
    digits = re.sub(r"[^\d]", "", date_str)
    if len(digits) == 8:
        try:
            dt = datetime.strptime(digits, "%d%m%Y")
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            pass
    return date_str  # fallback: return original if can't parse

def parse_pdf(file_path: str, categories: dict):
    rows = []
    saved_indices = None  # сохраняем индексы колонок после первой страницы

    def looks_like_headers(row):
        if not row:
            return False
        text = " ".join([c or "" for c in row]).lower()
        # если нет даты и суммы, считаем строку частью шапки
        return not re.search(r"\d{2}[./-]\d{2}[./-]\d{2,4}", text) and "₸" not in text and not re.search(r"[+-]?\d[\d\s,.]*", text)
    
    def looks_like_transaction(row):
        if not row:
            return False
        text = " ".join([c or "" for c in row]).lower()
        return re.search(r"\d{2}[./-]\d{2}[./-]\d{2,4}", text) or "₸" in text or re.search(r"[+-]?\d[\d\s,.]*", text)

    with pdfplumber.open(file_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            table_settings = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
                "join_tolerance": 3,
                "intersection_tolerance": 3,
                "edge_min_length": 3,
                "min_words_vertical": 1,
                "min_words_horizontal": 1,
            }
            tables = page.extract_tables(table_settings=table_settings)
            print(f"Страница {page_number}: найдено {len(tables)} таблиц")
            if not tables:
                print(f"Страница {page_number}: таблиц не найдено")
                continue

            for table_number, table in enumerate(tables, start=1):
                print(f"  Таблица {table_number}: {len(table)} строк, {len(table[0]) if table and table[0] else 0} колонок")
                if not table or not table[0]:
                    continue

                raw_headers = table[0]

                if looks_like_transaction(raw_headers) and saved_indices is not None:
                    headers = None
                    data_rows = table
                    idx_date = saved_indices.get("date")
                    idx_desc = saved_indices.get("desc")
                    idx_amount = saved_indices.get("amount")
                    idx_currency = saved_indices.get("currency")
                    idx_details = saved_indices.get("details")
                else:
                    if len(table) > 1 and looks_like_headers(table[1]):
                        combined = []
                        for i in range(len(raw_headers)):
                            h1 = raw_headers[i] or ""
                            h2 = table[1][i] or ""
                            combined.append((h1 + " " + h2).replace("\n", " ").strip().lower())
                        headers = combined
                        data_rows = table[2:]
                    else:
                        headers = [h.replace("\n", " ").strip().lower() if h else "" for h in raw_headers]
                        data_rows = table[1:]

                    idx_date = idx_desc = idx_amount = idx_currency = idx_details = None

                    if headers and any(headers):  # определяем индексы только если есть заголовки
                        for i, header_lower in enumerate(headers):
                            if any(h.lower() in header_lower for h in column_map["date"]):
                                idx_date = i
                            elif any(h.lower() in header_lower for h in column_map["description"]):
                                idx_desc = i
                            elif any(h.lower() in header_lower for h in column_map["amount"]):
                                idx_amount = i
                            elif any(h.lower() in header_lower for h in column_map["currency"]):
                                idx_currency = i
                            elif any(h.lower() in header_lower for h in column_map["details"]):
                                idx_details = i
                        saved_indices = {
                            "date": idx_date,
                            "desc": idx_desc,
                            "amount": idx_amount,
                            "currency": idx_currency,
                            "details": idx_details
                        }
                    else:  # если заголовков нет, используем сохранённые индексы
                        print(f"    Нет заголовков, используем сохранённые индексы: {saved_indices}")
                        if saved_indices is None:
                            print(f"Страница {page_number}, таблица {table_number}: пропущена, нет заголовков и сохранённых индексов")
                            continue
                        idx_date = saved_indices.get("date")
                        idx_desc = saved_indices.get("desc")
                        idx_amount = saved_indices.get("amount")
                        idx_currency = saved_indices.get("currency")
                        idx_details = saved_indices.get("details")

                if idx_date is None or idx_desc is None or idx_amount is None:
                    print(f"Страница {page_number}, таблица {table_number}: пропущена, нет обязательных колонок")
                    print(f"    Индексы: date={idx_date}, desc={idx_desc}, amount={idx_amount}")
                    continue

                for row in data_rows:
                    if row is None or len(row) <= max(idx_date, idx_desc, idx_amount):
                        continue

                    date_raw = row[idx_date]
                    desc = row[idx_desc]
                    amount_str = row[idx_amount]
                    if date_raw is None or desc is None or amount_str is None:
                        continue

                    date = normalize_date(date_raw)
                    amount_str = amount_str.replace("₸", "")
                    matches = re.findall(r"[+-]?\d[\d\s,.]*", amount_str)
                    if matches:
                        try:
                            normalized = matches[0].replace(" ", "").replace("\u00A0", "")
                            if "," in normalized and "." in normalized:
                                normalized = normalized.replace(",", "")
                            elif "," in normalized and "." not in normalized:
                                normalized = normalized.replace(",", ".")
                            amount = round(abs(float(normalized)))
                        except ValueError:
                            amount = None
                    else:
                        amount = None

                    full_text = desc or ""
                    if idx_details is not None and len(row) > idx_details:
                        details = row[idx_details]
                        if details:
                            full_text += " " + details

                    entry = {
                        "date": date,
                        "description": desc.strip(),
                        "amount": amount,
                        "category": categorize(full_text.strip(), categories)
                    }

                    if idx_currency is not None and len(row) > idx_currency:
                        currency = row[idx_currency]
                        if currency:
                            entry["currency"] = currency
                    if idx_details is not None and len(row) > idx_details:
                        details = row[idx_details]
                        if details:
                            entry["details"] = details

                    rows.append(entry)

    # Суммы по категориям
    from collections import defaultdict
    totals = defaultdict(float)
    for r in rows:
        if r.get("amount") is not None:
            totals[r["category"]] += r["amount"]

    print("\nСуммы по категориям:")
    for cat, total in totals.items():
        print(f"{cat}: {total:,.2f}")

    return rows