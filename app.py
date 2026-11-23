"""Tris–mCP 흡광도에서 NaCl 농도를 추산하는 Tk 데스크톱 앱."""

import csv
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from estimate import (
    Point, baseline_correct, calibration_curve, estimate, load_reference, ratio_from_absorbances,
    read_absorbances, validate_reference,
)
from evaluation import (
    TARGET_ERROR, read_samples, reference_from_samples, assess_samples,
    assessment_summary, write_checks,
)



class EstimatorApp(ttk.Frame):
    """측정값 입력, 추산 결과, 기준 곡선과 검증 정보를 표시한다."""

    def __init__(self, master, reference=None):
        self.calibration_samples = load_reference() if reference is None else list(reference)
        self.baseline_active = reference is None
        self.reference = reference_from_samples(self.calibration_samples, self.baseline_active)
        self.reference_name = "3차 실험 · 2026-11-05"
        self.checks = []
        self.curve = calibration_curve(self.reference)
        self.validation = validate_reference(self.reference)
        super().__init__(master, padding=(20, 14), style="Page.TFrame")
        self._setup_styles()
        self.a434 = tk.StringVar(master=self)
        self.a578 = tk.StringVar(master=self)
        self.a730 = tk.StringVar(master=self)
        self.baseline_enabled = tk.BooleanVar(master=self, value=self.baseline_active)
        self.source_text = tk.StringVar(master=self, value="직접 입력")
        self.ratio_text = tk.StringVar(master=self, value="—")
        self.result_text = tk.StringVar(master=self, value="—")
        self.detail_text = tk.StringVar(master=self)
        self.reference_status = tk.StringVar(master=self)
        self.external_text = tk.StringVar(master=self, value=assessment_summary([]))
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
        self.a730.trace_add("write", self._on_edit)
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
        formula = ("R보정 = (A578.3 − A730.1) / (A434.2 − A730.1)"
                   if self.baseline_active else "R = A578.3 / A434.2")
        intro = ttk.Label(header, text=f"{self.reference_name} 기준 · {formula}",
                          style="Intro.TLabel", wraplength=850)
        intro.grid(sticky="ew", pady=(2, 0))
        intro.bind("<Configure>", self._wrap_label)
        toolbar = ttk.Frame(header, style="Page.TFrame")
        toolbar.grid(row=2, column=0, sticky="w", pady=(9, 0))
        for col, (label, command) in enumerate([
            ("검량자료 열기", self.choose_calibration),
            ("3차 기준으로 복원", self.restore_reference),
            ("CSV 양식 저장", self.save_template),
            ("참고 문헌", self.show_references),
        ]):
            ttk.Button(toolbar, text=label, command=command).grid(row=0, column=col, padx=(0, 5))
        ttk.Label(header, textvariable=self.reference_status, style="Intro.TLabel").grid(
            row=3, column=0, sticky="w", pady=(2, 0))
        ttk.Checkbutton(header, text="730.1 nm 바탕선 보정 적용", variable=self.baseline_enabled,
                        command=self.change_baseline_mode).grid(row=4, column=0, sticky="w", pady=(5, 0))

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
        ttk.Label(fields, text="730.1 nm 흡광도 · 바탕선", style="Text.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Entry(fields, textvariable=self.a730, style="Amount.TEntry",
                  state="normal" if self.baseline_active else "disabled").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        actions = ttk.Frame(inputs, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="w", pady=(12, 8))
        ttk.Button(actions, text="CSV 열기…", command=self.choose_csv).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(actions, text="기준점 예시", command=self.load_example).grid(row=0, column=1)
        source = ttk.Label(inputs, textvariable=self.source_text, style="Note.TLabel", wraplength=240)
        source.grid(row=3, column=0, sticky="ew")
        source.bind("<Configure>", self._wrap_label)
        ttk.Label(inputs, text="검량 곡선 · 빈 원은 추산값", style="Text.TLabel").grid(
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
        ttk.Label(line, text="보정 흡광도비 R" if self.baseline_active else "흡광도비 R",
                  style="Note.TLabel").pack(side="left", padx=(0, 6))
        ttk.Label(line, textvariable=self.ratio_text, style="Text.TLabel").pack(side="left")
        notes = [
            (self.detail_text, None),
            (None, f"기준 농도 {self.reference[0].concentration:.2f}–{self.reference[-1].concentration:.2f} M"
                   f" · R {self.reference[0].ratio:.5f}–{self.reference[-1].ratio:.5f}"),
            (None, "입력 시료는 검량자료와 같은 조제·측정 조건이어야 합니다."),
            (None, "730.1 nm 값이 일정한 바탕선 오프셋이라는 가정으로 보정합니다. "
                   "배경 용액(블랭크)·pH·온도 보정은 포함하지 않습니다."
                   if self.baseline_active else "바탕선 보정을 적용하지 않은 흡광도비입니다."),
            (None, f"목표 절대오차 ±{TARGET_ERROR:.2f} M"),
            (self.external_text, None),
            (None, "±0.30 M는 목표값입니다. 이 프로그램은 개별 추산값의 신뢰구간을 계산하지 않습니다."),
        ]
        for row, (variable, text) in enumerate(notes, 3):
            label = ttk.Label(result, text=text or "", textvariable=variable,
                              style="Note.TLabel", wraplength=420)
            label.grid(row=row, column=0, sticky="ew", pady=(3, 6))
            label.bind("<Configure>", self._wrap_label)

        checks = ttk.Frame(self, padding=(14, 10), style="Card.TFrame")
        checks.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        checks.columnconfigure(0, weight=1)
        ttk.Label(checks, text="현재 검량선의 내부 보간 검증", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        stats = self.validation
        metrics = ttk.Label(
            checks,
            text=f"평균절대오차(MAE) {stats.mae:.3f} M   ·   RMSE {stats.rmse:.3f} M"
                 f"   ·   최대절대오차 {stats.max_error:.3f} M"
                 f"   ·   목표 이내 {sum(abs(p.error) <= TARGET_ERROR + 1e-12 for p in stats.samples)}"
                 f"/{len(stats.samples)}개",
            style="Text.TLabel", wraplength=800,
        )
        metrics.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        metrics.bind("<Configure>", self._wrap_label)
        self.validation_table = ttk.Treeview(
            checks, columns=("actual", "predicted", "error"),
            show="headings", height=min(6, len(stats.samples)), style="Validation.Treeview",
            selectmode="none",
        )
        self.validation_table.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        validation_scroll = ttk.Scrollbar(checks, command=self.validation_table.yview)
        validation_scroll.grid(row=2, column=1, sticky="ns", pady=(0, 5))
        self.validation_table.configure(yscrollcommand=validation_scroll.set)
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
            f" 표의 오차는 위 {len(stats.samples)}개 검증 사례에 대한 값입니다.",
            "기본 3차 자료는 pH·온도를 측정하지 않았고 NaCl과 함께 Tris·mCP의 최종 농도도 변했습니다. "
            "미지 시료에 적용하려면 조제·측정 조건을 맞추고 별도로 검증해야 합니다.",
        ]
        for row, text in enumerate(explanations, 3):
            label = ttk.Label(checks, text=text, style="Note.TLabel", wraplength=800)
            label.grid(row=row, column=0, sticky="ew", pady=(2, 0))
            label.bind("<Configure>", self._wrap_label)

        external = ttk.Frame(self, padding=(14, 10), style="Card.TFrame")
        external.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        external.columnconfigure(0, weight=1)
        ttk.Label(external, text="별도 검증자료 · 목표 ±0.30 M", style="Section.TLabel").grid(
            row=0, column=0, sticky="w")
        buttons = ttk.Frame(external, style="Card.TFrame")
        buttons.grid(row=1, column=0, sticky="w", pady=6)
        ttk.Button(buttons, text="검증자료 열기", command=self.choose_validation).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="검증 결과 저장", command=self.save_validation).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="현재 추산값 저장", command=self.save_estimate).pack(side="left")
        self.external_table = ttk.Treeview(
            external, columns=("actual", "predicted", "error", "status"),
            show="headings", height=5, style="Validation.Treeview",
        )
        self.external_table.grid(row=2, column=0, sticky="ew")
        for key, title in (("actual", "조제 농도 (M)"), ("predicted", "추산 (M)"),
                           ("error", "오차 (M)"), ("status", "목표 판정")):
            self.external_table.heading(key, text=title)
            self.external_table.column(key, width=130, minwidth=80, anchor="center")
        self.external_table.column("status", width=230)
        scroll = ttk.Scrollbar(external, orient="vertical", command=self.external_table.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.external_table.configure(yscrollcommand=scroll.set)
        for check in self.checks:
            self.external_table.insert("", "end", values=(
                f"{check.actual:.3f}",
                "—" if check.predicted is None else f"{check.predicted:.3f}",
                "—" if check.error is None else f"{check.error:+.3f}",
                check.status,
            ))
        note = ttk.Label(
            external, text="각 행에 알려진 조제 농도와 측정 흡광도를 기록한 별도 시료 CSV를 사용하세요. "
                           "보정 모드에서는 A730_1 열도 필요합니다. "
                           "검량자료와 같은 조제·측정 조건인지 확인해야 합니다. "
                           "농도·흡광도비가 검량자료나 앞선 검증 행과 같으면 독립성 확인 대상으로 표시합니다.",
            style="Note.TLabel", wraplength=800,
        )
        note.grid(row=3, column=0, sticky="ew", pady=(5, 0))
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

    def _set_inputs(self, a434, a578, source, a730=""):
        self._updating_inputs = True
        try:
            self.a434.set(a434)
            self.a578.set(a578)
            self.a730.set(a730)
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
        elif self.baseline_active and not self.a730.get().strip():
            self.detail_text.set("바탕선 보정에 필요한 730.1 nm 흡광도를 입력하거나 CSV를 다시 여세요.")
        else:
            try:
                a434, a578 = float(self.a434.get()), float(self.a578.get())
                ratio_from_absorbances(a434, a578)
                if self.baseline_active:
                    ratio = baseline_correct(Point(0, a434, a578, float(self.a730.get()))).ratio
                else:
                    ratio = ratio_from_absorbances(a434, a578)
                concentration = estimate(ratio, self.reference)
            except ValueError as exc:
                self.detail_text.set(f"입력을 확인하세요. {exc}")
            else:
                self.ratio_text.set(f"{ratio:.3e}" if ratio >= 1_000 else f"{ratio:.5f}")
                self._ratio, self._concentration = ratio, concentration
                if concentration is None:
                    self.result_text.set("기준 범위 밖")
                    self.detail_text.set("입력한 비율이 검량자료의 측정 범위를 벗어나 농도를 추산할 수 없습니다.")
                else:
                    self.result_text.set(f"{concentration:.2f} M")
                    self.detail_text.set("현재 검량자료의 PCHIP 곡선에서 구한 참고 농도입니다.")
        self._draw_curve()

    def choose_csv(self):
        file = filedialog.askopenfilename(parent=self, title="Vernier 측정 CSV 선택",
                                          filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*")])
        if file:
            self.load_csv(file)

    def load_csv(self, path):
        """현재 모드에 필요한 파장의 흡광도를 읽고 실패 시 기존 결과를 비운다."""
        try:
            values = read_absorbances(path, include_baseline=self.baseline_active)
        except (ValueError, OSError) as exc:
            self._set_inputs("", "", f"CSV 오류 · {Path(path).name}")
            self.detail_text.set(str(exc))
            return
        self._set_inputs(str(values[0]), str(values[1]),
                         f"CSV · {Path(path).name}\n폴더 · {Path(path).parent}",
                         str(values[2]) if self.baseline_active else "")

    def load_example(self):
        concentration = self.reference[len(self.reference) // 2].concentration
        point = next(p for p in self.calibration_samples if p.concentration == concentration)
        self._set_inputs(str(point.a434), str(point.a578), f"검량 기준점 예시 · 농도 {point.concentration:.2f} M",
                         "" if point.a730 is None else str(point.a730))

    @property
    def correction_mode(self):
        return "constant_offset_A730_1" if self.baseline_active else "none"

    def change_baseline_mode(self):
        requested = self.baseline_enabled.get()
        try:
            reference = reference_from_samples(self.calibration_samples, requested)
            curve = calibration_curve(reference)
            validation = validate_reference(reference)
        except ValueError as exc:
            self.baseline_enabled.set(self.baseline_active)
            self.reference_status.set(f"보정 모드 변경 실패 · {exc}")
            return
        self.baseline_active = requested
        self.reference, self.curve, self.validation = reference, curve, validation
        self.checks = []
        self.external_text.set(assessment_summary([]))
        self.reference_status.set("바탕선 보정 설정을 변경했습니다. 별도 검증자료를 다시 불러오세요.")
        self._refresh()

    def _refresh(self):
        for widget in self.winfo_children():
            widget.destroy()
        self._build()
        self.update_result()

    def choose_calibration(self):
        path = filedialog.askopenfilename(parent=self, title="알려진 농도의 검량자료 CSV",
                                          filetypes=[("CSV 파일", "*.csv")])
        if path:
            self.load_calibration(path)

    def load_calibration(self, path):
        try:
            samples = read_samples(path)
            reference = reference_from_samples(samples, self.baseline_active)
            curve = calibration_curve(reference)
            validation = validate_reference(reference)
        except (ValueError, OSError) as exc:
            self.reference_status.set(f"검량자료 확인 필요 · {exc}")
            return False
        self.calibration_samples = samples
        self.reference, self.curve, self.validation = reference, curve, validation
        self.reference_name = str(Path(path).resolve())
        self.checks = []
        self.external_text.set(assessment_summary([]))
        self.reference_status.set(f"{len(reference)}개 농도 · {len(samples)}개 측정값 · 농도별 흡광도비 평균 사용")
        self._refresh()
        return True

    def restore_reference(self):
        try:
            samples = load_reference()
            reference = reference_from_samples(samples, self.baseline_active)
            curve = calibration_curve(reference)
            validation = validate_reference(reference)
        except (ValueError, OSError) as exc:
            self.reference_status.set(f"기준 파일 확인 필요 · {exc}")
            return
        self.reference, self.curve, self.validation = reference, curve, validation
        self.calibration_samples = samples
        self.reference_name = "3차 실험 · 2026-11-05"
        self.checks = []
        self.external_text.set(assessment_summary([]))
        self.reference_status.set("")
        self._refresh()

    def choose_validation(self):
        path = filedialog.askopenfilename(parent=self, title="별도로 제조한 검증 시료 CSV",
                                          filetypes=[("CSV 파일", "*.csv")])
        if path:
            self.load_validation(path)

    def load_validation(self, path):
        try:
            checks = assess_samples(read_samples(path), self.reference, self.calibration_samples,
                                    self.baseline_active)
        except (ValueError, OSError) as exc:
            self.external_text.set(f"검증자료 확인 필요 · {exc}")
            self.checks = []
            self._refresh()
            return False
        self.checks = checks
        self.external_text.set(f"검증자료 · {Path(path).name}\n{assessment_summary(checks)}")
        self._refresh()
        return True

    def save_template(self):
        path = filedialog.asksaveasfilename(
            parent=self, title="검량·검증 CSV 양식 저장",
            defaultextension=".csv", initialfile="measurement_template.csv",
            filetypes=[("CSV 파일", "*.csv")])
        if path:
            try:
                Path(path).write_text("concentration_M,A434_2,A578_3,A730_1\n", encoding="utf-8-sig")
            except OSError as exc:
                messagebox.showerror("저장 오류", str(exc), parent=self)

    def save_validation(self):
        if not self.checks:
            messagebox.showinfo("검증 결과", "먼저 별도 검증자료를 불러오세요.", parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv",
                                          initialfile="validation_results.csv")
        if path:
            try:
                write_checks(path, self.checks, self.reference_name, self.correction_mode)
            except OSError as exc:
                messagebox.showerror("저장 오류", str(exc), parent=self)

    def save_estimate(self):
        if self._ratio is None:
            messagebox.showinfo("추산 결과", "먼저 유효한 흡광도를 입력하세요.", parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv",
                                          initialfile="estimate.csv")
        if path:
            try:
                with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["calibration", "source", "A434_2", "A578_3", "A730_1",
                                     "correction_mode", "ratio",
                                     "predicted_M", "estimate_status", "target_M", "validation_status"])
                    writer.writerow([self.reference_name, self.source_text.get(),
                                     self.a434.get(), self.a578.get(), self.a730.get(),
                                     self.correction_mode, self._ratio,
                                     "" if self._concentration is None else self._concentration,
                                     "기준 범위 밖" if self._concentration is None else "검량선에 따른 참고값",
                                     TARGET_ERROR, self.external_text.get()])
            except OSError as exc:
                messagebox.showerror("저장 오류", str(exc), parent=self)

    def show_references(self):
        try:
            content = Path(__file__).with_name("REFERENCES.md").read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("참고 문헌", str(exc), parent=self)
            return
        window = tk.Toplevel(self)
        window.title("사용 문헌과 적용 범위")
        window.geometry("850x600")
        text = tk.Text(window, wrap="word", padx=15, pady=15)
        scroll = ttk.Scrollbar(window, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", content)
        text.configure(state="disabled")

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
        concentrations = [left + (right - left) * index / 200 for index in range(201)]
        coords = [project(c, float(self.curve(c))) for c in concentrations]
        canvas.create_line(*[coordinate for point in coords for coordinate in point],
                           fill="#0b7363", width=2, tags="reference")
        for point in self.reference:
            x, y = project(point.concentration, point.ratio)
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
