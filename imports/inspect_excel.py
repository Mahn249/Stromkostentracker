from openpyxl import load_workbook

file_path = "historische_verbraeuche.xlsx"

workbook = load_workbook(
    filename=file_path,
    read_only=True,
    data_only=True,
)

print("Tabellenblätter:", workbook.sheetnames)

sheet = workbook.active

for row in sheet.iter_rows(min_row=1, max_row=6, values_only=True):
    print(row)

workbook.close()