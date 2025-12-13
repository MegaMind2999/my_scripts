import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import re
import pandas as pd
import os
import urllib3
import time

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# THEME CONFIGURATION
# =========================================================
COLOR_BG = "#f4f6f9"
COLOR_HEADER = "#2c3e50"
COLOR_ACCENT = "#2980b9"
COLOR_TEXT = "#34495e"
COLOR_WHITE = "#ffffff"
COLOR_SUCCESS = "#27ae60"
COLOR_WARNING = "#e74c3c"

LOGIN_URL = "https://tdb.tanta.edu.eg/student_results/default.aspx"
TARGET_URL = "https://tdb.tanta.edu.eg/student_results/marklist.aspx"
REPORT_URL = "https://tdb.tanta.edu.eg/student_results/marklist_report.aspx"

class TantaScraperApp:
    def __init__(self, root):
        self.root = root
        
        # --- UPDATE 1: Application Name ---
        self.root.title("Student List to Excel")
        
        # --- UPDATE 2: Application Icon ---
        # The .ico file must be in the same folder as this script
        try:
            self.root.iconbitmap("nicde.ico")
        except Exception:
            # If icon is missing during dev, don't crash, just print warning
            print("Warning: nicde.ico not found in folder.")

        self.root.geometry("700x850")
        self.root.configure(bg=COLOR_BG)
        
        # --- SESSION SETUP ---
        self.session = requests.Session()
        retry_strategy = Retry(
            total=4, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Origin': 'https://tdb.tanta.edu.eg',
            'Referer': LOGIN_URL
        })
        
        self.current_soup = None
        self.selections = {} 
        self.dropdown_map = {} 
        self.combos = {}
        
        self.id_map = {
            "Year": "ctl00_ContentPlaceHolder3_ddl_acad_year",
            "Faculty": "ctl00_ContentPlaceHolder3_ddl_fac",
            "Regulation": "ctl00_ContentPlaceHolder3_ddl_bylaw",
            "Phase": "ctl00_ContentPlaceHolder3_ddl_phase",
            "Dept": "ctl00_ContentPlaceHolder3_ddl_dept",
            "Semester": "ctl00_ContentPlaceHolder3_ddl_semester",
            "Door": "ctl00_ContentPlaceHolder3_door",
            "SubjSem": "ctl00_ContentPlaceHolder3_ddl_semester_subject",
            "Subject": "ctl00_ContentPlaceHolder3_ddl_subj"
        }

        self._apply_styles()
        self._setup_ui()
        
        self.log("System Initialized...", color="cyan")
        threading.Thread(target=self.perform_login, daemon=True).start()

    def _apply_styles(self):
        style = ttk.Style()
        try: style.theme_use('clam') 
        except: pass
        
        style.configure("Main.TFrame", background=COLOR_BG)
        style.configure("Card.TFrame", background=COLOR_WHITE, relief="flat")
        style.configure("Header.TLabel", background=COLOR_HEADER, foreground=COLOR_WHITE, font=("Segoe UI", 16, "bold"), padding=10)
        style.configure("Field.TLabel", background=COLOR_WHITE, foreground=COLOR_TEXT, font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", background=COLOR_HEADER, foreground=COLOR_WHITE, font=("Consolas", 9))
        style.configure("TCombobox", fieldbackground=COLOR_BG, background=COLOR_WHITE, arrowcolor=COLOR_ACCENT)
        style.map('TCombobox', fieldbackground=[('readonly', COLOR_BG)])
        style.configure("Action.TButton", font=("Segoe UI", 11, "bold"), background=COLOR_ACCENT, foreground=COLOR_WHITE, padding=8)

    def _setup_ui(self):
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill=tk.X)
        # Updated Header Text
        ttk.Label(header_frame, text="📊 Student List to Excel", style="Header.TLabel").pack(fill=tk.X)

        main_frame = ttk.Frame(self.root, style="Main.TFrame", padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        card_frame = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        card_frame.pack(fill=tk.X, pady=(0, 20))
        
        fields = [
            ("Year", "Academic Year"),
            ("Faculty", "Faculty"),
            ("Regulation", "Regulation"),
            ("Phase", "Level (Ferka)"),
            ("Dept", "Department"),
            ("Semester", "Semester"),
            ("Door", "Door"),
            ("SubjSem", "Course Semester"),
            ("Subject", "Course")
        ]

        for i, (key, label_text) in enumerate(fields):
            ttk.Label(card_frame, text=label_text, style="Field.TLabel").grid(row=i, column=0, sticky="w", pady=8, padx=(0, 15))
            cb = ttk.Combobox(card_frame, state="disabled", font=("Segoe UI", 10), width=50)
            cb.grid(row=i, column=1, sticky="ew", pady=8)
            cb.bind("<<ComboboxSelected>>", lambda e, k=key: self.on_selection(k))
            self.combos[key] = cb

        card_frame.columnconfigure(1, weight=1)

        action_frame = ttk.Frame(main_frame, style="Main.TFrame")
        action_frame.pack(fill=tk.X)

        self.progress = ttk.Progressbar(action_frame, mode='indeterminate', length=200)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self.btn_fetch = tk.Button(
            action_frame, text="📥 FETCH REPORT & SAVE EXCEL", state="disabled", 
            command=self.start_fetch, bg=COLOR_SUCCESS, fg="white", 
            font=("Segoe UI", 10, "bold"), padx=20, pady=8, borderwidth=0, cursor="hand2"
        )
        self.btn_fetch.pack(side=tk.RIGHT)

        log_frame = ttk.Frame(main_frame, style="Main.TFrame")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(20, 0))

        ttk.Label(log_frame, text="Activity Log", background=COLOR_BG, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 5))

        self.log_area = scrolledtext.ScrolledText(
            log_frame, height=10, state='disabled', font=("Consolas", 10), 
            bg="#1e1e1e", fg="#00ff00", insertbackground="white", relief="flat", borderwidth=0
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)
        
        for tag, color in [("info", "#00ff00"), ("error", "#ff4444"), ("cyan", "#00ffff"), ("warning", "orange")]:
            self.log_area.tag_config(tag, foreground=color)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel", padding=5).pack(side=tk.BOTTOM, fill=tk.X)

    def log(self, message, color="info"):
        def _log():
            self.log_area.config(state='normal')
            self.log_area.insert(tk.END, f">> {message}\n", color)
            self.log_area.see(tk.END)
            self.log_area.config(state='disabled')
            self.status_var.set(message)
        self.root.after(0, _log)

    def toggle_loading(self, is_loading):
        if is_loading:
            self.progress.start(10)
            self.root.config(cursor="watch")
        else:
            self.progress.stop()
            self.root.config(cursor="")

    # =========================================================
    # LOGIC
    # =========================================================

    def perform_login(self):
        try:
            self.toggle_loading(True)
            self.log("Connecting to Tanta University Server...", "cyan")
            
            resp = self.session.get(LOGIN_URL, verify=False, timeout=30)
            soup = BeautifulSoup(resp.text, 'html.parser')
            data = self.get_form_data(soup)
            data.update({'txt_user_name': "علوم", 'txt_pw': "علوم1234", 'Button1': 'دخول'})
            
            self.session.post(LOGIN_URL, data=data, headers={'Referer': LOGIN_URL}, verify=False, timeout=30)
            
            self.log("Authenticating...", "cyan")
            resp = self.session.get(TARGET_URL, verify=False, timeout=30)
            self.current_soup = BeautifulSoup(resp.text, 'html.parser')

            if "ddl_acad_year" not in resp.text:
                self.log("Login Failed: Page structure mismatch", "error")
                self.toggle_loading(False)
                return

            self.log("Login Successful", "info")
            self.root.after(0, lambda: self.load_step("Year"))

        except Exception as e:
            self.log(f"Connection Error: {e}", "error")
            self.toggle_loading(False)

    def get_form_data(self, soup):
        data = {}
        if not soup: return data
        for inp in soup.find_all('input'):
            if inp.get('name'): data[inp.get('name')] = inp.get('value', '')
        return data

    def extract_options(self, element_id):
        if not self.current_soup: return []
        select = self.current_soup.find('select', {'id': element_id})
        if not select: return []
        
        opts = []
        for opt in select.find_all('option'):
            val = opt.get('value', '')
            txt = opt.text.strip()
            if val and val != '0' and "اختر" not in txt and not txt.startswith("Select"):
                opts.append((val, txt))
        return opts

    def update_combo(self, key, options, auto_select_index=None):
        cb = self.combos[key]
        cb['state'] = 'readonly'
        self.dropdown_map[key] = options 
        cb['values'] = [txt for val, txt in options]
        
        self.toggle_loading(False)
        
        if options:
            if auto_select_index is not None and 0 <= auto_select_index < len(options):
                cb.current(auto_select_index)
                self.log(f"Auto-selected {key}", "cyan")
                self.root.after(100, lambda: self.on_selection(key))
            else:
                cb.set(f"Select {key}...")
                cb.focus()
        else:
            cb.set("No options found")
            cb['state'] = 'disabled'

    def make_post(self, updates, event_target):
        try:
            form_data = self.get_form_data(self.current_soup)
            
            # Force previous selections
            for key, val in self.selections.items():
                html_id = self.id_map.get(key)
                if html_id:
                    elem = self.current_soup.find('select', {'id': html_id})
                    if elem and elem.get('name'):
                        form_data[elem.get('name')] = val
            
            for eid, val in updates.items():
                sel = self.current_soup.find('select', {'id': eid})
                if sel: form_data[sel.get('name')] = val
                
            target_elem = self.current_soup.find('select', {'id': event_target})
            form_data['__EVENTTARGET'] = target_elem.get('name', '') if target_elem else ''
            
            if 'ctl00$ContentPlaceHolder3$Button1' in form_data: 
                del form_data['ctl00$ContentPlaceHolder3$Button1']

            time.sleep(0.5)

            resp = self.session.post(
                TARGET_URL, data=form_data, headers={'Referer': TARGET_URL}, verify=False, timeout=45
            )
            
            if resp.status_code != 200:
                self.log(f"Server Error: {resp.status_code}", "error")
                return

            self.current_soup = BeautifulSoup(resp.text, 'html.parser')

        except Exception as e:
            self.log(f"Network Error: {e}", "error")
            raise e

    def load_step(self, step_name):
        try:
            get_opts = lambda k: self.extract_options(self.id_map[k])

            if step_name == "Year":
                opts = get_opts("Year")[:4]
                self.root.after(0, lambda: self.update_combo("Year", opts))

            elif step_name == "Faculty":
                opts = get_opts("Faculty")
                self.root.after(0, lambda: self.update_combo("Faculty", opts, auto_select_index=0))

            elif step_name == "Regulation":
                opts = get_opts("Regulation")
                self.root.after(0, lambda: self.update_combo("Regulation", opts))

            elif step_name == "Phase":
                opts = [o for o in get_opts("Phase") if "المستوى" in o[1]]
                self.root.after(0, lambda: self.update_combo("Phase", opts))

            elif step_name == "Dept":
                opts = get_opts("Dept")
                self.root.after(0, lambda: self.update_combo("Dept", opts))

            elif step_name == "Semester":
                opts = get_opts("Semester")
                self.root.after(0, lambda: self.update_combo("Semester", opts))

            elif step_name == "Door":
                opts = get_opts("Door")
                self.root.after(0, lambda: self.update_combo("Door", opts, auto_select_index=0))

            elif step_name == "SubjSem":
                opts = get_opts("SubjSem")
                self.root.after(0, lambda: self.update_combo("SubjSem", opts))

            elif step_name == "Subject":
                opts = get_opts("Subject")
                self.root.after(0, lambda: self.update_combo("Subject", opts))
                
                def enable_btn():
                    self.btn_fetch.config(state="normal", bg=COLOR_SUCCESS, cursor="hand2")
                self.root.after(0, enable_btn)

        except Exception as e:
            self.log(f"Error loading {step_name}: {e}", "error")
            self.toggle_loading(False)

    def on_selection(self, key):
        idx = self.combos[key].current()
        if idx == -1: return

        val, text = self.dropdown_map[key][idx]
        self.selections[key] = val
        self.log(f"Selected: {text}", "info")
        
        self.toggle_loading(True)
        threading.Thread(target=self.process_next_step, args=(key, val)).start()

    def process_next_step(self, current_key, current_val):
        target_id = self.id_map.get(current_key)
        seq = ["Year", "Faculty", "Regulation", "Phase", "Dept", "Semester", "Door", "SubjSem", "Subject"]
        
        try:
            if current_key == "Subject":
                self.make_post({target_id: current_val}, target_id)
                self.log("Ready to fetch.", "cyan")
                self.toggle_loading(False)
                return
            
            if current_key == "Regulation":
                self.make_post({target_id: current_val}, target_id)
            elif current_key not in ["Year", "Faculty"]:
                self.make_post({target_id: current_val}, target_id)

            try:
                curr_idx = seq.index(current_key)
                next_step = seq[curr_idx + 1]
                self.load_step(next_step)
            except IndexError:
                self.toggle_loading(False)
        
        except Exception as e:
            self.log(f"Processing Error: {e}", "error")
            self.toggle_loading(False)

    def start_fetch(self):
        self.btn_fetch.config(state="disabled", bg="#95a5a6", cursor="wait")
        self.toggle_loading(True)
        threading.Thread(target=self.fetch_report).start()

    def fetch_report(self):
        try:
            self.log("Requesting Final Report...", "warning")
            form_data = self.get_form_data(self.current_soup)
            
            for key, val in self.selections.items():
                html_id = self.id_map.get(key)
                if html_id:
                    elem = self.current_soup.find('select', {'id': html_id})
                    if elem and elem.get('name'): form_data[elem.get('name')] = val
            
            form_data['ctl00$ContentPlaceHolder3$Button1'] = 'تقرير الطلاب'

            self.session.post(TARGET_URL, data=form_data, headers={'Referer': TARGET_URL}, verify=False, allow_redirects=False)
            time.sleep(1.5)
            
            resp = self.session.get(REPORT_URL, headers={'Referer': TARGET_URL}, verify=False)
            soup = BeautifulSoup(resp.text, 'html.parser')
            names, code = self.parse_results(soup)
            
            if names:
                self.log(f"Found {len(names)} students. Saving...", "cyan")
                self.save_excel(names, code)
            else:
                self.log("No students found.", "warning")
                messagebox.showwarning("Result", "No students found.")

        except Exception as e:
            self.log(f"Fetch Error: {e}", "error")
        finally:
            self.toggle_loading(False)
            def reset_btn():
                self.btn_fetch.config(state="normal", bg=COLOR_SUCCESS, cursor="hand2")
            self.root.after(0, reset_btn)

    def parse_results(self, soup):
        txt = soup.get_text()
        match = re.search(r'([A-Za-z0-9]+)\s*كود المقرر', txt)
        code = match.group(1) if match else "Student_List"
        
        students = []
        table = soup.find('table', {'id': 'ctl00_ContentPlaceHolder3_gv_list'})
        rows = table.find_all('tr') if table else soup.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 8:
                try:
                    s_txt = cells[-1].get_text(strip=True)
                    if not s_txt.isdigit(): continue
                    s_id = int(s_txt)
                    name = cells[-3].get_text(strip=True).replace('\xa0', '').strip()
                    if name and "اسم الطالب" not in name:
                        students.append({'id': s_id, 'name': name})
                except: continue
        
        students.sort(key=lambda x: x['id'])
        final_names = []
        seen = set()
        for s in students:
            if s['name'] not in seen:
                final_names.append(s['name'])
                seen.add(s['name'])
        return final_names, code

    def save_excel(self, names, code):
        safe_code = "".join([c for c in code if c.isalnum() or c in (' ', '-', '_')]).strip()
        filename = f"{safe_code}.xlsx"
        
        data = [{'No': i, 'Student Name': name} for i, name in enumerate(names, 1)]
        df = pd.DataFrame(data)
        
        # --- UPDATE 3: File Permission Safety ---
        try:
            # Check if file is open/locked by trying to append to it first
            # If it's locked by Excel, this raises PermissionError
            if os.path.exists(filename):
                with open(filename, "a"): pass
            
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Sheet1')
                ws = writer.sheets['Sheet1']
                ws.sheet_view.rightToLeft = True
                ws.column_dimensions['B'].width = 40
                ws.column_dimensions['A'].width = 8
            
            full_path = os.path.abspath(filename)
            self.log(f"Saved: {filename}", "info")
            
            ask_open = messagebox.askyesno(
                "Success", 
                f"File saved successfully:\n{filename}\n\nDo you want to open it now?"
            )
            if ask_open:
                os.startfile(full_path)

        except PermissionError:
            self.log("ERROR: File is open. Close Excel and try again.", "error")
            messagebox.showerror("Permission Error", f"The file '{filename}' is currently open in Excel.\n\nPlease close it and try again.")
        except Exception as e:
            self.log(f"Excel Error: {e}", "error")

if __name__ == "__main__":
    root = tk.Tk()
    app = TantaScraperApp(root)
    root.mainloop()