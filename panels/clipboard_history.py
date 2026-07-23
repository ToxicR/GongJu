# -*- coding: utf-8 -*-
"""本机剪贴板历史。"""
import customtkinter as ctk


class ClipboardHistoryPanel(ctk.CTkFrame):
    title = "剪贴板历史"

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._history = []
        self._last = None
        self._poll_id = None
        self._build()

    def _build(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(8, 8))
        ctk.CTkLabel(head, text="剪贴板历史", font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="清空历史", width=90, fg_color="gray", command=self._clear).pack(side="right")

        ctk.CTkLabel(
            self,
            text="自动监听本机剪贴板变化（最多保留 50 条）。双击可复制回剪贴板。",
            font=ctk.CTkFont(size=13),
            text_color="gray70",
            anchor="w",
        ).pack(fill="x", padx=8, pady=(0, 8))

        self._list = ctk.CTkTextbox(self, font=ctk.CTkFont(size=13))
        self._list.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._list.bind("<Double-Button-1>", self._copy_selected)

    def on_show(self):
        self._poll()

    def on_hide(self):
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None

    def _poll(self):
        try:
            text = self.clipboard_get()
        except Exception:
            text = None
        if text is not None and text != self._last:
            self._last = text
            if not self._history or self._history[0] != text:
                self._history.insert(0, text)
                self._history = self._history[:50]
                self._render()
                self.app.set_status("剪贴板已更新")
        self._poll_id = self.after(800, self._poll)

    def _render(self):
        lines = []
        for i, item in enumerate(self._history, 1):
            preview = item.replace("\r", "\\r").replace("\n", "\\n")
            if len(preview) > 200:
                preview = preview[:200] + "…"
            lines.append(f"[{i}] {preview}")
        self._list.delete("1.0", "end")
        self._list.insert("1.0", "\n\n".join(lines) if lines else "(暂无记录)")

    def _clear(self):
        self._history = []
        self._render()

    def _copy_selected(self, _event=None):
        try:
            index = self._list.index("insert linestart")
            line = self._list.get(index, f"{index} lineend").strip()
        except Exception:
            return
        if not line.startswith("["):
            return
        try:
            num = int(line.split("]", 1)[0].strip("["))
            text = self._history[num - 1]
        except Exception:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.set_status("已复制到剪贴板")
