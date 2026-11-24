"""
ChipDocs.org KiCad 7/8/9 PCM Action Plugin (`org.chipdocs.kicad`)
Search chipdocs.org directly inside KiCad PCB Editor and download verified
.kicad_mod footprints, .kicad_sym symbols & 3D .step models into ${KIPRJMOD}/chipdocs_libs/.
"""

import json
import os
import re
import urllib.parse
import urllib.request
import webbrowser

import pcbnew
import wx

API_BASE = "https://chipdocs.org"


def _safe_name(val: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]+", "_", (val or "part").strip()).strip("_") or "part"


class ChipDocsDialog(wx.Dialog):
    def __init__(self, parent, project_dir: str):
        super().__init__(parent, title="ChipDocs.org — Free IPC-7351B CAD Library Search", size=(760, 480))
        self.project_dir = project_dir
        self.results = []

        vbox = wx.BoxSizer(wx.VERTICAL)

        # Search Row
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.search_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_input.SetHint("Enter MPN, e.g. STM32F103C8T6, ESP32-S3, CH340G, LM2596...")
        self.search_btn = wx.Button(self, label="Search chipdocs.org")
        hbox.Add(self.search_input, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=8)
        hbox.Add(self.search_btn, flag=wx.ALIGN_CENTER_VERTICAL)
        vbox.Add(hbox, flag=wx.EXPAND | wx.ALL, border=10)

        # Results List
        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.list_ctrl.InsertColumn(0, "MPN", width=180)
        self.list_ctrl.InsertColumn(1, "Manufacturer", width=155)
        self.list_ctrl.InsertColumn(2, "Package", width=130)
        self.list_ctrl.InsertColumn(3, "Pins", width=55)
        self.list_ctrl.InsertColumn(4, "Pitch", width=65)
        self.list_ctrl.InsertColumn(5, "3D STEP", width=75)
        vbox.Add(self.list_ctrl, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)

        # Status + Action Buttons
        self.status_lbl = wx.StaticText(self, label=f"Target folder: {os.path.join(project_dir, 'chipdocs_libs')}")
        vbox.Add(self.status_lbl, flag=wx.EXPAND | wx.ALL, border=10)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.dl_btn = wx.Button(self, label="Download Symbol + Footprint + 3D STEP")
        self.web_btn = wx.Button(self, label="Open Pinout & Equivalents on Web")
        self.close_btn = wx.Button(self, wx.ID_CLOSE, label="Close")
        btn_row.Add(self.dl_btn, flag=wx.RIGHT, border=8)
        btn_row.Add(self.web_btn, flag=wx.RIGHT, border=8)
        btn_row.AddStretchSpacer()
        btn_row.Add(self.close_btn)
        vbox.Add(btn_row, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        self.SetSizer(vbox)

        self.search_btn.Bind(wx.EVT_BUTTON, self.on_search)
        self.search_input.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        self.dl_btn.Bind(wx.EVT_BUTTON, self.on_download)
        self.web_btn.Bind(wx.EVT_BUTTON, self.on_open_web)
        self.close_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))

    def on_search(self, _event):
        q = self.search_input.GetValue().strip()
        if not q:
            return
        self.status_lbl.SetLabel(f"Searching chipdocs.org for '{q}'...")
        wx.Yield()
        try:
            url = f"{API_BASE}/api/v1/components/search?q={urllib.parse.quote(q)}&limit=25"
            req = urllib.request.Request(url, headers={"User-Agent": "ChipDocs-KiCad-Plugin/1.0"})
            data = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8"))
            self.results = data.get("components", [])
            self.list_ctrl.DeleteAllItems()
            for idx, item in enumerate(self.results):
                self.list_ctrl.InsertItem(idx, str(item.get("mpn") or ""))
                self.list_ctrl.SetItem(idx, 1, str(item.get("canonical_manufacturer") or item.get("manufacturer") or ""))
                self.list_ctrl.SetItem(idx, 2, str(item.get("package") or ""))
                self.list_ctrl.SetItem(idx, 3, str(item.get("pin_count") or 0))
                pitch = item.get("pitch_mm")
                self.list_ctrl.SetItem(idx, 4, f"{pitch}mm" if pitch else "-")
                self.list_ctrl.SetItem(idx, 5, "Ready" if item.get("has_3d_glb") else "Auto")
            self.status_lbl.SetLabel(f"Found {len(self.results)} verified components.")
        except Exception as exc:
            self.status_lbl.SetLabel(f"Search error: {exc}")

    def _selected_item(self):
        idx = self.list_ctrl.GetFirstSelected()
        if idx < 0 or idx >= len(self.results):
            wx.MessageBox("Select a component from the list first.", "ChipDocs", wx.OK | wx.ICON_INFORMATION)
            return None
        return self.results[idx]

    def on_download(self, _event):
        item = self._selected_item()
        if not item:
            return
        pid = urllib.parse.quote(item["lcsc_part"])
        sname = _safe_name(item["mpn"])
        lib_root = os.path.join(self.project_dir, "chipdocs_libs")
        pretty_dir = os.path.join(lib_root, "chipdocs.pretty")
        models_dir = os.path.join(lib_root, "3dmodels")
        os.makedirs(pretty_dir, exist_ok=True)
        os.makedirs(models_dir, exist_ok=True)

        targets = [
            (f"{API_BASE}/api/v1/assets/{pid}/cleanroom/footprint.kicad_mod", os.path.join(pretty_dir, f"{sname}.kicad_mod")),
            (f"{API_BASE}/api/v1/assets/{pid}/cleanroom/symbol.kicad_sym", os.path.join(lib_root, f"{sname}.kicad_sym")),
            (f"{API_BASE}/api/v1/assets/{pid}/cleanroom/model.step", os.path.join(models_dir, f"{sname}.step")),
        ]
        saved = []
        for url, dest in targets:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "ChipDocs-KiCad-Plugin/1.0"})
                raw = urllib.request.urlopen(req, timeout=15).read()
                with open(dest, "wb") as f:
                    f.write(raw)
                saved.append(os.path.basename(dest))
            except Exception as exc:
                saved.append(f"{os.path.basename(dest)} (err: {exc})")
        self.status_lbl.SetLabel(f"Saved to {lib_root}: {', '.join(saved)}")
        wx.MessageBox(
            f"Downloaded to:\n{lib_root}\n\nFiles:\n- " + "\n- ".join(saved),
            "ChipDocs Library Installed",
            wx.OK | wx.ICON_INFORMATION,
        )

    def on_open_web(self, _event):
        item = self._selected_item()
        if not item:
            return
        mpn_seg = urllib.parse.quote(re.sub(r"[^A-Za-z0-9_.\-]+", "-", item["mpn"]).strip("-"))
        webbrowser.open(f"{API_BASE}/parts/{mpn_seg}")


class ChipDocsLibraryPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "ChipDocs Library Downloader"
        self.category = "Component Libraries"
        self.description = "Search & install verified IPC-7351B footprints, symbols & 3D STEP models from chipdocs.org"
        self.show_toolbar_button = True

    def Run(self):
        board = pcbnew.GetBoard()
        board_file = board.GetFileName() if board else ""
        proj_dir = os.path.dirname(board_file) if board_file else os.path.expanduser("~")
        dlg = ChipDocsDialog(None, proj_dir)
        dlg.ShowModal()
        dlg.Destroy()
