"""Tris–mCP 흡광도에서 NaCl 농도를 추산하는 Tk 데스크톱 앱."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from estimate import estimate, load_reference, ratio_from_absorbances, read_absorbances, validate_reference



class EstimatorApp(ttk.Frame):
    """측정값 입력, 추산 결과, 기준 곡선과 검증 정보를 표시한다."""

    def __init__(self, master, reference=None):
        self.reference = load_reference() if reference is None else reference
        self.validation = validate_reference(self.reference)
        super().__init__(master, padding=(20, 14), style="Page.TFrame")
        self._setup_styles()
        self.a434 = tk.StringVar(master=self)
        self.a578 = tk.StringVar(master=self)
        self.source_text = tk.StringVar(master=self, value="직접 입력")
        self.ratio_text = tk.StringVar(master=self, value="—")
        self.result_text = tk.StringVar(master=self, value="—")
        self.detail_text = tk.StringVar(master=self)
        self._updating_inputs = False
        self._ratio = None
        self._concentration = None
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
            ("Result.TLabel", 13, "#006452", "#ffffff", "bold"),
        ]:
            style.configure(name, background=bg, foreground=color, font=(family, size, weight))
        style.configure("Amount.TEntry", padding=(5, 4))
        style.configure("Validation.Treeview", rowheight=25)

    def _build(self):
        header = ttk.Frame(self, style="Page.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="NaCl 농도 추산기", style="Title.TLabel").grid(sticky="w")
        intro = ttk.Label(header, text="3차 실험 기준 · 흡광도비 R = A(578.3 nm) / A(434.2 nm)로 NaCl 농도를 추산합니다.",
                          style="Intro.TLabel", wraplength=850)
        intro.grid(sticky="ew", pady=(2, 0))
        intro.bind("<Configure>", self._wrap_label)

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
        ttk.Label(inputs, text="3차 기준 곡선 · 빈 원은 추산값", style="Text.TLabel").grid(
            row=4, column=0, sticky="w", pady=(10, 0))
        inputs.rowconfigure(5, weight=1)
        self.chart = tk.Canvas(inputs, background="#ffffff", highlightthickness=0, width=220, height=115)
        self.chart.grid(row=5, column=0, sticky="nsew")
        self.chart.bind("<Configure>", lambda _event: self._draw_curve())

        result = ttk.Frame(body, padding=14, style="Card.TFrame")
        result.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        result.columnconfigure(0, weight=1)
        ttk.Label(result, text="추산 결과", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(result, textvariable=self.result_text, style="Result.TLabel").grid(
            row=1, column=0, sticky="w", pady=(12, 8))
        line = ttk.Frame(result, style="Card.TFrame")
        line.grid(row=2, column=0, sticky="ew", pady=(3, 8))
        ttk.Label(line, text="흡광도비 R", style="Note.TLabel").pack(side="left", padx=(0, 6))
        ttk.Label(line, textvariable=self.ratio_text, style="Text.TLabel").pack(side="left")
        notes = [
            (self.detail_text, None),
            (None, f"기준 농도 {self.reference[0].concentration:.2f}–{self.reference[-1].concentration:.2f} M"
                   f" · R {self.reference[0].ratio:.5f}–{self.reference[-1].ratio:.5f}"),
            (None, "입력 시료는 3차와 같은 조제·측정 조건이어야 합니다."),
            (None, "농도별 반복측정이 없어 개별 추산값의 ±오차와 신뢰구간은 산출할 수 없습니다."),
        ]
        for row, (variable, text) in enumerate(notes, 3):
            label = ttk.Label(result, text=text or "", textvariable=variable,
                              style="Note.TLabel", wraplength=420)
            label.grid(row=row, column=0, sticky="ew", pady=(3, 6))
            label.bind("<Configure>", self._wrap_label)

        checks = ttk.Frame(self, padding=(14, 10), style="Card.TFrame")
        checks.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        checks.columnconfigure(0, weight=1)
        ttk.Label(checks, text="3차 내부 보간 검증", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        stats = self.validation
        metrics = ttk.Label(
            checks,
            text=f"평균절대오차(MAE) {stats.mae:.3f} M   ·   RMSE {stats.rmse:.3f} M"
                 f"   ·   최대절대오차 {stats.max_error:.3f} M",
            style="Text.TLabel", wraplength=800,
        )
        metrics.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        metrics.bind("<Configure>", self._wrap_label)
        self.validation_table = ttk.Treeview(
            checks, columns=("actual", "predicted", "error"),
            show="headings", height=len(stats.samples), style="Validation.Treeview",
            selectmode="none",
        )
        self.validation_table.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        for key, title in [("actual", "제외한 농도 (M)"), ("predicted", "나머지 점으로 추산 (M)"),
                           ("error", "추산값 − 조제값 (M)")]:
            self.validation_table.heading(key, text=title)
            self.validation_table.column(key, anchor="center", width=180, minwidth=100)
        for point in stats.samples:
            self.validation_table.insert("", "end", values=(
                f"{point.actual:.2f}", f"{point.predicted:.3f}", f"{point.error:+.3f}",
            ))
        explanations = [
            f"내부 농도 {len(stats.samples)}개를 하나씩 제외하고 남은 점으로 추산했습니다."
            f" 양 끝 {stats.excluded_endpoints}개는 외삽이 필요해 검증에서 제외했습니다.",
            "MAE는 절대오차의 평균, RMSE는 오차 제곱 평균의 제곱근입니다."
            " 표의 오차는 위 여섯 검증 사례에 대한 값입니다.",
            "미지 시료의 정확도는 별도 검증이 필요합니다. 시료의 pH는 측정하지 않았고,"
            " NaCl 농도와 함께 Tris·mCP의 최종 농도도 변했습니다.",
        ]
        for row, text in enumerate(explanations, 3):
            label = ttk.Label(checks, text=text, style="Note.TLabel", wraplength=800)
            label.grid(row=row, column=0, sticky="ew", pady=(2, 0))
            label.bind("<Configure>", self._wrap_label)

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
        """입력이 바뀌면 추산값과 그래프의 이전 표시를 함께 갱신한다."""
        self._ratio = None
        self._concentration = None
        self.ratio_text.set("—")
        self.result_text.set("—")
        if not self.a434.get().strip() or not self.a578.get().strip():
            self.detail_text.set("434.2 nm와 578.3 nm 흡광도를 모두 입력하세요.")
        else:
            try:
                a434, a578 = float(self.a434.get()), float(self.a578.get())
                ratio = ratio_from_absorbances(a434, a578)
                concentration = estimate(ratio, self.reference)
            except ValueError as exc:
                self.detail_text.set(f"입력을 확인하세요. {exc}")
            else:
                self.ratio_text.set(f"{ratio:.3e}" if ratio >= 1_000 else f"{ratio:.5f}")
                self._ratio, self._concentration = ratio, concentration
                if concentration is None:
                    self.result_text.set("기준 범위 밖")
                    self.detail_text.set("입력한 비율이 3차의 측정 범위를 벗어나 농도를 추산할 수 없습니다.")
                else:
                    self.result_text.set(f"{concentration:.2f} M")
                    self.detail_text.set("3차의 인접한 두 기준점 사이를 선형 보간한 농도입니다.")
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
        self._set_inputs(str(point.a434), str(point.a578), f"3차 기준점 예시 · 조제 농도 {point.concentration:.2f} M")

    def _draw_curve(self):
        canvas = self.chart
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 110 or h < 90:
            return
        x0, x1 = 44, w - 16
        y0, y1 = 15, h - 31
        left, right = self.reference[0].concentration, self.reference[-1].concentration
        lowest, highest = self.reference[0].ratio, self.reference[-1].ratio
        margin = 0.07 * (highest - lowest)
        low, high = lowest - margin, highest + margin

        def project(concentration, ratio):
            x = x0 + (concentration - left) / (right - left) * (x1 - x0)
            y = y1 - (ratio - low) / (high - low) * (y1 - y0)
            return x, y

        for value in (lowest, (lowest + highest) / 2, highest):
            _, y = project(left, value)
            canvas.create_line(x0, y, x1, y, fill="#dbe5df")
            canvas.create_text(x0 - 6, y, anchor="e", text=f"{value:.2f}", fill="#486155")
        canvas.create_line(x0, y0, x0, y1, x1, y1, fill="#71877a")
        for value in (left, (left + right) / 2, right):
            x, _ = project(value, low)
            canvas.create_text(x, y1 + 3, anchor="n", text=f"{value:.1f}", fill="#486155")
        canvas.create_text(x0 - 2, y0 - 1, anchor="se", text="R", fill="#486155")
        canvas.create_text((x0 + x1) / 2, h - 1, anchor="s", text="NaCl 농도 (M)", fill="#486155")
        coords = [project(p.concentration, p.ratio) for p in self.reference]
        canvas.create_line(*[coordinate for point in coords for coordinate in point],
                           fill="#0b7363", width=2, tags="reference")
        for x, y in coords:
            canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#0b7363", outline="")
        if self._concentration is not None:
            x, y = project(self._concentration, self._ratio)
            canvas.create_line(x, y, x, y1, fill="#a34d18", dash=(3, 3), tags="prediction")
            canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#ffffff",
                               outline="#a34d18", width=2, tags="prediction")


def main():
    root = tk.Tk()
    root.title("NaCl 농도 추산기")
    root.geometry(f"{min(1000, root.winfo_screenwidth()-55)}x{min(690, root.winfo_screenheight()-85)}")
    root.minsize(640, 505)
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)
    viewport = tk.Canvas(root, highlightthickness=0, background="#f2f5f3")
    viewport.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(root, orient="vertical", command=viewport.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    viewport.configure(yscrollcommand=scrollbar.set, yscrollincrement=15)
    page = ttk.Frame(viewport)
    window = viewport.create_window(0, 0, anchor="nw", window=page)

    viewport.bind("<Configure>", lambda event: viewport.itemconfigure(window, width=event.width))
    page.bind("<Configure>", lambda _event: viewport.configure(scrollregion=viewport.bbox(window)))
    root.bind("<MouseWheel>", lambda event: viewport.yview_scroll(-int(event.delta / 120), "units"))
    try:
        app = EstimatorApp(page)
    except (ValueError, OSError) as exc:
        messagebox.showerror("기준 자료를 읽을 수 없습니다", str(exc), parent=root)
        root.destroy()
        return
    app.first_entry.focus_set()
    root.mainloop()


if __name__ == "__main__":
    main()
