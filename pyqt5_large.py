import sys
import json
import shutil
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QTableWidget, QTableWidgetItem, QLabel, QScrollArea,
                            QGroupBox, QHeaderView, QStyleFactory, QLineEdit, QFormLayout,
                            QAbstractItemView, QMessageBox, QPushButton, QHBoxLayout,
                            QGridLayout, QFrame, QDialog, QProgressDialog, QCompleter)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIcon
import os
from datetime import datetime
import re

class ClaimsViewer(QMainWindow):
    CPT_REQUIRED_KEYS = [
        "select", "from_date", "to_date", "cpt", "mo1", "mo2", "rev_code",
        "units", "billed", "allowed", "discount", "deduct", "coins", "copay",
        "patres", "adj_noncvrd", "group_code", "rc", "rmk", "cob", "paid",
        "balance", "Multi"
    ]
    REQUIRED_FIELDS = ["patient_last_name", "claim_id", "billed"]

    def __init__(self, data, input_file='jobjson.json'):
        super().__init__()
        self.data = data
        self.input_file = input_file
        self.claims_data = None
        self.claims_container = None
        self.summary_widget = None
        self.header_widget = None
        self.changes = {}
        self.completers = {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Claims Viewer')
        self.setGeometry(100, 100, 1400, 800)  # Wider window to fit all content
        self.setMinimumSize(1280, 720)
        if os.path.exists('icon_3.ico'):
            self.setWindowIcon(QIcon('icon_3.ico'))

        app_font = QFont("Inter", 10)
        QApplication.setFont(app_font)

        try:
            with open('styles.qss', 'r') as style_file:
                self.setStyleSheet(style_file.read())
        except FileNotFoundError:
            print("Warning: styles.qss not found, using default styling")
            self.apply_default_theme()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(20, 20, 20, 20)

        transaction_data = self.data["all_transaction_data"][0]["transaction_data"]
        self.claims_data = transaction_data["claims_data"]

        # Top Bar: Search and Action Buttons
        top_bar_layout = QHBoxLayout()
        search_label = QLabel("Search Claims:")
        search_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.search_bar = QLineEdit()
        self.search_bar.setProperty("searchBar", True)
        self.search_bar.setPlaceholderText("Search by Patient Last Name, Claim ID, or Payer Name")
        self.search_bar.setToolTip("Filter claims by patient last name, claim ID, or payer name")
        self.search_bar.setMinimumWidth(400)
        self.search_bar.textChanged.connect(self.filter_claims)
        top_bar_layout.addWidget(search_label)
        top_bar_layout.addWidget(self.search_bar)
        top_bar_layout.addStretch()

        load_button = QPushButton("Load EOBs")
        load_button.setFixedWidth(120)
        load_button.setProperty("text", "Load EOBs")
        load_button.setIcon(QIcon('load_icon.png') if os.path.exists('load_icon.png') else QIcon())
        load_button.clicked.connect(self.load_eobs)
        top_bar_layout.addWidget(load_button)

        save_button = QPushButton("Save")
        save_button.setFixedWidth(120)
        save_button.setProperty("text", "Save")
        save_button.setIcon(QIcon('save_icon.png') if os.path.exists('save_icon.png') else QIcon())
        save_button.clicked.connect(self.save_changes)
        top_bar_layout.addWidget(save_button)
        content_layout.addLayout(top_bar_layout)

        self.header_widget = self.create_header_section()
        content_layout.addWidget(self.header_widget)

        self.claims_container = self.create_claims_container()
        content_layout.addWidget(self.claims_container)

        self.summary_widget = self.create_summary_section(transaction_data)
        content_layout.addWidget(self.summary_widget)

        scroll_area.setWidget(content_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.addWidget(scroll_area)

        self.setup_shortcuts()
        self.setup_completers()
        self.show()

    def setup_shortcuts(self):
        from PyQt5.QtGui import QKeySequence
        from PyQt5.QtWidgets import QShortcut
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_changes)
        QShortcut(QKeySequence("Ctrl+N"), self, lambda: self.add_new_claim(self.claims_container.layout(), None))
        QShortcut(QKeySequence("Ctrl+D"), self, lambda: self.delete_claim(self.claims_container.layout(), None))

    def setup_completers(self):
        payer_names = set()
        patient_names = set()
        cpt_codes = set()
        for claim in self.claims_data:
            payer_names.add(self.data["all_transaction_data"][0]["transaction_data"].get("payer_name", ""))
            patient_names.add(claim.get("patient_last_name", ""))
            for line in claim.get("cpt_data", []):
                cpt_codes.add(line.get("cpt", ""))
        
        self.completers["payer_name"] = QCompleter(list(payer_names), self)
        self.completers["patient_last_name"] = QCompleter(list(patient_names), self)
        self.completers["cpt"] = QCompleter(list(cpt_codes), self)
        for completer in self.completers.values():
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setCompletionMode(QCompleter.PopupCompletion)

    def validate_field(self, field, value, field_name):
        if field_name in self.REQUIRED_FIELDS and not value.strip():
            field.setProperty("error", True)
            return f"{field_name.replace('_', ' ').title()} is required"
        if field_name == "cpt" and value and not re.match(r"^\d{5}$", value):
            field.setProperty("error", True)
            return "CPT code must be 5 digits"
        if field_name in ["billed", "allowed", "paid", "discount", "deduct", "coins", "copay", "patres", "cob", "balance"]:
            if value and not re.match(r"^-?\d*\.?\d{0,2}$", value.replace('$', '').replace(',', '')):
                field.setProperty("error", True)
                return f"{field_name.replace('_', ' ').title()} must be a valid number"
        if field_name in ["from_date", "to_date"]:
            if value and not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                field.setProperty("error", True)
                return "Date must be in YYYY-MM-DD format"
        field.setProperty("error", False)
        return None

    def track_header_change(self, key, value, field):
        if "header" not in self.changes:
            self.changes["header"] = {}
        self.changes["header"][key] = value
        error = self.validate_field(field, value, key)
        field.setStyleSheet("")
        field.setToolTip(error or f"Enter {key.replace('_', ' ').title()}")

    def apply_default_theme(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f7fa; }
            QGroupBox { 
                background-color: #ffffff; 
                border: 1px solid #d1d5db; 
                border-radius: 8px; 
                margin-top: 20px; 
                padding: 15px; 
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                subcontrol-position: top left; 
                padding: 8px 15px; 
                background: linear-gradient(90deg, #1e40af, #3b82f6); 
                color: #ffffff; 
                font-weight: 700;
            }
            QTableWidget { 
                background-color: #ffffff; 
                border: 1px solid #d1d5db; 
                border-radius: 8px; 
                gridline-color: #e5e7eb; 
                alternate-background-color: #f9fafb; 
            }
            QHeaderView::section { 
                background: linear-gradient(90deg, #1e40af, #3b82f6); 
                color: #ffffff; 
                padding: 8px; 
                border: none; 
                font-weight: 600; 
            }
            QLineEdit { 
                border: 1px solid #d1d5db; 
                border-radius: 6px; 
                padding: 8px; 
                background-color: #ffffff; 
            }
            QPushButton { 
                background: linear-gradient(45deg, #3b82f6, #2563eb); 
                color: #ffffff; 
                border: none; 
                border-radius: 6px; 
                padding: 10px; 
                font-weight: 600; 
            }
        """)

    def track_field_change(self, claim_number, field_name, value, field):
        if "claims" not in self.changes:
            self.changes["claims"] = {}
        if claim_number not in self.changes["claims"]:
            self.changes["claims"][claim_number] = {}
        self.changes["claims"][claim_number][field_name] = value
        error = self.validate_field(field, value, field_name)
        field.setStyleSheet("")
        field.setToolTip(error or f"Enter {field_name.replace('_', ' ').title()}")

    def track_service_change(self, claim_number, item, field=None):
        if "service_lines" not in self.changes:
            self.changes["service_lines"] = {}
        if claim_number not in self.changes["service_lines"]:
            self.changes["service_lines"][claim_number] = {}
        
        row = item.row()
        col = item.column()
        headers = self.CPT_REQUIRED_KEYS
        field_name = headers[col]
        
        is_new_claim = False
        new_claim_data = None
        base_index = claim_number - 1
        for change in self.changes.get("claims_structural", []):
            if change["index"] == base_index and change["action"] == "added":
                is_new_claim = True
                new_claim_data = change["data"]
                break
        
        if is_new_claim:
            if row not in self.changes["service_lines"][claim_number]:
                cpt_data = new_claim_data["cpt_data"]
                if row < len(cpt_data):
                    self.changes["service_lines"][claim_number][row] = cpt_data[row].copy()
                else:
                    empty_row = {key: "" for key in self.CPT_REQUIRED_KEYS}
                    empty_row["Multi"] = "[]"
                    self.changes["service_lines"][claim_number][row] = empty_row
            self.changes["service_lines"][claim_number][row][field_name] = item.text()
            if field:
                error = self.validate_field(field, item.text(), field_name)
                field.setToolTip(error or f"Enter {field_name.replace('_', ' ').title()}")
        else:
            adjusted_number = claim_number
            for change in self.changes.get("claims_structural", []):
                if change["index"] < base_index:
                    if change["action"] == "deleted":
                        adjusted_number -= 1
                    elif change["action"] == "added":
                        adjusted_number += 1
            if 0 <= adjusted_number - 1 < len(self.claims_data):
                claim_data = self.claims_data[adjusted_number - 1]
                cpt_data = claim_data["cpt_data"]
                if row < len(cpt_data):
                    if row not in self.changes["service_lines"][claim_number]:
                        self.changes["service_lines"][claim_number][row] = cpt_data[row].copy()
                    self.changes["service_lines"][claim_number][row][field_name] = item.text()
                    if field:
                        error = self.validate_field(field, item.text(), field_name)
                        field.setToolTip(error or f"Enter {field_name.replace('_', ' ').title()}")
                else:
                    if row not in self.changes["service_lines"][claim_number]:
                        empty_row = {key: "" for key in self.CPT_REQUIRED_KEYS}
                        empty_row["Multi"] = "[]"
                        self.changes["service_lines"][claim_number][row] = empty_row
                    self.changes["service_lines"][claim_number][row][field_name] = item.text()
                    if field:
                        error = self.validate_field(field, item.text(), field_name)
                        field.setToolTip(error or f"Enter {field_name.replace('_', ' ').title()}")

    def save_changes(self):
        errors = self.validate_all_fields()
        if errors:
            QMessageBox.critical(self, "Validation Error", "Please fix the following errors:\n" + "\n".join(errors))
            return

        progress = QProgressDialog("Saving changes...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        try:
            progress.setValue(10)
            if "header" in self.changes:
                for key, value in self.changes["header"].items():
                    if key in ["job_filename", "out_filename", "job_filepath", "Ml-HM-status", 
                            "job_id", "client_name", "claimcount", "autopopulatestatus"]:
                        self.data[key] = value
                    else:
                        self.data["all_transaction_data"][0]["transaction_data"][key] = value
            
            progress.setValue(30)
            if "claims_structural" in self.changes:
                for change in sorted([c for c in self.changes["claims_structural"] if c["action"] == "deleted"], 
                                key=lambda x: x["index"], reverse=True):
                    self.claims_data.pop(change['index'])
                
                deletions = sum(1 for c in self.changes["claims_structural"] if c["action"] == "deleted")
                for change in sorted([c for c in self.changes["claims_structural"] if c["action"] == "added"], 
                                key=lambda x: x["index"]):
                    adjusted_index = change["index"] - deletions
                    self.claims_data.insert(adjusted_index, change["data"])
            
            progress.setValue(50)
            if "claims" in self.changes:
                for claim_number, fields in self.changes["claims"].items():
                    base_index = claim_number - 1
                    adjusted_index = base_index
                    additions_before = 0
                    deletions_before = 0
                    for change in self.changes.get("claims_structural", []):
                        if change["index"] < base_index:
                            if change["action"] == "added":
                                additions_before += 1
                            elif change["action"] == "deleted":
                                deletions_before += 1
                        elif change["index"] == base_index and change["action"] == "added":
                            adjusted_index = base_index
                            break
                    else:
                        adjusted_index = base_index + additions_before - deletions_before
                    
                    while adjusted_index >= len(self.claims_data):
                        empty_claim = self.create_empty_claim()
                        self.claims_data.append(empty_claim)

                    for field_name, value in fields.items():
                        self.claims_data[adjusted_index][field_name] = value
            
            progress.setValue(70)
            if "service_lines" in self.changes:
                for claim_number, rows in self.changes["service_lines"].items():
                    base_index = claim_number - 1
                    adjusted_index = base_index
                    additions_before = 0
                    deletions_before = 0
                    for change in self.changes.get("claims_structural", []):
                        if change["index"] < base_index:
                            if change["action"] == "added":
                                additions_before += 1
                            elif change["action"] == "deleted":
                                deletions_before += 1
                        elif change["index"] == base_index and change["action"] == "added":
                            adjusted_index = base_index
                            break
                    else:
                        adjusted_index = base_index + additions_before - deletions_before
                    
                    while adjusted_index >= len(self.claims_data):
                        empty_claim = self.create_empty_claim()
                        self.claims_data.append(empty_claim)
                    
                    claim_data = self.claims_data[adjusted_index]
                    if "cpt_data" not in claim_data:
                        claim_data["cpt_data"] = []
                    cpt_data = claim_data["cpt_data"]
                    
                    for row in sorted([r for r, d in rows.items() if d.get("action") == "deleted"], reverse=True):
                        if 0 <= row < len(cpt_data):
                            cpt_data.pop(row)
                    
                    for row in sorted([r for r, d in rows.items() if d.get("action") == "added"]):
                        if row >= len(cpt_data):
                            cpt_data.append({})
                        for key in self.CPT_REQUIRED_KEYS:
                            if key not in rows[row]:
                                rows[row][key] = "" if key != "Multi" else "[]"
                        cpt_data[row].update({k: v for k, v in rows[row].items() if k != "action"})
                    
                    for row, fields in rows.items():
                        if fields.get("action") in ["added", "deleted"]:
                            continue
                        while row >= len(cpt_data):
                            empty_row = {key: "" for key in self.CPT_REQUIRED_KEYS}
                            empty_row["Multi"] = "[]"
                            cpt_data.append(empty_row)
                        for key in self.CPT_REQUIRED_KEYS:
                            if key not in fields:
                                fields[key] = "" if key != "Multi" else "[]"
                        cpt_data[row].update(fields)
            
            progress.setValue(90)
            self.data["all_transaction_data"][0]["transaction_data"]["claims_data"] = self.claims_data
            
            shutil.copy(self.input_file, self.input_file + '.backup')
            
            with open(self.input_file, 'w') as file:
                json.dump(self.data, file, indent=4)
            
            progress.setValue(100)
            QMessageBox.information(self, "Success", "Changes saved. Backup created as jobjson.json.backup.")
            
            transaction_data = self.data["all_transaction_data"][0]["transaction_data"]
            new_summary_widget = self.create_summary_section(transaction_data)
            content_layout = self.centralWidget().layout().itemAt(0).widget().widget().layout()
            content_layout.replaceWidget(self.summary_widget, new_summary_widget)
            self.summary_widget.deleteLater()
            self.summary_widget = new_summary_widget
            
            self.setup_completers()
            self.changes.clear()
        
        except Exception as e:
            progress.cancel()
            QMessageBox.critical(self, "Error", f"Failed to save changes: {str(e)}")

    def validate_all_fields(self):
        errors = []
        for i, claim in enumerate(self.claims_data):
            for field in self.REQUIRED_FIELDS:
                if not claim.get(field, "").strip():
                    errors.append(f"Claim {i+1}: {field.replace('_', ' ').title()} is required")
                if field == "billed":
                    value = claim.get(field, "")
                    if value and not re.match(r"^-?\d*\.?\d{0,2}$", value.replace('$', '').replace(',', '')):
                        errors.append(f"Claim {i+1}: Billed must be a valid number")
            for line in claim.get("cpt_data", []):
                if line.get("cpt") and not re.match(r"^\d{5}$", line["cpt"]):
                    errors.append(f"Claim {i+1}, Service Line: CPT code must be 5 digits")
                for key in ["from_date", "to_date"]:
                    if line.get(key) and not re.match(r"^\d{4}-\d{2}-\d{2}$", line[key]):
                        errors.append(f"Claim {i+1}, Service Line: {key.replace('_', ' ').title()} must be in YYYY-MM-DD format")
        return errors

    def create_empty_claim(self):
        empty_service_line = {key: "" for key in self.CPT_REQUIRED_KEYS}
        empty_service_line["Multi"] = "[]"
        empty_service_line["from_date"] = datetime.now().strftime("%Y-%m-%d")
        return {
            "keyername": "", "keyerid": "", "autopopulatestatus": "",
            "Patient_act_no": "", "claim_id": str(self.get_next_claim_id()),
            "Payer_claim": "", "Forwarded_To": "", "Ins": "", "MA": "",
            "Ins_Value": "", "payer_account_number": "", "period_start_date": "",
            "period_end_date": "", "status_code": "", "patient_first_name": "",
            "patient_middle_name": "", "patient_last_name": "", "patient_identifier": "",
            "subscriber_first_name": "", "subscriber_middle_name": "",
            "subscriber_last_name": "", "subscriber_identifier": "",
            "rendering_provider_first_name": "", "rendering_provider_last_name": "",
            "rendering_provider_identifier": "", "cpt_data": [empty_service_line]
        }

    def load_eobs(self):
        from PyQt5.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(self, "Select EOB JSON Files", "", "JSON Files (*.json)")
        if not files:
            return

        progress = QProgressDialog("Loading EOBs...", "Cancel", 0, len(files), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        for i, file in enumerate(files):
            progress.setValue(i)
            try:
                with open(file, 'r') as f:
                    new_data = json.load(f)
                    new_claims = new_data["all_transaction_data"][0]["transaction_data"]["claims_data"]
                    for claim in new_claims:
                        claim["claim_id"] = str(self.get_next_claim_id())
                        self.claims_data.append(claim)
            except Exception as e:
                QMessageBox.warning(self, "Load Error", f"Failed to load {file}: {str(e)}")
        
        progress.setValue(len(files))
        self.refresh_ui()

    def filter_claims(self, text):
        text = text.lower()
        layout = self.claims_container.layout()
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if isinstance(widget, QGroupBox):
                claim_index = i // 2
                if claim_index < len(self.claims_data):
                    claim = self.claims_data[claim_index]
                    matches = (
                        text in claim.get("patient_last_name", "").lower() or
                        text in claim.get("claim_id", "").lower() or
                        text in self.data["all_transaction_data"][0]["transaction_data"].get("payer_name", "").lower()
                    )
                    widget.setVisible(matches)
                    if i + 1 < layout.count():
                        button_widget = layout.itemAt(i + 1).widget()
                        if button_widget:
                            button_widget.setVisible(matches)

    def create_header_section(self):
        group_box = QGroupBox("File and Transaction Information")
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)

        transaction = self.data["all_transaction_data"][0]["transaction_data"]

        # File Information
        file_grid = QGridLayout()
        file_grid.setSpacing(8)
        file_grid.setContentsMargins(15, 15, 15, 15)

        labels_and_fields = [
            ("Job Filename:", QLineEdit(self.data.get("job_filename", "")), "job_filename", "Enter Job Filename", 200),
            ("Out Filename:", QLineEdit(self.data.get("out_filename", "")), "out_filename", "Enter Output Filename", 200),
            ("Job Filepath:", QLineEdit(self.data.get("job_filepath", "")), "job_filepath", "Enter Job Filepath", 200),
            ("ML Status:", QLineEdit(self.data.get("Ml-HM-status", "")), "Ml-HM-status", "Enter ML Status", 120),
            ("Job ID:", QLineEdit(str(self.data.get("job_id", ""))), "job_id", "Enter Job ID", 120),
            ("Client Name:", QLineEdit(self.data.get("client_name", "")), "client_name", "Enter Client Name", 200),
            ("Claim Count:", QLineEdit(self.data.get("claimcount", "")), "claimcount", "Enter Claim Count", 120),
            ("Auto Populate:", QLineEdit(self.data.get("autopopulatestatus", "")), "autopopulatestatus", "Enter Auto Populate Status", 120),
        ]

        prev_field = None
        for i, (label_text, field, key, placeholder, width) in enumerate(labels_and_fields):
            row = i // 4
            col = (i % 4) * 2
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if key in self.REQUIRED_FIELDS:
                label.setProperty("required", True)
            field.setMinimumWidth(width)
            field.setPlaceholderText(placeholder)
            field.setToolTip(f"Enter {label_text.lower().rstrip(':')}")
            field.textChanged.connect(lambda text, k=key, f=field: self.track_header_change(k, text, f))
            if key in self.completers:
                field.setCompleter(self.completers[key])
            file_grid.addWidget(label, row, col)
            file_grid.addWidget(field, row, col + 1)
            if prev_field:
                self.setTabOrder(prev_field, field)
            prev_field = field

        main_layout.addLayout(file_grid)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        # Transaction Details
        trans_label = QLabel("Transaction Details")
        trans_label.setProperty("sectionHeader", True)
        main_layout.addWidget(trans_label)

        trans_grid = QGridLayout()
        trans_grid.setSpacing(8)

        file_labels_and_fields = [
            ("Transaction ID:", QLineEdit(str(transaction["transaction_id"])), "transaction_id", "Enter Transaction ID", 120),
            ("Job ID:", QLineEdit(str(transaction["job_id"])), "job_id", "Enter Job ID", 120),
            ("NPI:", QLineEdit(transaction["npi"]), "npi", "Enter NPI", 120),
            ("Default NPI:", QLineEdit(transaction["Default_npi"]), "Default_npi", "Enter Default NPI", 120),
            ("Tax ID:", QLineEdit(transaction["tax_id"]), "tax_id", "Enter Tax ID", 120),
            ("Payment Method:", QLineEdit(transaction["payment_method"]), "payment_method", "Enter Payment Method", 150),
            ("Check Number:", QLineEdit(transaction["check_number"]), "check_number", "Enter Check Number", 120),
            ("Check Date:", QLineEdit(transaction["check_date"]), "check_date", "Enter Check Date (YYYY-MM-DD)", 120),
            ("Check Amount:", QLineEdit(transaction["check_amount"]), "check_amount", "Enter Check Amount", 120),
            ("Remaining Amount:", QLineEdit(transaction["remaining_amount"]), "remaining_amount", "Enter Remaining Amount", 120),
            ("Payee Name:", QLineEdit(transaction["payee_name"]), "payee_name", "Enter Payee Name", 200),
            ("Payer Name:", QLineEdit(transaction["payer_name"]), "payer_name", "Enter Payer Name", 200),
        ]

        for i, (label_text, field, key, placeholder, width) in enumerate(file_labels_and_fields):
            row = i // 4
            col = (i % 4) * 2
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if key in self.REQUIRED_FIELDS:
                label.setProperty("required", True)
            field.setMinimumWidth(width)
            field.setPlaceholderText(placeholder)
            field.setToolTip(f"Enter {label_text.lower().rstrip(':')}")
            field.textChanged.connect(lambda text, k=key, f=field: self.track_header_change(k, text, f))
            if key in self.completers:
                field.setCompleter(self.completers[key])
            trans_grid.addWidget(label, row, col)
            trans_grid.addWidget(field, row, col + 1)
            if prev_field:
                self.setTabOrder(prev_field, field)
            prev_field = field

        main_layout.addLayout(trans_grid)
        group_box.setLayout(main_layout)
        return group_box

    def create_claim_section(self, claim_data, claim_number, is_empty=False):
        if is_empty:
            title = f"New Claim {claim_number}"
        else:
            title = f"Claim {claim_number}: {claim_data.get('patient_last_name', '')}, {claim_data.get('patient_first_name', '')} - {claim_data.get('Patient_act_no', '')}"
        
        claim_group = QGroupBox(title)
        claim_layout = QVBoxLayout()
        claim_layout.setSpacing(12)
        claim_layout.setContentsMargins(15, 15, 15, 15)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(8)

        field_names = [
            "Patient_act_no", "claim_id", "patient_last_name", "patient_first_name",
            "payer_account_number", "status_code", "period_start_date", "period_end_date"
        ]
        label_texts = [
            "Patient Account No:", "Claim ID:", "Patient Last Name:", "Patient First Name:",
            "Payer Account Number:", "Status Code:", "Period Start Date:", "Period End Date:"
        ]
        placeholders = [
            "Enter Patient Account No", "Enter Claim ID", "Enter Patient Last Name", "Enter Patient First Name",
            "Enter Payer Account Number", "Enter Status Code", "Enter Period Start Date (YYYY-MM-DD)", "Enter Period End Date (YYYY-MM-DD)"
        ]
        widths = [150, 120, 150, 150, 150, 120, 120, 120]

        labels_and_fields = []
        prev_field = None
        for i, (field_name, label_text, placeholder, width) in enumerate(zip(field_names, label_texts, placeholders, widths)):
            if is_empty:
                value = "" if field_name != "claim_id" else str(self.get_next_claim_id())
            else:
                value = str(claim_data[field_name]) if field_name == "claim_id" else claim_data[field_name]

            field = QLineEdit(value)
            field.setObjectName(f"claim_{claim_number}_{field_name}")
            field.setPlaceholderText(placeholder)
            field.setToolTip(f"Enter {label_text.lower().rstrip(':')}")
            field.textChanged.connect(lambda text, fn=field_name, cn=claim_number, f=field: self.track_field_change(cn, fn, text, f))
            if field_name in self.completers:
                field.setCompleter(self.completers[field_name])
            labels_and_fields.append((label_text, field, field_name, width))

        for i, (label_text, field, field_name, width) in enumerate(labels_and_fields):
            row = i // 4
            col = (i % 4) * 2
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if field_name in self.REQUIRED_FIELDS:
                label.setProperty("required", True)
            field.setMinimumWidth(width)
            grid_layout.addWidget(label, row, col)
            grid_layout.addWidget(field, row, col + 1)
            if prev_field:
                self.setTabOrder(prev_field, field)
            prev_field = field

        claim_layout.addLayout(grid_layout)

        service_label = QLabel("Service Lines")
        service_label.setProperty("sectionHeader", True)
        claim_layout.addWidget(service_label)

        service_table = QTableWidget()
        service_table.setAlternatingRowColors(True)
        service_table.setColumnCount(14)  # Reduced columns for visibility
        service_table.setHorizontalHeaderLabels([
            "From Date", "To Date", "CPT", "Units", "Billed", "Allowed", 
            "Deduct", "CoIns", "CoPay", "Paid", "Balance", "Group Code", "Remark", "Multi"
        ])
        service_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        if is_empty:
            service_table.setRowCount(1)
            for col in range(service_table.columnCount()):
                item = QTableWidgetItem("")
                if col >= 4:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                service_table.setItem(0, col, item)
        else:
            cpt_data = claim_data["cpt_data"]
            service_table.setRowCount(len(cpt_data))
            for i, line in enumerate(cpt_data):
                for key in self.CPT_REQUIRED_KEYS:
                    if key not in line:
                        line[key] = "" if key != "Multi" else "[]"
                selected_keys = ["from_date", "to_date", "cpt", "units", "billed", "allowed", 
                               "deduct", "coins", "copay", "paid", "balance", "group_code", "rmk", "Multi"]
                for j, key in enumerate(selected_keys[:-1]):
                    item = QTableWidgetItem(line[key])
                    if j >= 4:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    service_table.setItem(i, j, item)
                button = QPushButton()
                button.setIcon(QIcon('edit_icon.png') if os.path.exists('edit_icon.png') else QIcon())
                button.clicked.connect(lambda checked, row=i: self.open_multi_dialog(service_table, row, claim_number))
                service_table.setCellWidget(i, 13, button)
                service_table.setItem(i, 13, QTableWidgetItem(line["Multi"]))

        self.add_totals_row(service_table)

        header = service_table.horizontalHeader()
        # header = service_table.horizontalHeader()
        for col in range(service_table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Stretch)

        service_table.setEditTriggers(QAbstractItemView.DoubleClicked | 
                                    QAbstractItemView.EditKeyPressed |
                                    QAbstractItemView.AnyKeyPressed)
        service_table.setObjectName(f"service_table_{claim_number}")
        service_table.itemChanged.connect(lambda item, cn=claim_number, f=service_table: self.on_service_item_changed(service_table, cn, item, f))

        add_line_button = QPushButton("Add Line")
        add_line_button.setIcon(QIcon('add_icon.png') if os.path.exists('add_icon.png') else QIcon())
        remove_line_button = QPushButton("Remove Line")
        remove_line_button.setIcon(QIcon('delete_icon.png') if os.path.exists('delete_icon.png') else QIcon())
        add_line_button.clicked.connect(lambda: self.add_service_line(service_table))
        remove_line_button.clicked.connect(lambda: self.remove_service_line(service_table))

        button_layout = QHBoxLayout()
        button_layout.addWidget(add_line_button)
        button_layout.addWidget(remove_line_button)
        button_layout.addStretch()

        row_height = 32
        service_table.verticalHeader().setDefaultSectionSize(row_height)
        header_height = service_table.horizontalHeader().height()
        table_height = (row_height * 5) + header_height + 15
        service_table.setMinimumHeight(table_height)
        service_table.setMaximumHeight(table_height)

        claim_layout.addWidget(service_table)
        claim_layout.addLayout(button_layout)

        claim_group.setLayout(claim_layout)
        return claim_group

    def add_totals_row(self, table):
        last_row = table.rowCount() - 1
        if last_row >= 0 and table.item(last_row, 0) and table.item(last_row, 0).text().strip().upper() == "TOTALS":
            table.removeRow(last_row)

        current_row_count = table.rowCount()
        table.insertRow(current_row_count)

        bold_font = QFont()
        bold_font.setWeight(700)

        table.blockSignals(True)
        try:
            totals_label = QTableWidgetItem("TOTALS")
            totals_label.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            totals_label.setFont(bold_font)
            totals_label.setFlags(Qt.ItemIsEnabled)
            totals_label.setData(Qt.UserRole, "totalsRow")
            table.setItem(current_row_count, 0, totals_label)

            for col in range(1, table.columnCount()):
                item = QTableWidgetItem("")
                item.setFont(bold_font)
                item.setFlags(Qt.ItemIsEnabled)
                item.setData(Qt.UserRole, "totalsRow")
                if col >= 4:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(current_row_count, col, item)
        finally:
            table.blockSignals(False)

        self.calculate_totals_for_table(table)

    def calculate_totals_for_table(self, table):
        totals_row = table.rowCount() - 1
        if totals_row < 0:
            return

        financial_cols = [4, 5, 6, 7, 8, 9, 10]

        table.blockSignals(True)
        try:
            for col in financial_cols:
                total = 0.0
                for row in range(totals_row):
                    item = table.item(row, col)
                    if item and item.text():
                        try:
                            value_text = item.text().replace('$', '').replace(',', '')
                            value = float(value_text) if value_text.strip() else 0.0
                            total += value
                        except (ValueError, TypeError):
                            continue
                total_str = f"${total:.2f}" if total != 0 else ""
                total_item = QTableWidgetItem(total_str)
                total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                total_item.setFont(QFont("", weight=700))
                total_item.setFlags(Qt.ItemIsEnabled)
                table.setItem(totals_row, col, total_item)
        finally:
            table.blockSignals(False)

    def on_service_item_changed(self, table, claim_number, item, field):
        self.track_service_change(claim_number, item, field)
        self.calculate_totals_for_table(table)

    def add_service_line(self, table):
        table.insertRow(table.rowCount() - 1)
        row = table.rowCount() - 2
        for col in range(table.columnCount()):
            if col == 13:
                claim_number = int(table.objectName().split("_")[-1])
                button = QPushButton("View/Edit")
                button.setIcon(QIcon('edit_icon.png') if os.path.exists('edit_icon.png') else QIcon())
                button.clicked.connect(lambda checked, r=row: self.open_multi_dialog(table, r, claim_number))
                table.setCellWidget(row, col, button)
                table.setItem(row, col, QTableWidgetItem("[]"))
            else:
                value = datetime.now().strftime("%Y-%m-%d") if col == 0 else ""
                item = QTableWidgetItem(value)
                if col >= 4:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(row, col, item)
        self.calculate_totals_for_table(table)

    def remove_service_line(self, table):
        selected_items = table.selectedItems()
        if not selected_items:
            return
        selected_row = selected_items[0].row()
        totals_row = table.rowCount() - 1
        if selected_row != totals_row:
            table.removeRow(selected_row)
            self.calculate_totals_for_table(table)

    def open_multi_dialog(self, table, row, claim_number):
        multi_item = table.item(row, 13)
        current_data = "[]"
        if multi_item:
            current_data = multi_item.text()
        else:
            table.setItem(row, 13, QTableWidgetItem("[]"))
        
        dialog = MultiDataDialog(current_data, parent=table)
        if dialog.exec_():
            updated_data = dialog.get_data()
            table.blockSignals(True)
            try:
                table.setItem(row, 13, QTableWidgetItem(updated_data))
            finally:
                table.blockSignals(False)
            
            button = table.cellWidget(row, 13)
            if button:
                data_list = json.loads(updated_data)
                button.setText("View/Edit" + (" (*)" if data_list else ""))
            
            self.track_service_change(claim_number, table.item(row, 13))

    def get_next_claim_id(self):
        max_id = 0
        for claim in self.claims_data:
            try:
                claim_id = int(claim.get('claim_id', 0))
                if claim_id > max_id:
                    max_id = claim_id
            except (ValueError, TypeError):
                pass
        return max_id + 1

    def create_claims_container(self):
        claims_container = QWidget()
        claims_container.setObjectName("claimsContainer")
        claims_layout = QVBoxLayout()
        claims_layout.setSpacing(15)
        
        for i, claim_data in enumerate(self.claims_data):
            claim_section = self.create_claim_section(claim_data, i + 1)
            claims_layout.addWidget(claim_section)
            
            button_widget = QWidget()
            button_layout = QHBoxLayout()
            button_layout.setContentsMargins(0, 0, 0, 0)
            
            add_button = QPushButton("+")
            add_button.setFixedSize(40, 40)
            add_button.setProperty("addButton", True)
            add_button.clicked.connect(lambda checked, l=claims_layout, b=add_button: self.add_new_claim(l, b))
            
            delete_button = QPushButton("-")
            delete_button.setFixedSize(40, 40)
            delete_button.setProperty("deleteButton", True)
            delete_button.clicked.connect(lambda checked, l=claims_layout, b=delete_button: self.delete_claim(l, b))
            
            button_layout.addStretch()
            button_layout.addWidget(add_button)
            button_layout.addWidget(delete_button)
            button_layout.addStretch()
            
            button_widget.setLayout(button_layout)
            claims_layout.addWidget(button_widget)
        
        claims_layout.addStretch()
        claims_container.setLayout(claims_layout)
        return claims_container

    def delete_claim(self, layout, button):
        if len(self.claims_data) <= 1:
            QMessageBox.warning(self, "Warning", "Cannot delete the last claim")
            return
        
        button_widget = button.parent() if button else None
        button_index = -1
        for i in range(layout.count()):
            if button_widget and layout.itemAt(i).widget() == button_widget:
                button_index = i
                break
        else:
            selected = [w for w in layout.children()[0].findChildren(QGroupBox) if w.underMouse()]
            if selected:
                button_index = layout.indexOf(selected[0]) + 1
        
        if button_index > 0:
            claim_widget = layout.itemAt(button_index - 1).widget()
            if not isinstance(claim_widget, QGroupBox):
                QMessageBox.critical(self, "Error", "No claim found above the button")
                return
            claim_index = 0
            for i in range(button_index):
                if isinstance(layout.itemAt(i).widget(), QGroupBox):
                    claim_index += 1
            claim_index -= 1
            
            if claim_index < 0 or claim_index >= len(self.claims_data):
                QMessageBox.critical(self, "Error", "Invalid claim index")
                return
            
            layout.removeWidget(claim_widget)
            if button_widget:
                layout.removeWidget(button_widget)
            claim_widget.deleteLater()
            if button_widget:
                button_widget.deleteLater()
            
            deleted_claim = self.claims_data[claim_index]
            
            if "claims_structural" not in self.changes:
                self.changes["claims_structural"] = []
            self.changes["claims_structural"].append({"action": "deleted", "index": claim_index, "data": deleted_claim})
            
            self.update_claim_numbers(layout)
            self.update_button_indices(layout)
            self.refresh_ui()
        else:
            QMessageBox.critical(self, "Error", "No claim found to delete")

    def update_claim_numbers(self, layout):
        claim_count = 0
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if isinstance(widget, QGroupBox) and widget.title().startswith("Claim"):
                claim_count += 1
                if claim_count - 1 < len(self.claims_data):
                    claim_data = self.claims_data[claim_count - 1]
                    title = f"Claim {claim_count}: {claim_data.get('patient_last_name', '')}, {claim_data.get('patient_first_name', '')} - {claim_data.get('Patient_act_no', '')}"
                    widget.setTitle(title)

    def add_new_claim(self, layout, button):
        button_widget = button.parent() if button else None
        button_index = -1
        for i in range(layout.count()):
            if button_widget and layout.itemAt(i).widget() == button_widget:
                button_index = i
                break
        else:
            button_index = layout.count()
        
        new_claim_number = len(self.claims_data) + 1
        new_claim = self.create_claim_section({}, new_claim_number, is_empty=True)
        
        empty_claim_data = self.create_empty_claim()
        
        claim_index = 0
        for i in range(button_index):
            if isinstance(layout.itemAt(i).widget(), QGroupBox):
                claim_index += 1
        
        layout.insertWidget(button_index, new_claim)
        
        if "claims_structural" not in self.changes:
            self.changes["claims_structural"] = []
        self.changes["claims_structural"].append({"action": "added", "index": claim_index, "data": empty_claim_data})
        
        self.update_claim_numbers(layout)
        self.update_button_indices(layout)
        self.refresh_ui()

    def update_button_indices(self, layout):
        i = 0
        while i < layout.count():
            widget = layout.itemAt(i).widget()
            if widget and isinstance(widget, QWidget) and widget.layout():
                button_layout = widget.layout()
                is_button_widget = False
                for j in range(button_layout.count()):
                    item = button_layout.itemAt(j)
                    if item and item.widget() and isinstance(item.widget(), QPushButton):
                        button_text = item.widget().text()
                        if button_text in ["+", "-"]:
                            is_button_widget = True
                            break
                if is_button_widget:
                    layout.removeWidget(widget)
                    widget.deleteLater()
                    continue
            i += 1
        
        claim_count = 0
        i = 0
        while i < layout.count():
            widget = layout.itemAt(i).widget()
            if isinstance(widget, QGroupBox):
                claim_count += 1
                button_widget = QWidget()
                button_layout = QHBoxLayout()
                button_layout.setContentsMargins(0, 0, 0, 0)
                
                add_button = QPushButton("+")
                add_button.setFixedSize(40, 40)
                add_button.setProperty("addButton", True)
                add_button.clicked.connect(lambda checked, l=layout, b=add_button: self.add_new_claim(l, b))
                
                delete_button = QPushButton("-")
                delete_button.setFixedSize(40, 40)
                delete_button.setProperty("deleteButton", True)
                delete_button.clicked.connect(lambda checked, l=layout, b=delete_button: self.delete_claim(l, b))
                
                button_layout.addStretch()
                button_layout.addWidget(add_button)
                button_layout.addWidget(delete_button)
                button_layout.addStretch()
                
                button_widget.setLayout(button_layout)
                layout.insertWidget(i + 1, button_widget)
                i += 2
            else:
                i += 1

    def refresh_ui(self):
        content_layout = self.centralWidget().layout().itemAt(0).widget().widget().layout()
        new_claims_container = self.create_claims_container()
        content_layout.replaceWidget(self.claims_container, new_claims_container)
        self.claims_container.deleteLater()
        self.claims_container = new_claims_container

        transaction_data = self.data["all_transaction_data"][0]["transaction_data"]
        new_summary_widget = self.create_summary_section(transaction_data)
        content_layout.replaceWidget(self.summary_widget, new_summary_widget)
        self.summary_widget.deleteLater()
        self.summary_widget = new_summary_widget

    def create_summary_section(self, transaction_data):
        group_box = QGroupBox("Payment Summary")
        layout = QVBoxLayout()
        layout.setSpacing(12)

        summary_table = QTableWidget(1, 5)
        summary_table.setObjectName("summaryTable")
        summary_table.setHorizontalHeaderLabels([
            "Total Claims", "Total Billed", "Total Allowed", "Total Paid", "Check Amount"
        ])
        summary_table.verticalHeader().setVisible(False)
        summary_table.setAlternatingRowColors(True)
        summary_table.setFixedHeight(100)
        summary_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        total_claims = len(transaction_data["claims_data"])
        total_billed = 0.0
        total_allowed = 0.0
        total_paid = 0.0

        for claim in transaction_data["claims_data"]:
            for line in claim["cpt_data"]:
                try:
                    if line["billed"]:
                        total_billed += float(line["billed"])
                    if line["allowed"]:
                        total_allowed += float(line["allowed"])
                    if line["paid"]:
                        total_paid += float(line["paid"])
                except ValueError:
                    pass

        summary_table.setItem(0, 0, QTableWidgetItem(str(total_claims)))
        
        for col, value in enumerate([total_billed, total_allowed, total_paid]):
            item = QTableWidgetItem(f"${value:.2f}")
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item.setFlags(Qt.ItemIsEnabled)
            summary_table.setItem(0, col + 1, item)

        try:
            check_amount = float(transaction_data['check_amount'])
            check_amount_item = QTableWidgetItem(f"${check_amount:.2f}")
        except (ValueError, TypeError):
            check_amount_item = QTableWidgetItem(transaction_data['check_amount'])
        check_amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        check_amount_item.setFlags(Qt.ItemIsEnabled)
        summary_table.setItem(0, 4, check_amount_item)

        header = summary_table.horizontalHeader()
        for i in range(5):
            header.setSectionResizeMode(i, QHeaderView.Stretch)

        layout.addWidget(summary_table)

        try:
            check_amount = float(transaction_data['check_amount'])
            if abs(check_amount - total_paid) > 0.01:
                warning_label = QLabel(f"WARNING: Check amount (${check_amount:.2f}) does not match total paid amount (${total_paid:.2f})")
                warning_label.setProperty("warning", True)
                layout.addWidget(warning_label)
        except ValueError:
            pass

        group_box.setLayout(layout)
        return group_box

class MultiDataDialog(QDialog):
    def __init__(self, multi_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Adjustment Data")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self.multi_data = json.loads(multi_data) if multi_data and multi_data != "[]" else []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)

        title_label = QLabel("Edit Adjustment Data")
        title_label.setProperty("headerBar", True)
        layout.addWidget(title_label)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Group Code", "Reason Code", "Amount", "Remark"])
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.table.setRowCount(len(self.multi_data))
        for row, data in enumerate(self.multi_data):
            for col, key in enumerate(["group_code", "reason_code", "amount", "remark"]):
                item = QTableWidgetItem(data.get(key, ""))
                if col == 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, col, item)

        header = self.table.horizontalHeader()
        column_widths = [100, 100, 120, 150]
        for col, width in enumerate(column_widths):
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, width)

        self.table.verticalHeader().setDefaultSectionSize(32)
        table_height = (32 * 5) + self.table.horizontalHeader().height() + 15
        self.table.setMinimumHeight(table_height)
        self.table.setMaximumHeight(table_height)

        self.table.itemChanged.connect(self.validate_table_item)
        layout.addWidget(self.table)

        button_layout = QHBoxLayout()
        add_button = QPushButton("Add Row")
        add_button.setProperty("addButton", True)
        add_button.setIcon(QIcon('add_icon.png') if os.path.exists('add_icon.png') else QIcon())
        add_button.clicked.connect(self.add_row)
        button_layout.addWidget(add_button)

        remove_button = QPushButton("Remove Row")
        remove_button.setProperty("deleteButton", True)
        remove_button.setIcon(QIcon('delete_icon.png') if os.path.exists('delete_icon.png') else QIcon())
        remove_button.clicked.connect(self.remove_row)
        button_layout.addWidget(remove_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        action_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.setProperty("text", "Save")
        save_button.setIcon(QIcon('save_icon.png') if os.path.exists('save_icon.png') else QIcon())
        save_button.clicked.connect(self.save_and_close)
        action_layout.addWidget(save_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        action_layout.addWidget(cancel_button)
        action_layout.addStretch()
        layout.addLayout(action_layout)

        self.setLayout(layout)

        from PyQt5.QtGui import QKeySequence
        from PyQt5.QtWidgets import QShortcut
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_and_close)

    def validate_table_item(self, item):
        row = item.row()
        col = item.column()
        headers = ["group_code", "reason_code", "amount", "remark"]
        field_name = headers[col]
        value = item.text()

        error = None
        if field_name == "amount" and value:
            if not re.match(r"^-?\d*\.?\d{0,2}$", value.replace('$', '').replace(',', '')):
                error = "Amount must be a valid number"
                item.setToolTip(error)
                item.setBackground(Qt.red)
                return
        elif field_name in ["group_code", "reason_code"] and value and not re.match(r"^[A-Za-z0-9]{1,5}$", value):
            error = f"{field_name.replace('_', ' ').title()} must be 1-5 alphanumeric characters"
            item.setToolTip(error)
            item.setBackground(Qt.red)
            return

        item.setToolTip(f"Enter {field_name.replace('_', ' ').title()}")
        item.setBackground(Qt.transparent)

    def add_row(self):
        row_count = self.table.rowCount()
        self.table.insertRow(row_count)
        for col in range(4):
            item = QTableWidgetItem("")
            if col == 2:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_count, col, item)

    def remove_row(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            return
        selected_row = selected_items[0].row()
        self.table.removeRow(selected_row)

    def save_and_close(self):
        errors = []
        new_data = []
        for row in range(self.table.rowCount()):
            row_data = {}
            for col, key in enumerate(["group_code", "reason_code", "amount", "remark"]):
                item = self.table.item(row, col)
                value = item.text() if item else ""
                row_data[key] = value
                if key == "amount" and value and not re.match(r"^-?\d*\.?\d{0,2}$", value.replace('$', '').replace(',', '')):
                    errors.append(f"Row {row + 1}: Amount must be a valid number")
                elif key in ["group_code", "reason_code"] and value and not re.match(r"^[A-Za-z0-9]{1,5}$", value):
                    errors.append(f"Row {row + 1}: {key.replace('_', ' ').title()} must be 1-5 alphanumeric characters")
            new_data.append(row_data)

        if errors:
            QMessageBox.critical(self, "Validation Error", "Please fix the following errors:\n" + "\n".join(errors))
            return

        self.multi_data = new_data
        self.accept()

    def get_data(self):
        return json.dumps(self.multi_data)
    
def main():
    try:
        with open('jobjson.json', 'r') as file:
            data = json.load(file)
        
        app = QApplication(sys.argv)
        app.setStyle(QStyleFactory.create('Fusion'))
        ex = ClaimsViewer(data, input_file='jobjson.json')
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()