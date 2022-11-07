import subprocess
from pathlib import Path
from typing import Any, ClassVar

from qtpy.QtWidgets import (QLabel, QListWidget, QListWidgetItem,
                            QTableWidget, QTableWidgetItem, QWidget)
from pcdsutils.qt import DesignerDisplay

from .ftp_data import download_file_json_dict, list_file_info


class PMPSManagerGui(DesignerDisplay, QWidget):
    filename = Path(__file__).parent / 'tables.ui'

    title_label: QLabel
    plc_label: QLabel
    plc_table: QTableWidget
    device_label: QLabel
    device_list: QListWidget
    param_label: QLabel
    param_table: QTableWidget

    plc_columns: ClassVar[list[str]] = [
        'plc name',
        'status',
        'file last uploaded',
    ]
    param_columns: ClassVar[list[str]] = [
        'parameter',
        'value',
    ]
    param_dict: dict[str, dict[str, Any]]

    def __init__(self, plc_hostnames: list[str]):
        self.setup_table_columns()
        self.plc_row_map = {}
        for hostname in plc_hostnames:
            self.add_plc(hostname)
        self.device_list.itemActivated.connect(self.device_selected)
        self.plc_table.cellActivated.connect(self.plc_selected)

    def setup_table_columns(self):
        """
        Set the column headers on the plc and parameter tables.
        """
        self.plc_table.setColumnCount(len(self.plc_columns))
        self.plc_table.setVerticalHeaderLabels(self.plc_columns)
        self.param_table.setColumnCount(len(self.param_columns))
        self.param_table.setVerticalHeaderLabels(self.param_columns)

    def add_plc(self, hostname: str):
        """
        Add a PLC row in the table on the left.
        """
        row = self.plc_table.rowCount()
        self.plc_table.insertRow(row)
        name_item = QTableWidgetItem(text=hostname)
        status_item = QTableWidgetItem()
        upload_time_item = QTableWidgetItem()
        self.plc_table.setItem(row, 0, name_item)
        self.plc_table.setItem(row, 1, status_item)
        self.plc_table.setItem(row, 2, upload_time_item)
        self.update_plc_row(row)

    def update_plc_row(self, row: int):
        """
        Update the status information in the PLC table for one row.
        """
        hostname = self.plc_table.item(row, 0).text()
        if check_server_online(hostname):
            text = 'online'
        else:
            text = 'offline'
        self.plc_table.item(row, 1).setText(text)
        try:
            info = list_file_info(hostname)
        except Exception:
            info = []
        text = 'no file found'
        for file_info in info:
            if file_info.filename == f'{hostname}.json':
                text = file_info.create_time.ctime()
                break
        self.plc_table.item(row, 2).setText(text)

    def fill_device_list(self, hostname: str):
        """
        Cache the PLC's saved db and populate the device list.
        """
        self.device_list.clear()
        self.param_table.clear()
        try:
            json_info = download_file_json_dict(hostname, f'{hostname}.json')
        except Exception:
            json_info = {}
        try:
            self.param_dict = json_info[hostname]
        except KeyError:
            self.param_dict = {}
        for device_name in self.param_dict:
            self.device_list.addItem(device_name)

    def fill_parameter_table(self, device_name: str):
        """
        Use the cached db to show a single device's parameters in the table.
        """
        self.param_table.clear()
        for key, value in self.param_dict[device_name].items():
            row = self.param_table.rowCount()
            self.param_table.insertRow(row)
            key_item = QTableWidgetItem(text=key)
            value_item = QTableWidgetItem(text=value)
            self.param_table.setItem(row, 0, key_item)
            self.param_table.setItem(row, 1, value_item)

    def plc_selected(self, row: int, col: int):
        """
        When a plc is selected, reset and seed the device list.
        """
        self.update_plc_row()
        hostname = self.plc_table.item(row, 0).text()
        self.fill_device_list(hostname)

    def device_selected(self, item: QListWidgetItem):
        """
        When a device is selected, reset and seed the parameter list.
        """
        self.fill_parameter_table(item.text())


def check_server_online(hostname: str):
    try:
        return not subprocess.call(['ping', '-c', '1', hostname])
    except Exception:
        return False