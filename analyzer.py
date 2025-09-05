import os
import pandas as pd
from parser import parse_pdf, load_categories

def analyze(input_source="pdfs", output_file="report.xlsx", categories_file="categories.json"):
    """
    input_source: str (папка) или list (список файлов)
    """
    categories = load_categories(categories_file)
    all_rows = []

    # Преобразуем вход в список файлов
    if isinstance(input_source, str):
        # Папка
        files = [os.path.join(input_source, f) for f in os.listdir(input_source) if f.endswith(".pdf")]
    elif isinstance(input_source, list):
        # Список файлов
        files = [f for f in input_source if f.endswith(".pdf")]
    else:
        raise TypeError("input_source должен быть строкой (папка) или списком файлов.")

    for file_path in files:
        all_rows.extend(parse_pdf(file_path, categories))

    if not all_rows:
        print("Нет транзакций для анализа.")
        return None, None

    df = pd.DataFrame(all_rows)

    # Преобразуем даты в datetime с автоматическим определением формата
    df['date'] = pd.to_datetime(df['date'], dayfirst=True, errors='coerce', infer_datetime_format=True)

    # Удаляем строки, где дата не распознана
    df = df.dropna(subset=['date'])

    # Добавляем округление до минуты для удаления дубликатов
    df['minute'] = df['date'].dt.floor('T')
    df = df.drop_duplicates(subset=['minute', 'amount', 'description'], keep='first')
    df = df.drop(columns='minute')

    summary = df.groupby("category")["amount"].sum().reset_index()

    # Записываем в Excel
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Сводка", index=False)
        df.to_excel(writer, sheet_name="Детализация", index=False)

    print(f"Отчет сохранен в {output_file}")
    return df, summary

if __name__ == "__main__":
    analyze()