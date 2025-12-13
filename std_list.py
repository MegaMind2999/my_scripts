import time
import pandas as pd
import os
import re
from bs4 import BeautifulSoup
import requests
import urllib3
from urllib.parse import parse_qsl, urlencode

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# CONFIGURATION
# =========================================================
LOGIN_URL = "https://tdb.tanta.edu.eg/student_results/default.aspx"
TARGET_URL = "https://tdb.tanta.edu.eg/student_results/marklist.aspx"
REPORT_URL = "https://tdb.tanta.edu.eg/student_results/marklist_report.aspx"

# =========================================================
# PARSING LOGIC
# =========================================================
def extract_course_code(soup):
    """Finds the course code in the page text."""
    text = soup.get_text()
    match = re.search(r'([A-Za-z0-9]+)\s*كود المقرر', text)
    if match: return match.group(1)
    return "Student_List"

def extract_names_and_code(soup):
    """Extracts student names and sorts them by Serial Number."""
    students_data = []
    course_code = extract_course_code(soup)
    
    # Try to find specific table, fallback to all rows
    table = soup.find('table', {'id': 'ctl00_ContentPlaceHolder3_gv_list'})
    rows = table.find_all('tr') if table else soup.find_all('tr')
    
    print(f"   [Parser] Scanning {len(rows)} rows...")

    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 8:
            try:
                # Extract Serial Number (Last cell)
                serial_txt = cells[-1].get_text(strip=True)
                if not serial_txt.isdigit(): continue
                serial_num = int(serial_txt)

                # Extract Name (3rd cell from right)
                name_text = cells[-3].get_text(strip=True)
                clean_name = name_text.replace('\xa0', '').strip()
                
                if not clean_name or "اسم الطالب" in clean_name: continue
                
                students_data.append({'id': serial_num, 'name': clean_name})
            except (IndexError, ValueError):
                continue

    # Sorting Logic
    if students_data:
        students_data.sort(key=lambda x: x['id'])
    
    # Remove duplicates preserving order
    final_names = []
    seen = set()
    for s in students_data:
        if s['name'] not in seen:
            final_names.append(s['name'])
            seen.add(s['name'])
            
    return final_names, course_code

def save_to_excel_rtl(names, filename_code):
    """Saves to Excel with Right-to-Left formatting."""
    if not names:
        print("   [Info] No students found to save.")
        return

    data = [{'No': i, 'Student Name': name} for i, name in enumerate(names, 1)]
    df = pd.DataFrame(data)
    
    safe_code = "".join([c for c in filename_code if c.isalnum() or c in (' ', '-', '_')]).strip()
    filename = f"{safe_code}.xlsx"
    
    try:
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
            ws = writer.sheets['Sheet1']
            ws.sheet_view.rightToLeft = True
            ws.column_dimensions['B'].width = 40
            ws.column_dimensions['A'].width = 8

        print(f"\n   [SUCCESS] Saved {len(names)} unique names to: {filename}")
    except Exception as e:
        print(f"\n   [ERROR] Could not save Excel file: {e}")

# =========================================================
# REQUESTS-BASED HELPERS
# =========================================================

def get_all_form_inputs(soup):
    """Extracts all inputs/selects for POST data."""
    inputs = {}
    for inp in soup.find_all('input'):
        if inp.get('name'): inputs[inp.get('name')] = inp.get('value', '')
    
    for select in soup.find_all('select'):
        name = select.get('name')
        if name:
            selected = select.find('option', selected=True)
            if selected: inputs[name] = selected.get('value', '')
            else:
                first = select.find('option')
                inputs[name] = first.get('value', '') if first else ''
    return inputs

def get_select_options(soup, element_id):
    """Scrapes <option> tags from a select element."""
    select_elem = soup.find('select', {'id': element_id})
    if not select_elem: return []
    
    options = []
    for opt in select_elem.find_all('option'):
        val = opt.get('value', '')
        text = opt.text.strip()
        options.append((val, text))
    return options

def user_select_option(current_soup, element_id, label_name, 
                       auto_select_index=None, 
                       filter_condition=None, 
                       limit_display=None):
    """
    Enhanced selection function.
    - auto_select_index: If set (e.g. 0), picks that index automatically.
    - filter_condition: Lambda function to filter text (e.g. only show 'المستوى').
    - limit_display: Integer to show only top N options (e.g. top 4 years).
    """
    print(f"\n--- Select {label_name} ---")
    options = get_select_options(current_soup, element_id)
    
    # 1. Cleaning: Remove 'Select...' placeholders and empty values
    clean_options = []
    for val, text in options:
        if not val or val == '0' or "اختر" in text or text.startswith("Select"):
            continue
        clean_options.append((val, text))

    if not clean_options:
        print(f"   [Error] No valid options found for {label_name}.")
        return None, None

    # 2. Filtering: Apply custom text filter if provided
    if filter_condition:
        clean_options = [opt for opt in clean_options if filter_condition(opt[1])]
        if not clean_options:
            print(f"   [Error] No options matched filter for {label_name}.")
            return None, None

    # 3. Auto Selection Logic
    if auto_select_index is not None:
        if 0 <= auto_select_index < len(clean_options):
            val, txt = clean_options[auto_select_index]
            print(f"   [Auto-Selected] {txt}")
            return val, txt
        else:
            # Fallback to first if index is out of bounds
            val, txt = clean_options[0]
            print(f"   [Auto-Selected (Fallback)] {txt}")
            return val, txt

    # 4. Display Limit Logic
    display_options = clean_options[:limit_display] if limit_display else clean_options

    # 5. User Interaction
    for idx, (val, text) in enumerate(display_options):
        print(f"   {idx}. {text}")

    while True:
        try:
            choice_idx = int(input(f">> Enter number (0-{len(display_options)-1}): "))
            if 0 <= choice_idx < len(display_options):
                return display_options[choice_idx]
            print("Invalid number.")
        except ValueError:
            print("Please enter a number.")

def make_post_request(session, current_soup, updates_dict, event_target):
    """Makes a POST request with updated form values."""
    form_data = get_all_form_inputs(current_soup)
    
    if 'ctl00$ContentPlaceHolder3$Button1' in form_data:
        del form_data['ctl00$ContentPlaceHolder3$Button1']
    
    required_dropdowns = [
        'ctl00$ContentPlaceHolder3$ddl_acad_year', 'ctl00$ContentPlaceHolder3$ddl_fac',
        'ctl00$ContentPlaceHolder3$ddl_bylaw', 'ctl00$ContentPlaceHolder3$ddl_phase',
        'ctl00$ContentPlaceHolder3$ddl_dept', 'ctl00$ContentPlaceHolder3$ddl_semester',
        'ctl00$ContentPlaceHolder3$ddl_semester_subject',
    ]
    for d in required_dropdowns:
        if d not in form_data: form_data[d] = '0'
    
    for element_id, value in updates_dict.items():
        select_elem = current_soup.find('select', {'id': element_id})
        if select_elem: form_data[select_elem.get('name')] = value
    
    event_target_elem = current_soup.find('select', {'id': event_target})
    form_data['__EVENTTARGET'] = event_target_elem.get('name', '') if event_target_elem else ''
    form_data['__EVENTARGUMENT'] = ''
    form_data['__LASTFOCUS'] = ''
    
    # print(f"   [POST] Updating via {event_target}...")
    
    response = session.post(
        TARGET_URL, 
        data=form_data,
        headers={'Referer': TARGET_URL, 'Origin': 'https://tdb.tanta.edu.eg'}, 
        verify=False
    )
    # time.sleep(0.5) 
    if response.status_code != 200: return None
    return BeautifulSoup(response.text, 'html.parser')

def get_final_report_and_parse(session, current_soup):
    """Gets the final report."""
    if current_soup is None: return [], "Error"
    
    form_data = get_all_form_inputs(current_soup)
    form_data['ctl00$ContentPlaceHolder3$Button1'] = 'تقرير الطلاب'

    print("   [Submitting] Final report request...")
    session.post(TARGET_URL, data=form_data, headers={'Referer': TARGET_URL}, verify=False, allow_redirects=False)
    time.sleep(1)

    print("   [Fetching] Report page...")
    report_response = session.get(REPORT_URL, headers={'Referer': TARGET_URL}, verify=False)
    
    if report_response.status_code != 200: return [], "Error"
    return extract_names_and_code(BeautifulSoup(report_response.text, 'html.parser'))

# =========================================================
# MAIN BOT
# =========================================================
def main():
    with requests.Session() as session:
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Upgrade-Insecure-Requests': '1'
        })

        try:
            print("="*60)
            print("Tanta University Scraper (Customized)")
            print("="*60)
            
            # Login
            print("[1/3] Logging in...")
            login_page = session.get(LOGIN_URL, verify=False)
            soup = BeautifulSoup(login_page.text, 'html.parser')
            data = get_all_form_inputs(soup)
            data.update({'txt_user_name': "علوم", 'txt_pw': "علوم1234", 'Button1': 'دخول'})
            session.post(LOGIN_URL, data=data, headers={'Referer': LOGIN_URL}, verify=False)
            
            # Navigate
            print("[2/3] Navigating...")
            res = session.get(TARGET_URL, verify=False)
            current_soup = BeautifulSoup(res.text, 'html.parser')
            if "ddl_acad_year" not in res.text:
                 print("✗ Login failed.")
                 return
            print("[3/3] Ready!")

            selections = []

            # 1. Academic Year (Limit to top 4)
            val, txt = user_select_option(current_soup, "ctl00_ContentPlaceHolder3_ddl_acad_year", "Academic Year", limit_display=4)
            if not val: return
            selections.append(f"Year: {txt}")
            year_val = val

            # 2. Faculty (Auto-select Index 0)
            val, txt = user_select_option(current_soup, "ctl00_ContentPlaceHolder3_ddl_fac", "Faculty", auto_select_index=0)
            if not val: return
            selections.append(f"Faculty: {txt}")
            fac_val = val

            # 3. Regulation
            val, txt = user_select_option(current_soup, "ctl00_ContentPlaceHolder3_ddl_bylaw", "Regulation")
            if not val: return
            selections.append(f"Regulation: {txt}")
            reg_val = val
            
            # Submit initial batch
            print(f"\n[Processing] Initial setup...")
            current_soup = make_post_request(session, current_soup, 
                {'ctl00_ContentPlaceHolder3_ddl_acad_year': year_val, 'ctl00_ContentPlaceHolder3_ddl_fac': fac_val, 'ctl00_ContentPlaceHolder3_ddl_bylaw': reg_val},
                'ctl00_ContentPlaceHolder3_ddl_bylaw'
            )
            if not current_soup: return

            # 4. Level (Filter: Only "المستوى")
            print(f"\n--- Current Selection: {selections[0]} | {selections[1]} ---")
            val, txt = user_select_option(
                current_soup, 
                "ctl00_ContentPlaceHolder3_ddl_phase", 
                "Level (Ferka)", 
                filter_condition=lambda text: "المستوى" in text  # Custom Filter
            )
            if not val: return
            selections.append(f"Level: {txt}")
            current_soup = make_post_request(session, current_soup, {"ctl00_ContentPlaceHolder3_ddl_phase": val}, "ctl00_ContentPlaceHolder3_ddl_phase")

            # 5. Department
            val, txt = user_select_option(current_soup, "ctl00_ContentPlaceHolder3_ddl_dept", "Department")
            if not val: return
            selections.append(f"Dept: {txt}")
            current_soup = make_post_request(session, current_soup, {"ctl00_ContentPlaceHolder3_ddl_dept": val}, "ctl00_ContentPlaceHolder3_ddl_dept")

            # 6. Semester
            val, txt = user_select_option(current_soup, "ctl00_ContentPlaceHolder3_ddl_semester", "Semester")
            if not val: return
            selections.append(f"Sem: {txt}")
            current_soup = make_post_request(session, current_soup, {"ctl00_ContentPlaceHolder3_ddl_semester": val}, "ctl00_ContentPlaceHolder3_ddl_semester")

            # 7. Door (Auto-select "دور أول" / Index 0)
            val, txt = user_select_option(current_soup, "ctl00_ContentPlaceHolder3_door", "Door", auto_select_index=0)
            if not val: return
            selections.append(f"Door: {txt}")
            current_soup = make_post_request(session, current_soup, {"ctl00_ContentPlaceHolder3_door": val}, "ctl00_ContentPlaceHolder3_door")

            # 8. Course Semester
            val, txt = user_select_option(current_soup, "ctl00_ContentPlaceHolder3_ddl_semester_subject", "Course Semester")
            if not val: return
            current_soup = make_post_request(session, current_soup, {"ctl00_ContentPlaceHolder3_ddl_semester_subject": val}, "ctl00_ContentPlaceHolder3_ddl_semester_subject")

            # 9. Course
            val, txt = user_select_option(current_soup, "ctl00_ContentPlaceHolder3_ddl_subj", "Course")
            if not val: return
            selections.append(f"Course: {txt}")
            make_post_request(session, current_soup, {"ctl00_ContentPlaceHolder3_ddl_subj": val}, "ctl00_ContentPlaceHolder3_ddl_subj")

            # Final Report
            print("="*60)
            print("Fetching Data...")
            names, code = get_final_report_and_parse(session, current_soup)
            
            print(f"\n✓ Found {len(names)} unique students for course: {code}")
            if names: save_to_excel_rtl(names, code)
            else: print("⚠ No students found.")

        except Exception as e:
            print(f"\n✗ Error: {e}")

if __name__ == "__main__":
    main()