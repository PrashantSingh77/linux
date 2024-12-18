import os
import csv
import openpyxl
from openpyxl import Workbook
import win32com.client as win32
import random
import string

def generate_random_password(length=8):
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for i in range(length))

def convert_csv_to_excel(folder_path):
    output_folder = os.path.join(folder_path, 'output')
    os.makedirs(output_folder, exist_ok=True)

    # Open the password file in write mode to overwrite it
    password_file = os.path.join(output_folder, 'passwords.txt')
    with open(password_file, 'w') as file:
        file.write('')  # Clear the file content

    for filename in os.listdir(folder_path):
        if filename.endswith('.csv'):
            csv_file = os.path.join(folder_path, filename)
            excel_file = os.path.join(output_folder, f'{os.path.splitext(filename)[0]}.xlsx')

            workbook = Workbook()
            sheet = workbook.active

            with open(csv_file, 'r', encoding='utf-8') as file:
                reader = csv.reader(file)
                for row in reader:
                    sheet.append(row)

            # Save the Excel workbook
            workbook.save(excel_file)

            # Generate a random password for the workbook
            password = generate_random_password()

            # Set the password for the workbook using win32com
            excel = win32.Dispatch('Excel.Application')
            wb = excel.Workbooks.Open(excel_file)
            wb.Password = password
            wb.Save()
            wb.Close()
            excel.Quit()

            # Append the password to the text file
            with open(password_file, 'a') as file:
                file.write(f'{excel_file}: {password}\n')

    print('Conversion completed successfully.')

# Provide the folder path containing the CSV files
folder_path = r'C:\alikeys\test'  # Use raw string literal
convert_csv_to_excel(folder_path)