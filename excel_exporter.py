import io
from datetime import datetime
from typing import List, Dict, Any
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def export_transactions_to_excel(transactions: List[Dict[str, Any]]) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Операції"

    # Заголовки таблиці
    headers = ["ID", "Дата та час", "Тип", "Категорія", "Сума (грн)", "Опис"]
    ws.append(headers)

    # Стилі заголовків
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    # Заповнення даними
    green_font = Font(name="Calibri", size=11, color="008000")  # Зелений для доходу
    red_font = Font(name="Calibri", size=11, color="C00000")    # Червоний для витрати

    for row_idx, tx in enumerate(transactions, start=2):
        tx_type_str = "Витрата" if tx["type"] == "expense" else "Дохід"
        amount_val = tx["amount"]
        if tx["type"] == "expense":
            amount_val = -amount_val

        ws.append([
            tx["id"],
            tx["created_at"],
            tx_type_str,
            tx["category"],
            amount_val,
            tx.get("description", "")
        ])

        # Центруємо ID, Дату, Тип
        ws.cell(row=row_idx, column=1).alignment = center_align
        ws.cell(row=row_idx, column=2).alignment = center_align
        ws.cell(row=row_idx, column=3).alignment = center_align

        # Форматуємо суму
        amount_cell = ws.cell(row=row_idx, column=5)
        amount_cell.number_format = '#,##0.00 ₴'
        amount_cell.font = red_font if tx["type"] == "expense" else green_font
        amount_cell.alignment = Alignment(horizontal="right", vertical="center")

        # Додаємо легку рамку
        for col_idx in range(1, len(headers) + 1):
            ws.cell(row=row_idx, column=col_idx).border = thin_border

    # Автоматична ширина колонок
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

