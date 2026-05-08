import csv
import sys


def filter_zero_co_ppm_after_line(input_file: str, output_file: str, start_line: int = 58) -> None:
    """Copy input_file to output_file, dropping rows with co_ppm == 0.0 after start_line."""
    with open(input_file, 'r', newline='') as infile, open(output_file, 'w', newline='') as outfile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"CSV file {input_file} is empty or missing a header")

        if 'fire' not in fieldnames:
            fieldnames = fieldnames + ['fire']

        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for row_index, row in enumerate(reader, start=2):
            # row_index is 2 for the first data row when header is on line 1
            row['fire'] = '0.0'

            if row_index > start_line:
                co_value = row.get('co_ppm', '').strip()
                try:
                    co_ppm = float(co_value) if co_value != '' else None
                except ValueError:
                    co_ppm = None

                if co_ppm == 0.0:
                    continue

            writer.writerow(row)

def change_fire_value(input_file: str, new_value: str = '1.0') -> None:
    """Change the 'fire' column value to new_value for the specified line_number in input_file."""
    with open(input_file, 'r', newline='') as infile, open('temp_output.csv', 'w', newline='') as outfile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"CSV file {input_file} is empty or missing a header")

        if 'fire' not in fieldnames:
            fieldnames = fieldnames + ['fire']

        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for row_index, row in enumerate(reader, start=2):
            row['fire'] = new_value
            writer.writerow(row)

    # Replace original file with modified file
    import os
    os.replace('temp_output.csv', input_file)


if __name__ == '__main__':
    # input_path = 'data_log.csv'
    # output_path = 'processed_data.csv'

    # if len(sys.argv) >= 2:
    #     input_path = sys.argv[1]
    # if len(sys.argv) >= 3:
    #     output_path = sys.argv[2]

    # filter_zero_co_ppm_after_line(input_path, output_path)
    # print(f'Wrote filtered output to {output_path}')

    change_fire_value("close.csv", new_value='1.0')
    change_fire_value("5ft.csv", new_value='0.7')
    print('Updated fire values in close.csv and 5ft.csv')
