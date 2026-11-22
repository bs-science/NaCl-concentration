"""Tris–mCP 흡광도에서 NaCl 농도를 추산하는 Tk 데스크톱 앱."""

import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from estimate import estimate, load_runs, ratio_from_absorbances, read_absorbances, validate_runs


class EstimatorApp(ttk.Frame):
    """측정값 입력, 추산 결과, 기준 곡선과 검증 정보를 표시한다."""

    def __init__(self, master, runs=None):
        self.runs = load_runs() if runs is None else runs
        self.reference = self.runs[2]
        self.validation = validate_runs(self.runs)
        super().__init__(master, padding=(20, 14), style="Page.TFrame")
        self._setup_styles()
        self.a434 = tk.StringVar(master=self)
        self.a578 = tk.StringVar(master=self)
        self.source_text = tk.StringVar(master=self, value="직접 입력")
        self.ratio_text = tk.StringVar(master=self, value="—")
        self.result_text = tk.StringVar(master=self, value="—")
        self.detail_text = tk.StringVar(master=self)
        self._updating_inputs = False
        self._marker = None
        self.grid(sticky="nsew")
        master.rowconfigure(0, weight=1)
        master.columnconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build()
        self.a434.trace_add("write", self._on_edit)
        self.a578.trace_add("write", self._on_edit)
        self.update_result()

    def _setup_styles(self):
        style = ttk.Style(self)
        family = tkfont.nametofont("TkDefaultFont").actual("family")
        if "맑은 고딕" in tkfont.families(self):
            family = "맑은 고딕"
        for name, background in [("Page.TFrame", "#f2f5f3"), ("Card.TFrame", "#ffffff")]:
            style.configure(name, background=background)
        for name, size, color, bg, weight in [
            ("Title.TLabel", 23, "#193a33", "#f2f5f3", "bold"),
            ("Intro.TLabel", 10, "#465e54", "#f2f5f3", "normal"),
            ("Section.TLabel", 13, "#203d32", "#ffffff", "bold"),
            ("Text.TLabel", 10, "#273e35", "#ffffff", "normal"),
            ("Note.TLabel", 10, "#4a6056", "#ffffff", "normal"),
            ("Result.TLabel", 21, "#006452", "#ffffff", "bold"),
        ]:
            style.configure(name, background=bg, foreground=color, font=(family, size, weight))
        style.configure("Amount.TEntry", padding=(5, 4))
        style.configure("Validation.Treeview", rowheight=25)

    def _build(self):
        header = ttk.Frame(self, style="Page.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(header, text="NaCl 농도 추산기", style="Title.TLabel").grid(sticky="w")
        ttk.Label(header, text="3차 Tris–mCP 실험의 여덟 농도를 기준으로 흡광도비에 대응하는 농도를 추산합니다.",
                  style="Intro.TLabel").grid(sticky="w", pady=(2, 0))

        body = ttk.Frame(self, style="Page.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=2, uniform="main")
        body.columnconfigure(1, weight=3, uniform="main")
        inputs = ttk.Frame(body, padding=14, style="Card.TFrame")
        inputs.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        inputs.columnconfigure(0, weight=1)
        ttk.Label(inputs, text="측정값 입력", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        fields = ttk.Frame(inputs, style="Card.TFrame")
        fields.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        for i, (label, var) in enumerate([("434.2 nm 흡광도", self.a434), ("578.3 nm 흡광도", self.a578)]):
            fields.columnconfigure(i, weight=1, uniform="values")
            padding = (0, 4) if i == 0 else (4, 0)
            ttk.Label(fields, text=label, style="Text.TLabel").grid(row=0, column=i, padx=padding, sticky="w")
            entry = ttk.Entry(fields, width=9, textvariable=var, style="Amount.TEntry")
            entry.grid(row=1, column=i, sticky="ew", padx=padding, pady=(2, 0))
            if i == 0:
                self.first_entry = entry
        actions = ttk.Frame(inputs, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="w", pady=(12, 8))
        ttk.Button(actions, text="CSV 열기…", command=self.choose_csv).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(actions, text="3차 예시", command=self.load_example).grid(row=0, column=1)
        source = ttk.Label(inputs, textvariable=self.source_text, style="Note.TLabel", wraplength=240)
        source.grid(row=3, column=0, sticky="ew")
        source.bind("<Configure>", self._wrap_label)

        result = ttk.Frame(body, padding=14, style="Card.TFrame")
        result.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        result.columnconfigure(0, weight=1)
        result.rowconfigure(4, weight=1)
        ttk.Label(result, text="추산 결과", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        line = ttk.Frame(result, style="Card.TFrame")
        line.grid(row=1, column=0, sticky="ew", pady=(3, 1))
        ttk.Label(line, textvariable=self.result_text, style="Result.TLabel").pack(side="left")
        ttk.Label(line, text="흡광도비 R", style="Note.TLabel").pack(side="left", padx=(12, 3))
        ttk.Label(line, textvariable=self.ratio_text, style="Text.TLabel").pack(side="left")
        details = ttk.Label(result, textvariable=self.detail_text, style="Note.TLabel", wraplength=420)
        details.grid(row=2, column=0, sticky="ew")
        details.bind("<Configure>", self._wrap_label)
        ttk.Label(result, text="3차 기준 곡선", style="Text.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.chart = tk.Canvas(result, background="#ffffff", highlightthickness=0, width=250, height=145)
        self.chart.grid(row=4, column=0, sticky="nsew")
        self.chart.bind("<Configure>", lambda _event: self._draw_curve())

        checks = ttk.Frame(self, padding=(14, 10), style="Card.TFrame")
        checks.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        checks.columnconfigure(0, weight=1)
        ttk.Label(checks, text="농도를 알고 있는 시료로 검증한 결과", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        table = ttk.Treeview(checks, columns=("set", "covered", "mae"), show="headings",
                             height=len(self.validation), style="Validation.Treeview", selectmode="none")
        table.grid(row=1, column=0, sticky="ew", pady=(6, 5))
        for key, title, alignment, width in [("set", "검증 자료", "w", 260), ("covered", "범위 안 / 전체 시료", "center", 110),
                                               ("mae", "평균절대오차 (M)", "e", 112)]:
            table.heading(key, text=title, anchor=alignment)
            table.column(key, anchor=alignment, width=width, minwidth=65)
        for label, nvalid, total, mae in self.validation:
            displayed = f"{mae:.3f}" if nvalid and math.isfinite(mae) else "—"
            table.insert("", "end", values=(label, f"{nvalid} / {total}", displayed))
        for row, text in enumerate([
            "3차 내부 검증은 양 끝 농도를 제외하고 한 점씩 빼서 추산했습니다. 다른 회차는 기준 범위 안의 시료만 오차 계산에 사용했습니다.",
            "pH를 측정하지 않았고 NaCl과 함께 Tris·mCP 농도도 변했습니다. 실제 미지 시료에 대한 정확도는 확인되지 않았습니다.",
        ], start=2):
            note = ttk.Label(checks, text=text, style="Note.TLabel", wraplength=800)
            note.grid(row=row, column=0, sticky="ew", pady=(1, 0))
            note.bind("<Configure>", self._wrap_label)

    @staticmethod
    def _wrap_label(event):
        width = max(100, event.width - 2)
        if int(float(event.widget.cget("wraplength"))) != width:
            event.widget.configure(wraplength=width)

    def _on_edit(self, *_args):
        if not self._updating_inputs:
            self.source_text.set("직접 입력")
            self.update_result()

    def _set_inputs(self, a434, a578, source):
        self._updating_inputs = True
        try:
            self.a434.set(a434)
            self.a578.set(a578)
        finally:
            self._updating_inputs = False
        self.source_text.set(source)
        self.update_result()

    def update_result(self):
        """입력 하나라도 지워지거나 유효하지 않으면 이전 추산과 그래프 표시를 지운다."""
        self._marker = None
        self.ratio_text.set("—")
        self.result_text.set("—")
        if not self.a434.get().strip() or not self.a578.get().strip():
            self.detail_text.set("434.2 nm와 578.3 nm 흡광도를 모두 입력하세요.")
        else:
            try:
                a434, a578 = float(self.a434.get()), float(self.a578.get())
            except ValueError:
                self.detail_text.set("두 흡광도에 숫자를 입력하세요.")
            else:
                try:
                    ratio = ratio_from_absorbances(a434, a578)
                    concentration = estimate(ratio, self.reference)
                except ValueError as exc:
                    self.detail_text.set(str(exc))
                else:
                    self.ratio_text.set(f"{ratio:.3e}" if abs(ratio) >= 1_000 else f"{ratio:.5f}")
                    if concentration is None:
                        self.result_text.set("범위 밖")
                        self.detail_text.set(f"3차 기준 흡광도비 {self.reference[0].ratio:.5f}–{self.reference[-1].ratio:.5f} 안에서만 추산합니다.")
                    else:
                        self.result_text.set(f"{concentration:.2f} M")
                        self.detail_text.set("3차 기준점 사이의 선형 보간값입니다.")
                        self._marker = (concentration, ratio)
        self._draw_curve()

    def choose_csv(self):
        file = filedialog.askopenfilename(parent=self, title="Vernier 측정 CSV 선택",
                                          filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*")])
        if file:
            self.load_csv(file)

    def load_csv(self, path):
        """CSV 경로에서 두 파장의 흡광도를 읽고 실패 시 기존 결과를 비운다."""
        try:
            a434, a578 = read_absorbances(path)
        except (ValueError, OSError) as exc:
            self._set_inputs("", "", f"CSV 오류 · {Path(path).name}")
            self.detail_text.set(str(exc))
            return
        self._set_inputs(str(a434), str(a578), f"CSV · {Path(path).name}")

    def load_example(self):
        point = self.reference[len(self.reference) // 2]
        self._set_inputs(str(point.a434), str(point.a578), f"3차 기준 시료 예시 · 조제 농도 {point.concentration:.2f} M")

    def _draw_curve(self):
        canvas = self.chart
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 110 or h < 90:
            return
        x0, x1 = 44, w - 16
        y0, y1 = 15, h - 31
        left, right = self.reference[0].concentration, self.reference[-1].concentration
        low, high = self.reference[0].ratio, self.reference[-1].ratio
        yrange = high - low
        low -= 0.07 * yrange
        high += 0.07 * yrange

        def project(concentration, ratio):
            return (x0 + (concentration-left)/(right-left)*(x1-x0), y1 - (ratio-low)/(high-low)*(y1-y0))

        for i in range(3):
            value = self.reference[0].ratio + yrange*i/2
            _, y = project(left, value)
            canvas.create_line(x0, y, x1, y, fill="#dbe5df")
            canvas.create_text(x0-6, y, anchor="e", text=f"{value:.2f}", fill="#486155")
        canvas.create_line(x0, y0, x0, y1, x1, y1, fill="#71877a")
        for value in (left, (left+right)/2, right):
            x, _ = project(value, low)
            canvas.create_text(x, y1+3, anchor="n", text=f"{value:.1f}", fill="#486155")
        canvas.create_text(x0-2, y0-1, anchor="se", text="R", fill="#486155")
        canvas.create_text((x0+x1)/2, h-1, anchor="s", text="NaCl 농도 (M)", fill="#486155")
        coords = [project(p.concentration,p.ratio) for p in self.reference]
        canvas.create_line(*[xy for point in coords for xy in point], fill="#14745f", width=2)
        for x,y in coords:
            canvas.create_oval(x-2.5, y-2.5, x+2.5, y+2.5, fill="#14745f", outline="")
        if self._marker is not None:
            x, y = project(*self._marker)
            canvas.create_line(x, y, x, y1, fill="#b2621e", dash=(3, 3))
            canvas.create_oval(x-5, y-5, x+5, y+5, fill="#ffffff", outline="#ae5113", width=2)


def main():
    root = tk.Tk()
    root.title("NaCl 농도 추산기")
    root.geometry(f"{min(1000, root.winfo_screenwidth()-55)}x{min(690, root.winfo_screenheight()-85)}")
    root.minsize(640, 505)
    try:
        app = EstimatorApp(root)
    except (ValueError, OSError) as exc:
        messagebox.showerror("기준 자료를 읽을 수 없습니다", str(exc), parent=root)
        root.destroy()
        return
    app.first_entry.focus_set()
    root.mainloop()


if __name__ == "__main__":
    main()
