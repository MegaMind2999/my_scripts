import requests
from bs4 import BeautifulSoup
import shlex
import urllib3
import pandas as pd
import re
import os

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# PASTE YOUR FULL CURL COMMAND BELOW
# ==========================================
raw_curl_input = r"""
curl 'https://tdb.tanta.edu.eg/student_results/marklist_report.aspx' \
  -H 'accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7' \
  -H 'accept-language: en-US,en;q=0.9,ar-AE;q=0.8,ar;q=0.7' \
  -H 'cache-control: max-age=0' \
  -b '_ga=GA1.1.1649906355.1757781455; _ga_LXMC68XVXL=GS2.1.s1757801078$o2$g1$t1757801108$j30$l0$h0; ASP.NET_SessionId=adfsn1nixahqga4555hhph55' \
  -H 'dnt: 1' \
  -H 'priority: u=0, i' \
  -H 'referer: https://tdb.tanta.edu.eg/student_results/marklist.aspx' \
  -H 'sec-ch-ua: "Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Windows"' \
  -H 'sec-fetch-dest: document' \
  -H 'sec-fetch-mode: navigate' \
  -H 'sec-fetch-site: same-origin' \
  -H 'sec-fetch-user: ?1' \
  -H 'upgrade-insecure-requests: 1' \
  -H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'"""

def parse_curl_and_get_response(curl_command):
    """Parses curl command and fetches data ignoring SSL."""
    clean_command = curl_command.replace('\\\n', ' ').replace('\\', '')
    tokens = shlex.split(clean_command)
    
    url = None
    headers = {}
    cookies = {}
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == 'curl' and url is not None: break
        
        if token.startswith('http'):
            url = token
        elif token in ['-H', '--header']:
            i += 1
            if i < len(tokens) and ':' in tokens[i]:
                k, v = tokens[i].split(':', 1)
                headers[k.strip()] = v.strip()
        elif token in ['-b', '--cookie']:
            i += 1
            if i < len(tokens):
                for pair in tokens[i].split(';'):
                    if '=' in pair:
                        k, v = pair.split('=', 1)
                        cookies[k.strip()] = v.strip()
        i += 1

    if not url: raise ValueError("No URL found in curl command.")
    
    print(f"Fetching data from: {url}...")
    try:
        response = requests.get(url, headers=headers, cookies=cookies, verify=False)
        return response.text
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

def extract_course_code(soup):
    text = soup.get_text()
    match = re.search(r'([A-Za-z0-9]+)\s*كود المقرر', text)
    if match:
        return match.group(1)
    return "Student_List"

def extract_names_and_code(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # List to store tuples: (Serial_Number, Student_Name)
    students_data = []
    
    course_code = extract_course_code(soup)
    
    rows = soup.find_all('tr')
    
    for row in rows:
        cells = row.find_all('td')
        
        # Check if row has enough columns
        if len(cells) >= 8:
            try:
                # 1. Extract Serial Number (Last cell)
                serial_txt = cells[-1].get_text(strip=True)
                
                # If serial is not a number, skip (header or footer row)
                if not serial_txt.isdigit():
                    continue
                
                serial_num = int(serial_txt)

                # 2. Extract Name (3rd cell from right)
                name_text = cells[-3].get_text(strip=True)
                clean_name = name_text.replace('\xa0', '').strip()
                
                # Basic validation
                if not clean_name: continue
                if "اسم الطالب" in clean_name: continue
                
                # Store (Serial, Name)
                students_data.append({'id': serial_num, 'name': clean_name})
                
            except (IndexError, ValueError):
                continue

    # ========================================================
    # SORTING LOGIC: Sort by the extracted ID (Serial Number)
    # ========================================================
    print("Sorting students by serial number...")
    students_data.sort(key=lambda x: x['id'])
    
    # Filter duplicates AFTER sorting to maintain order
    final_names = []
    seen_names = set()
    
    for student in students_data:
        if student['name'] not in seen_names:
            final_names.append(student['name'])
            seen_names.add(student['name'])
            
    return final_names, course_code

def save_to_excel_rtl(names, filename_code):
    if not names:
        print("No names found to save.")
        return

    # Create DataFrame
    data = [{'No': i, 'Student Name': name} for i, name in enumerate(names, 1)]
    df = pd.DataFrame(data)
    
    filename = f"{filename_code}.xlsx"
    
    try:
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
            
            # Formatting for RTL (Arabic)
            worksheet = writer.sheets['Sheet1']
            worksheet.sheet_view.rightToLeft = True
            worksheet.column_dimensions['B'].width = 40
            worksheet.column_dimensions['A'].width = 8

        full_path = os.path.abspath(filename)
        print(f"\n[SUCCESS] Saved {len(names)} unique names to: {full_path}")
        
    except Exception as e:
        print(f"\n[ERROR] Could not save Excel file: {e}")
        print("Please close the Excel file if it is open and try again.")

if __name__ == "__main__":
    html_data = parse_curl_and_get_response(raw_curl_input)

    if html_data:
        names, course_code = extract_names_and_code(html_data)
        
        print(f"Detected Course Code: {course_code}")
        print(f"Number of unique students found: {len(names)}")
        
        if names:
            save_to_excel_rtl(names, course_code)
        else:
            print("No names found.")