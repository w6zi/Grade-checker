import customtkinter as ctk
import json
import os
from datetime import date, datetime

# simple in-memory storage (backed by disk)
assignments = []
total_points = 0
next_id = 1
classes = []      # List of {'name': str, 'grade_percent': float or None}
study_log = []    # List of "YYYY-MM-DD" strings

DATA_FILE = "grade_data.json"


def load_data():
    """Load assignments, classes, points, etc. from disk if file exists."""
    global assignments, total_points, next_id, classes, study_log

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            assignments = data.get("assignments", [])
            total_points = data.get("total_points", 0)
            next_id = data.get("next_id", 1)
            classes = data.get("classes", [])
            study_log = data.get("study_log", [])
        except Exception:
            # If file is corrupted or unreadable, just start clean
            assignments = []
            total_points = 0
            next_id = 1
            classes = []
            study_log = []
    else:
        assignments = []
        total_points = 0
        next_id = 1
        classes = []
        study_log = []


def save_data():
    """Save all current data to disk."""
    data = {
        "assignments": assignments,
        "total_points": total_points,
        "next_id": next_id,
        "classes": classes,
        "study_log": study_log,
    }
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        # Ignore write errors for now; you could add an error popup later
        pass


def percent_to_letter_gpa(percent: float):
    if percent >= 97:
        return "A+", 4.0
    elif percent >= 93:
        return "A", 4.0
    elif percent >= 90:
        return "A-", 3.7
    elif percent >= 87:
        return "B+", 3.3
    elif percent >= 83:
        return "B", 3.0
    elif percent >= 80:
        return "B-", 2.7
    elif percent >= 77:
        return "C+", 2.3
    elif percent >= 73:
        return "C", 2.0
    elif percent >= 70:
        return "C-", 1.7
    elif percent >= 67:
        return "D+", 1.3
    elif percent >= 63:
        return "D", 1.0
    elif percent >= 60:
        return "D-", 0.7
    else:
        return "F", 0.0


def parse_due_date(due_str: str):
    """Parse YYYY-MM-DD into a date object. Return None if invalid/empty."""
    if not due_str:
        return None
    try:
        return datetime.strptime(due_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_subject_averages():
    """Return dict: subject -> average grade for that subject."""
    subject_grades = {}
    for a in assignments:
        subj = a.get("subject") or "No Subject"
        g = a.get("grade_percent")
        if g is not None:
            subject_grades.setdefault(subj, []).append(g)
    return {subj: sum(vals) / len(vals) for subj, vals in subject_grades.items()}


def compute_priority(assignment, today, subject_avgs):
    """
    Compute a priority score and factors for an assignment.

    Factors:
    - weight_factor: based on points (5-100, higher = more important)
    - urgency_factor: based on days until due / overdue
    - risk_factor: based on current/subject grade (lower grade = higher risk)
    """
    # ----- weight factor -----
    points = assignment.get("points", 250)
    points = max(5, min(100, points))
    # map 5–100 -> 0.5–1.0
    weight_factor = 0.5 + 0.5 * (points - 5) / (100 - 5)

    # ----- urgency factor -----
    due = parse_due_date(assignment.get("due", ""))
    if due is None:
        urgency_factor = 0.7
        days_until = None
    else:
        days_until = (due - today).days
        if days_until <= 0:
            urgency_factor = 2.0   # overdue / due today
        elif days_until <= 1:
            urgency_factor = 1.8
        elif days_until <= 3:
            urgency_factor = 1.6
        elif days_until <= 7:
            urgency_factor = 1.3
        elif days_until <= 14:
            urgency_factor = 1.1
        else:
            urgency_factor = 0.8   # far away

    # ----- risk factor -----
    subj = assignment.get("subject") or "No Subject"
    own_grade = assignment.get("grade_percent")
    if own_grade is not None:
        base_grade = own_grade
    elif subj in subject_avgs:
        base_grade = subject_avgs[subj]
    else:
        base_grade = 100.0

    # lower grade -> higher risk_factor
    # 100% → ~0.6   95% → ~1.0   80% → ~1.6 (clamped)
    raw_risk = (95.0 - base_grade) / 20.0 + 1.0
    risk_factor = max(0.6, min(1.6, raw_risk))

    priority = weight_factor * urgency_factor * risk_factor
    return priority, {
        "weight_factor": weight_factor,
        "urgency_factor": urgency_factor,
        "risk_factor": risk_factor,
        "days_until": days_until,
        "base_grade": base_grade,
    }


def compute_streaks():
    """
    Return (current_streak, longest_streak) based on study_log.
    Streaks are in days of consecutive study entries.
    """
    if not study_log:
        return 0, 0

    try:
        dates = sorted(
            {datetime.strptime(d, "%Y-%m-%d").date() for d in study_log}
        )
    except Exception:
        return 0, 0

    if not dates:
        return 0, 0

    # Longest streak
    longest = 1
    current = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            current += 1
        else:
            longest = max(longest, current)
            current = 1
    longest = max(longest, current)

    # Current streak (ending at last study date)
    current_streak = 1
    for i in range(len(dates) - 1, 0, -1):
        if (dates[i] - dates[i - 1]).days == 1:
            current_streak += 1
        else:
            break

    return current_streak, longest


class StudyApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Grade Tracker")
        self.geometry("1000x850")
        ctk.set_appearance_mode("light")

        self.main_purple = "#5a189a"
        self.light_purple = "#7b2cbf"
        self.accent_purple = "#9d4edd"
        self.text_baby_blue = "#9ef0ff"
        self.white = "#ffffff"

        self.configure(fg_color=self.main_purple)

        self.tabview = ctk.CTkTabview(
            self,
            fg_color=self.light_purple,
            corner_radius=20,
            segmented_button_fg_color=self.light_purple,
            segmented_button_selected_color=self.accent_purple,
            segmented_button_unselected_color=self.light_purple,
            segmented_button_selected_hover_color=self.accent_purple,
            segmented_button_unselected_hover_color="#8c42d9",
            text_color=self.text_baby_blue,
        )
        self.tabview.pack(fill="both", expand=True, padx=20, pady=20)

        self.tab_assign = self.tabview.add("Add Assignment")
        self.tab_upcoming = self.tabview.add("Upcoming")
        self.tab_study = self.tabview.add("What to Study")
        self.tab_points = self.tabview.add("Points / Grades")
        self.tab_grades = self.tabview.add("Grades")
        self.tab_classes = self.tabview.add("Classes")
        self.tab_fun = self.tabview.add("FUN")

        self.build_add_tab()
        self.build_upcoming_tab()
        self.build_study_tab()
        self.build_points_tab()
        self.build_grades_tab()
        self.build_classes_tab()
        self.build_fun_tab()

        # Make sure UI reflects loaded data
        self.refresh_upcoming_list()
        self.refresh_assignment_dropdown()
        self.refresh_grades_overview()
        self.refresh_classes_overview()
        self.refresh_fun_ui()

    # ---------- TAB 1: ADD ASSIGNMENT ----------

    def build_add_tab(self):
        frame = self.tab_assign

        title = ctk.CTkLabel(
            frame,
            text="Add Assignment",
            font=("Segoe UI", 24, "bold"),
            text_color=self.text_baby_blue,
        )
        title.pack(pady=10)

        self.entry_title = ctk.CTkEntry(
            frame,
            placeholder_text="Assignment title",
            width=400,
            height=40,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            border_width=2,
            text_color="black",
        )
        self.entry_title.pack(pady=8)

        self.entry_subject = ctk.CTkEntry(
            frame,
            placeholder_text="Class / Subject (optional)",
            width=400,
            height=40,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            border_width=2,
            text_color="black",
        )
        self.entry_subject.pack(pady=8)

        self.entry_due = ctk.CTkEntry(
            frame,
            placeholder_text="Due date (e.g. 2025-12-01)",
            width=400,
            height=40,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            border_width=2,
            text_color="black",
        )
        self.entry_due.pack(pady=8)

        points_label = ctk.CTkLabel(
            frame,
            text="Points (5 = least important, 100 = most important):",
            text_color=self.text_baby_blue,
        )
        points_label.pack(pady=(10, 0))

        self.points_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Enter points (5-100)",
            width=400,
            height=40,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            border_width=2,
            text_color="black",
        )
        self.points_entry.pack(pady=8)

        add_button = ctk.CTkButton(
            frame,
            text="Add Assignment",
            command=self.add_assignment,
            fg_color=self.accent_purple,
            hover_color="#c77dff",
            corner_radius=20,
            width=200,
            height=40,
        )
        add_button.pack(pady=10)

        self.add_status_label = ctk.CTkLabel(
            frame,
            text="",
            text_color=self.text_baby_blue,
        )
        self.add_status_label.pack(pady=5)

    def update_weight_label(self, value):
        self.weight_value_label.configure(text=str(int(float(value))))

    def add_assignment(self):
        global next_id, assignments

        title = self.entry_title.get().strip()
        subject = self.entry_subject.get().strip()
        due = self.entry_due.get().strip()
        points_str = self.points_entry.get().strip()

        if not title:
            self.add_status_label.configure(text="Title is required.")
            return

        try:
            points = int(points_str)
            if points < 5 or points > 100:
                self.add_status_label.configure(text="Points must be between 5 and 100.")
                return
        except ValueError:
            self.add_status_label.configure(text="Points must be a valid number.")
            return

        assignment = {
            "id": next_id,
            "title": title,
            "subject": subject,
            "due": due,
            "points": points,
            "grade_percent": None,
            "points_awarded": 0,
        }
        assignments.append(assignment)
        next_id += 1

        save_data()

        self.add_status_label.configure(text=f"Added: {title}")
        self.entry_title.delete(0, "end")
        self.entry_subject.delete(0, "end")
        self.entry_due.delete(0, "end")
        self.points_entry.delete(0, "end")

        self.refresh_upcoming_list()
        self.refresh_assignment_dropdown()
        self.refresh_grades_overview()
        self.refresh_fun_ui()

    # ---------- TAB 2: UPCOMING ----------

    def build_upcoming_tab(self):
        frame = self.tab_upcoming

        title = ctk.CTkLabel(
            frame,
            text="Upcoming Assignments",
            font=("Segoe UI", 24, "bold"),
            text_color=self.text_baby_blue,
        )
        title.pack(pady=10)

        self.upcoming_list = ctk.CTkTextbox(
            frame,
            width=800,
            height=350,
            corner_radius=15,
            fg_color=self.white,
            text_color="black",
            border_color=self.accent_purple,
            border_width=2,
        )
        self.upcoming_list.pack(pady=10)

    def refresh_upcoming_list(self):
        self.upcoming_list.configure(state="normal")
        self.upcoming_list.delete("1.0", "end")

        if not assignments:
            self.upcoming_list.insert("end", "No assignments yet.\n")
        else:
            for a in assignments:
                line = (
                    f"[ID {a['id']}] {a['title']} | "
                    f"{a['subject'] or 'No subject'} | "
                    f"Due: {a['due'] or 'N/A'} | "
                    f"Points: {a['points']}\n"
                )
                self.upcoming_list.insert("end", line)

        self.upcoming_list.configure(state="disabled")

    # ---------- TAB 3: WHAT TO STUDY ----------

    def build_study_tab(self):
        frame = self.tab_study

        title = ctk.CTkLabel(
            frame,
            text="What Should I Study?",
            font=("Segoe UI", 24, "bold"),
            text_color=self.text_baby_blue,
        )
        title.pack(pady=10)

        desc = ctk.CTkLabel(
            frame,
            text="Uses importance, due date, and grade risk to pick what matters most.",
            text_color=self.text_baby_blue,
        )
        desc.pack(pady=10)

        suggest_button = ctk.CTkButton(
            frame,
            text="Suggest",
            command=self.suggest_assignment,
            fg_color=self.accent_purple,
            hover_color="#c77dff",
            corner_radius=20,
            width=200,
            height=40,
        )
        suggest_button.pack(pady=10)

        self.suggest_label = ctk.CTkLabel(
            frame,
            text="",
            font=("Segoe UI", 16),
            text_color=self.text_baby_blue,
            justify="left",
        )
        self.suggest_label.pack(pady=10)

    def suggest_assignment(self):
        if not assignments:
            self.suggest_label.configure(text="No assignments to suggest.")
            return

        today = date.today()
        subject_avgs = compute_subject_averages()

        best_assignment = None
        best_priority = -1.0
        best_factors = None

        for a in assignments:
            priority, factors = compute_priority(a, today, subject_avgs)
            if priority > best_priority:
                best_priority = priority
                best_assignment = a
                best_factors = factors

        if not best_assignment:
            self.suggest_label.configure(text="No assignments to suggest.")
            return

        # Recommended study minutes based on priority (base 25 min)
        recommended_minutes = max(15, int(round(25 * best_priority)))

        title = best_assignment["title"]
        subject = best_assignment.get("subject") or "No subject"
        due_str = best_assignment.get("due") or "N/A"
        points = best_assignment.get("points", 250)

        days_until = best_factors["days_until"]
        base_grade = best_factors["base_grade"]
        weight_factor = best_factors["weight_factor"]
        urgency_factor = best_factors["urgency_factor"]
        risk_factor = best_factors["risk_factor"]

        if days_until is None:
            due_info = f"Due: {due_str} (no valid date)"
        else:
            if days_until < 0:
                due_info = f"Due: {due_str} (OVERDUE by {-days_until} days)"
            elif days_until == 0:
                due_info = f"Due: {due_str} (TODAY)"
            else:
                due_info = f"Due: {due_str} (in {days_until} days)"

        msg = (
            f"📚 Recommended: {title} ({subject})\n"
            f"{due_info}\n"
            f"Points: {points}\n"
            f"Estimated class grade: {base_grade:.1f}%\n\n"
            f"Priority score: {best_priority:.2f}\n"
            f"  • Weight factor:  {weight_factor:.2f}\n"
            f"  • Urgency factor: {urgency_factor:.2f}\n"
            f"  • Risk factor:    {risk_factor:.2f}\n\n"
            f"⏱ Suggested study time: {recommended_minutes} minutes"
        )

        self.suggest_label.configure(text=msg)

    # ---------- TAB 4: POINTS / GRADES ----------

    def build_points_tab(self):
        frame = self.tab_points

        title = ctk.CTkLabel(
            frame,
            text="Points & Grades",
            font=("Segoe UI", 24, "bold"),
            text_color=self.text_baby_blue,
        )
        title.pack(pady=10)

        self.assignment_dropdown = ctk.CTkComboBox(
            frame,
            values=[],
            width=400,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            text_color="black",
        )
        self.assignment_dropdown.pack(pady=10)

        self.grade_mode = ctk.StringVar(value="percent")

        mode_switch = ctk.CTkSegmentedButton(
            frame,
            values=["percent", "fraction"],
            variable=self.grade_mode,
            selected_color=self.accent_purple,
            selected_hover_color="#c77dff",
            unselected_color=self.light_purple,
            unselected_hover_color="#8c42d9",
            text_color=self.white,
            corner_radius=15,
        )
        mode_switch.pack(pady=10)

        self.grade_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Enter grade (e.g. 95 or 18/20)",
            width=300,
            height=40,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            border_width=2,
            text_color="black",
        )
        self.grade_entry.pack(pady=8)

        submit_button = ctk.CTkButton(
            frame,
            text="Add Points",
            command=self.add_points_for_grade,
            fg_color=self.accent_purple,
            hover_color="#c77dff",
            corner_radius=20,
            width=200,
            height=40,
        )
        submit_button.pack(pady=10)

        # Use loaded total_points here
        self.points_label = ctk.CTkLabel(
            frame,
            text=f"Total Points: {total_points}",
            font=("Segoe UI", 16, "bold"),
            text_color=self.text_baby_blue,
        )
        self.points_label.pack(pady=10)

        self.points_status_label = ctk.CTkLabel(
            frame,
            text="",
            text_color=self.text_baby_blue,
        )
        self.points_status_label.pack(pady=5)

    def refresh_assignment_dropdown(self):
        if not assignments:
            self.assignment_dropdown.configure(values=[], state="disabled")
        else:
            values = [f"{a['id']}: {a['title']}" for a in assignments]
            self.assignment_dropdown.configure(values=values, state="normal")
            self.assignment_dropdown.set(values[0])

    def add_points_for_grade(self):
        global total_points

        if not assignments:
            self.points_status_label.configure(text="No assignments available.")
            return

        selected = self.assignment_dropdown.get()
        if not selected:
            self.points_status_label.configure(text="Select an assignment.")
            return

        try:
            assignment_id = int(selected.split(":")[0])
        except ValueError:
            self.points_status_label.configure(text="Invalid assignment selection.")
            return

        grade_text = self.grade_entry.get().strip()
        if not grade_text:
            self.points_status_label.configure(text="Enter a grade.")
            return

        mode = self.grade_mode.get()
        try:
            if mode == "percent":
                percent = float(grade_text)
            else:
                num, den = grade_text.split("/")
                percent = (float(num) / float(den)) * 100.0
        except Exception:
            self.points_status_label.configure(text="Invalid grade format.")
            return

        if percent < 0 or percent > 120:
            self.points_status_label.configure(text="Percent out of range.")
            return

        # simple points formula
        points = round((percent / 100.0) * 20)

        total_points += points
        # Update the assignment's grade_percent
        for a in assignments:
            if a["id"] == assignment_id:
                a["grade_percent"] = round(percent, 2)
                break

        save_data()

        self.points_label.configure(text=f"Total Points: {total_points}")
        self.points_status_label.configure(text=f"+{points} points for {percent:.1f}%")
        self.grade_entry.delete(0, "end")
        self.refresh_grades_overview()
        self.refresh_fun_ui()

    # ---------- TAB 5: GRADES ----------

    def build_grades_tab(self):
        frame = self.tab_grades

        title = ctk.CTkLabel(
            frame,
            text="Grades Overview",
            font=("Segoe UI", 24, "bold"),
            text_color=self.text_baby_blue,
        )
        title.pack(pady=10)

        # Scrollable frame for subjects
        self.grades_scrollable = ctk.CTkScrollableFrame(
            frame,
            width=800,
            height=300,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            border_width=2,
        )
        self.grades_scrollable.pack(pady=10)

        # GPA labels at the bottom
        self.gpa_frame = ctk.CTkFrame(
            frame, fg_color=self.light_purple, corner_radius=15
        )
        self.gpa_frame.pack(pady=10, fill="x")

        self.unweighted_gpa_label = ctk.CTkLabel(
            self.gpa_frame,
            text="Unweighted GPA: N/A",
            font=("Segoe UI", 16, "bold"),
            text_color=self.text_baby_blue,
        )
        self.unweighted_gpa_label.pack(pady=5)

        self.weighted_gpa_label = ctk.CTkLabel(
            self.gpa_frame,
            text="Weighted GPA: N/A",
            font=("Segoe UI", 16, "bold"),
            text_color=self.text_baby_blue,
        )
        self.weighted_gpa_label.pack(pady=5)

    def refresh_grades_overview(self):
        # Clear existing widgets
        for widget in self.grades_scrollable.winfo_children():
            widget.destroy()

        # Group assignments by subject
        subjects = {}
        for a in assignments:
            subj = a["subject"] or "No Subject"
            subjects.setdefault(subj, []).append(a)

        # For each subject, calculate average grade and display
        for subj, assigns in subjects.items():
            graded = [a for a in assigns if a["grade_percent"] is not None]
            if graded:
                avg_percent = sum(a["grade_percent"] for a in graded) / len(graded)
                letter, gpa = percent_to_letter_gpa(avg_percent)
                text = f"{subj} - {letter} {avg_percent:.2f}%"
            else:
                text = f"{subj} - No grades yet"

            btn = ctk.CTkButton(
                self.grades_scrollable,
                text=text,
                command=lambda s=subj, a=assigns: self.show_subject_details(s, a),
                fg_color=self.accent_purple,
                hover_color="#c77dff",
                corner_radius=10,
                width=700,
                height=40,
            )
            btn.pack(pady=5)

        # Calculate GPA
        self.calculate_gpa(subjects)

    def show_subject_details(self, subject, assigns):
        # Create a popup window
        popup = ctk.CTkToplevel(self)
        popup.title(f"Details for {subject}")
        popup.geometry("600x400")
        popup.configure(fg_color=self.main_purple)

        title = ctk.CTkLabel(
            popup,
            text=f"Assignments in {subject}",
            font=("Segoe UI", 20, "bold"),
            text_color=self.text_baby_blue,
        )
        title.pack(pady=10)

        textbox = ctk.CTkTextbox(
            popup,
            width=550,
            height=300,
            corner_radius=15,
            fg_color=self.white,
            text_color="black",
            border_color=self.accent_purple,
            border_width=2,
        )
        textbox.pack(pady=10)

        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        for a in assigns:
            grade_str = (
                f"{a['grade_percent']:.2f}%"
                if a["grade_percent"] is not None
                else "Not graded"
            )
            line = f"{a['title']} | Grade: {grade_str}\n"
            textbox.insert("end", line)
        textbox.configure(state="disabled")

    def calculate_gpa(self, subjects):
        class_gpas = []
        total_weight = 0
        weighted_sum = 0

        for subj, assigns in subjects.items():
            graded = [a for a in assigns if a["grade_percent"] is not None]
            if graded:
                avg_percent = sum(a["grade_percent"] for a in graded) / len(graded)
                _, gpa = percent_to_letter_gpa(avg_percent)
                class_gpas.append(gpa)
                # Weighted by number of assignments
                weight = len(assigns)
                weighted_sum += gpa * weight
                total_weight += weight

        if class_gpas:
            unweighted = sum(class_gpas) / len(class_gpas)
            self.unweighted_gpa_label.configure(
                text=f"Unweighted GPA: {unweighted:.2f}"
            )
        else:
            self.unweighted_gpa_label.configure(text="Unweighted GPA: N/A")

        if total_weight > 0:
            weighted = weighted_sum / total_weight
            self.weighted_gpa_label.configure(text=f"Weighted GPA: {weighted:.2f}")
        else:
            self.weighted_gpa_label.configure(text="Weighted GPA: N/A")

    # ---------- TAB 6: CLASSES ----------

    def build_classes_tab(self):
        frame = self.tab_classes

        # GPA at the top
        self.classes_gpa_label = ctk.CTkLabel(
            frame,
            text="Unweighted GPA: N/A",
            font=("Segoe UI", 20, "bold"),
            text_color=self.text_baby_blue,
        )
        self.classes_gpa_label.pack(pady=10)

        # Top left buttons for + and -
        button_frame = ctk.CTkFrame(
            frame, fg_color=self.light_purple, corner_radius=15
        )
        button_frame.pack(pady=10, anchor="w", padx=20)

        add_button = ctk.CTkButton(
            button_frame,
            text="+",
            command=self.add_class,
            fg_color=self.accent_purple,
            hover_color="#c77dff",
            corner_radius=20,
            width=40,
            height=40,
        )
        add_button.pack(side="left", padx=5)

        remove_button = ctk.CTkButton(
            button_frame,
            text="-",
            command=self.remove_class,
            fg_color=self.accent_purple,
            hover_color="#c77dff",
            corner_radius=20,
            width=40,
            height=40,
        )
        remove_button.pack(side="left", padx=5)

        # Scrollable frame for classes
        self.classes_scrollable = ctk.CTkScrollableFrame(
            frame,
            width=800,
            height=300,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            border_width=2,
        )
        self.classes_scrollable.pack(pady=10)

    def refresh_classes_overview(self):
        # Clear existing widgets
        for widget in self.classes_scrollable.winfo_children():
            widget.destroy()

        # Display each class
        for i, cls in enumerate(classes):
            if cls["grade_percent"] is not None:
                letter, _ = percent_to_letter_gpa(cls["grade_percent"])
                text = f"{cls['name']} - {letter}"
            else:
                text = f"{cls['name']} - No grade"

            btn = ctk.CTkButton(
                self.classes_scrollable,
                text=text,
                command=lambda idx=i: self.edit_class_grade(idx),
                fg_color=self.accent_purple,
                hover_color="#c77dff",
                corner_radius=10,
                width=700,
                height=40,
            )
            btn.pack(pady=5)

        # Calculate overall GPA
        self.calculate_classes_gpa()

    def calculate_classes_gpa(self):
        if not classes:
            self.classes_gpa_label.configure(text="Unweighted GPA: N/A")
            return

        gpas = []
        for cls in classes:
            if cls["grade_percent"] is not None:
                _, gpa = percent_to_letter_gpa(cls["grade_percent"])
                gpas.append(gpa)

        if gpas:
            unweighted = sum(gpas) / len(gpas)
            self.classes_gpa_label.configure(text=f"Unweighted GPA: {unweighted:.2f}")
        else:
            self.classes_gpa_label.configure(text="Unweighted GPA: N/A")

    def add_class(self):
        # Popup to add class
        popup = ctk.CTkToplevel(self)
        popup.title("Add Class")
        popup.geometry("400x200")
        popup.configure(fg_color=self.main_purple)

        label = ctk.CTkLabel(
            popup,
            text="Class Name:",
            text_color=self.text_baby_blue,
        )
        label.pack(pady=10)

        entry = ctk.CTkEntry(
            popup,
            placeholder_text="Enter class name",
            width=300,
            height=40,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            border_width=2,
            text_color="black",
        )
        entry.pack(pady=10)

        def save_class():
            name = entry.get().strip()
            if name:
                classes.append({"name": name, "grade_percent": None})
                save_data()
                self.refresh_classes_overview()
            popup.destroy()

        save_button = ctk.CTkButton(
            popup,
            text="Add",
            command=save_class,
            fg_color=self.accent_purple,
            hover_color="#c77dff",
            corner_radius=20,
            width=100,
            height=40,
        )
        save_button.pack(pady=10)

    def remove_class(self):
        if not classes:
            return

        # Remove the last class for now
        classes.pop()
        save_data()
        self.refresh_classes_overview()

    def edit_class_grade(self, idx):
        cls = classes[idx]
        # Popup to edit grade
        popup = ctk.CTkToplevel(self)
        popup.title(f"Edit Grade for {cls['name']}")
        popup.geometry("400x250")
        popup.configure(fg_color=self.main_purple)

        label = ctk.CTkLabel(
            popup,
            text="Grade (%):",
            text_color=self.text_baby_blue,
        )
        label.pack(pady=10)

        entry = ctk.CTkEntry(
            popup,
            placeholder_text="Enter grade percentage",
            width=300,
            height=40,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            border_width=2,
            text_color="black",
        )
        if cls["grade_percent"] is not None:
            entry.insert(0, str(cls["grade_percent"]))
        entry.pack(pady=10)

        def save_grade():
            try:
                percent = float(entry.get().strip())
                if 0 <= percent <= 120:
                    cls["grade_percent"] = percent
                    save_data()
                    self.refresh_classes_overview()
                    popup.destroy()
                else:
                    pass
            except ValueError:
                pass

        save_button = ctk.CTkButton(
            popup,
            text="Save",
            command=save_grade,
            fg_color=self.accent_purple,
            hover_color="#c77dff",
            corner_radius=20,
            width=100,
            height=40,
        )
        save_button.pack(pady=10)

    # ---------- TAB 7: FUN (GPA SIM + STREAK + CHARTS) ----------

    def build_fun_tab(self):
        frame = self.tab_fun

        title = ctk.CTkLabel(
            frame,
            text="FUN Tools (Sim, Streaks, Charts)",
            font=("Segoe UI", 24, "bold"),
            text_color=self.text_baby_blue,
        )
        title.pack(pady=10)

        # GPA SIMULATOR
        self.fun_gpa_frame = ctk.CTkFrame(
            frame, fg_color=self.light_purple, corner_radius=15
        )
        self.fun_gpa_frame.pack(pady=8, padx=10, fill="x")

        gpa_title = ctk.CTkLabel(
            self.fun_gpa_frame,
            text="1) GPA Simulator – 'What if I bomb this test?'",
            font=("Segoe UI", 16, "bold"),
            text_color=self.text_baby_blue,
        )
        gpa_title.pack(pady=(8, 4), anchor="w", padx=10)

        gpa_row = ctk.CTkFrame(
            self.fun_gpa_frame, fg_color=self.light_purple, corner_radius=15
        )
        gpa_row.pack(pady=4, padx=10, fill="x")

        self.fun_subject_dropdown = ctk.CTkComboBox(
            gpa_row,
            values=[],
            width=250,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            text_color="black",
        )
        self.fun_subject_dropdown.pack(side="left", padx=5, pady=5)

        self.fun_sim_grade_entry = ctk.CTkEntry(
            gpa_row,
            placeholder_text="Hypothetical grade (%)",
            width=200,
            height=35,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            border_width=2,
            text_color="black",
        )
        self.fun_sim_grade_entry.pack(side="left", padx=5, pady=5)

        sim_button = ctk.CTkButton(
            gpa_row,
            text="Simulate",
            command=self.simulate_gpa_change,
            fg_color=self.accent_purple,
            hover_color="#c77dff",
            corner_radius=20,
            width=120,
            height=35,
        )
        sim_button.pack(side="left", padx=5, pady=5)

        self.fun_sim_result_label = ctk.CTkLabel(
            self.fun_gpa_frame,
            text="",
            text_color=self.text_baby_blue,
            justify="left",
        )
        self.fun_sim_result_label.pack(pady=(4, 8), padx=10, anchor="w")

        # STUDY STREAK
        self.fun_streak_frame = ctk.CTkFrame(
            frame, fg_color=self.light_purple, corner_radius=15
        )
        self.fun_streak_frame.pack(pady=8, padx=10, fill="x")

        streak_title = ctk.CTkLabel(
            self.fun_streak_frame,
            text="2) Study Streak Tracker",
            font=("Segoe UI", 16, "bold"),
            text_color=self.text_baby_blue,
        )
        streak_title.pack(pady=(8, 4), anchor="w", padx=10)

        self.fun_streak_label = ctk.CTkLabel(
            self.fun_streak_frame,
            text="Current streak: 0 days",
            text_color=self.text_baby_blue,
        )
        self.fun_streak_label.pack(pady=2, anchor="w", padx=10)

        self.fun_best_streak_label = ctk.CTkLabel(
            self.fun_streak_frame,
            text="Best streak: 0 days",
            text_color=self.text_baby_blue,
        )
        self.fun_best_streak_label.pack(pady=2, anchor="w", padx=10)

        streak_button = ctk.CTkButton(
            self.fun_streak_frame,
            text="I studied today ✅",
            command=self.log_study_today,
            fg_color=self.accent_purple,
            hover_color="#c77dff",
            corner_radius=20,
            width=160,
            height=35,
        )
        streak_button.pack(pady=6, padx=10, anchor="w")

        self.fun_streak_status_label = ctk.CTkLabel(
            self.fun_streak_frame,
            text="",
            text_color=self.text_baby_blue,
        )
        self.fun_streak_status_label.pack(pady=(0, 8), anchor="w", padx=10)

        # GRADE TREND "CHART"
        self.fun_chart_frame = ctk.CTkFrame(
            frame, fg_color=self.light_purple, corner_radius=15
        )
        self.fun_chart_frame.pack(pady=8, padx=10, fill="both", expand=True)

        chart_title = ctk.CTkLabel(
            self.fun_chart_frame,
            text="3) Grade Trend Chart (per subject)",
            font=("Segoe UI", 16, "bold"),
            text_color=self.text_baby_blue,
        )
        chart_title.pack(pady=(8, 4), anchor="w", padx=10)

        chart_controls = ctk.CTkFrame(
            self.fun_chart_frame, fg_color=self.light_purple, corner_radius=15
        )
        chart_controls.pack(pady=4, padx=10, fill="x")

        self.fun_chart_subject_dropdown = ctk.CTkComboBox(
            chart_controls,
            values=[],
            width=250,
            corner_radius=15,
            fg_color=self.white,
            border_color=self.accent_purple,
            text_color="black",
        )
        self.fun_chart_subject_dropdown.pack(side="left", padx=5, pady=5)

        show_chart_button = ctk.CTkButton(
            chart_controls,
            text="Show Chart",
            command=self.show_trend_chart,
            fg_color=self.accent_purple,
            hover_color="#c77dff",
            corner_radius=20,
            width=120,
            height=35,
        )
        show_chart_button.pack(side="left", padx=5, pady=5)

        self.fun_chart_textbox = ctk.CTkTextbox(
            self.fun_chart_frame,
            width=800,
            height=200,
            corner_radius=15,
            fg_color=self.white,
            text_color="black",
            border_color=self.accent_purple,
            border_width=2,
        )
        self.fun_chart_textbox.pack(pady=(4, 10), padx=10, fill="both", expand=True)

    def get_subject_list(self):
        """Return sorted list of subjects from assignments."""
        subjects = {a["subject"] or "No Subject" for a in assignments}
        return sorted(subjects)

    def refresh_fun_ui(self):
        # update dropdowns
        subjects = self.get_subject_list()
        if subjects:
            self.fun_subject_dropdown.configure(values=subjects, state="normal")
            self.fun_subject_dropdown.set(subjects[0])
            self.fun_chart_subject_dropdown.configure(values=subjects, state="normal")
            self.fun_chart_subject_dropdown.set(subjects[0])
        else:
            self.fun_subject_dropdown.configure(values=[], state="disabled")
            self.fun_chart_subject_dropdown.configure(values=[], state="disabled")

        # update streak labels
        current_streak, best_streak = compute_streaks()
        self.fun_streak_label.configure(
            text=f"Current streak: {current_streak} day(s)"
        )
        self.fun_best_streak_label.configure(
            text=f"Best streak: {best_streak} day(s)"
        )

        # clear sim result / chart if needed (optional)
        # self.fun_sim_result_label.configure(text="")
        # self.fun_chart_textbox.configure(state="normal")
        # self.fun_chart_textbox.delete("1.0", "end")
        # self.fun_chart_textbox.configure(state="disabled")

    def simulate_gpa_change(self):
        subj = self.fun_subject_dropdown.get().strip()
        if not subj:
            self.fun_sim_result_label.configure(
                text="Pick a subject first."
            )
            return

        hypothetical_str = self.fun_sim_grade_entry.get().strip()
        if not hypothetical_str:
            self.fun_sim_result_label.configure(
                text="Enter a hypothetical grade (e.g. 62)."
            )
            return

        try:
            hypothetical = float(hypothetical_str)
        except ValueError:
            self.fun_sim_result_label.configure(
                text="Invalid grade. Use a number like 65 or 92."
            )
            return

        if hypothetical < 0 or hypothetical > 120:
            self.fun_sim_result_label.configure(
                text="Grade out of range (0–120)."
            )
            return

        # find graded assignments for that subject
        graded = [
            a for a in assignments
            if (a.get("subject") or "No Subject") == subj
            and a.get("grade_percent") is not None
        ]

        if graded:
            current_avg = sum(a["grade_percent"] for a in graded) / len(graded)
            n = len(graded)
            new_avg = (current_avg * n + hypothetical) / (n + 1)
        else:
            current_avg = None
            new_avg = hypothetical

        if current_avg is not None:
            cur_letter, _ = percent_to_letter_gpa(current_avg)
            cur_text = f"Current avg: {current_avg:.2f}% ({cur_letter})"
        else:
            cur_text = "Current avg: N/A (no graded work yet)"

        new_letter, _ = percent_to_letter_gpa(new_avg)
        new_text = f"New avg if you get {hypothetical:.1f}%: {new_avg:.2f}% ({new_letter})"

        msg = f"{cur_text}\n{new_text}"
        self.fun_sim_result_label.configure(text=msg)

    def log_study_today(self):
        today_str = date.today().isoformat()
        if today_str not in study_log:
            study_log.append(today_str)
            save_data()
            self.fun_streak_status_label.configure(
                text=f"Logged study for {today_str}."
            )
        else:
            self.fun_streak_status_label.configure(
                text="You already logged today."
            )

        current_streak, best_streak = compute_streaks()
        self.fun_streak_label.configure(
            text=f"Current streak: {current_streak} day(s)"
        )
        self.fun_best_streak_label.configure(
            text=f"Best streak: {best_streak} day(s)"
        )

    def show_trend_chart(self):
        subj = self.fun_chart_subject_dropdown.get().strip()
        if not subj:
            return

        filtered = [
            a for a in assignments
            if (a.get("subject") or "No Subject") == subj
            and a.get("grade_percent") is not None
        ]

        self.fun_chart_textbox.configure(state="normal")
        self.fun_chart_textbox.delete("1.0", "end")

        if not filtered:
            self.fun_chart_textbox.insert(
                "end", "No graded assignments for this subject yet.\n"
            )
            self.fun_chart_textbox.configure(state="disabled")
            return

        # sort by due date if possible, else by id
        def sort_key(a):
            d = parse_due_date(a.get("due", ""))
            return (d or date.min, a["id"])

        filtered.sort(key=sort_key)

        self.fun_chart_textbox.insert(
            "end",
            f"Grade trend for subject: {subj}\n"
            "(Each bar is scaled to 0–100%)\n\n",
        )

        for idx, a in enumerate(filtered, start=1):
            g = a["grade_percent"]
            bar_len = max(1, int((g / 100.0) * 20))  # 0–100% -> 1–20 blocks
            bar = "█" * bar_len
            line = f"{idx:2d}) {g:6.2f}% | {bar}  {a['title']}\n"
            self.fun_chart_textbox.insert("end", line)

        self.fun_chart_textbox.configure(state="disabled")


if __name__ == "__main__":
    load_data()
    app = StudyApp()
    app.mainloop()
