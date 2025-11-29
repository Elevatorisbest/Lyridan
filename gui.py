import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import syllabize
import os
import sys
import webbrowser
from config import Config

# Theme Definitions
# Key Descriptions:
# bg: Main window background color
# fg: Default text color (high contrast recommended)
# text_bg: Background color for text areas (scrolledtext)
# text_fg: Text color for text areas
# entry_bg: Background color for entry widgets
# entry_fg: Text color for entry widgets
# btn_bg: Button background color
# btn_fg: Button text color
# btn_active_bg: Button background color when hovered/active
# btn_active_fg: Button text color when hovered/active
# frame_bg: Background color for inner frames (e.g., LrcFrame, RsFrame)
# label_bg: Background color for labels (usually matches frame_bg)
# label_fg: Text color for labels
# highlight: Color for focus highlights or accents
# select_bg: Background color for selected text
# border: Border color for widgets

# Platform-specific button text color (white on Windows, black on MacOS)
IS_MACOS = sys.platform == 'darwin'
BUTTON_TEXT_COLOR = "#000000" if IS_MACOS else "#ffffff"

THEMES = {
    "Dark": {
        "bg": "#1e1e1e",
        "fg": "#ffffff",          # Changed from #cccccc for better contrast
        "text_bg": "#252526",
        "text_fg": "#d4d4d4",
        "entry_bg": "#3c3c3c",
        "entry_fg": "#cccccc",
        "btn_bg": "#0e639c",
        "btn_fg": BUTTON_TEXT_COLOR,
        "btn_active_bg": "#1177bb",
        "btn_active_fg": BUTTON_TEXT_COLOR,
        "frame_bg": "#252526",
        "label_bg": "#252526",
        "label_fg": "#ffffff",    # Changed from #cccccc for better contrast
        "highlight": "#007fd4",
        "select_bg": "#264f78",
        "border": "#3c3c3c"
    },
    "Light": {
        "bg": "#f0f0f0",
        "fg": "#000000",          # Changed from #333333 for better contrast
        "text_bg": "#ffffff",
        "text_fg": "#333333",
        "entry_bg": "#ffffff",
        "entry_fg": "#333333",
        "btn_bg": "#007acc",
        "btn_fg": BUTTON_TEXT_COLOR,
        "btn_active_bg": "#005f9e",
        "btn_active_fg": BUTTON_TEXT_COLOR,
        "frame_bg": "#ffffff",
        "label_bg": "#ffffff",
        "label_fg": "#000000",    # Changed from #333333 for better contrast
        "highlight": "#007acc",
        "select_bg": "#add6ff",
        "border": "#cccccc"
    },
    "Lyridan Dark": {
        "bg": "#000000",
        "fg": "#fbeb4e",
        "text_bg": "#0a0a0a",
        "text_fg": "#ffffff",
        "entry_bg": "#1a1a1a",
        "entry_fg": "#fbeb4e",
        "btn_bg": "#fbeb4e",
        "btn_fg": "#000000",
        "btn_active_bg": "#fff176",
        "btn_active_fg": "#000000",
        "frame_bg": "#0a0a0a",
        "label_bg": "#0a0a0a",
        "label_fg": "#fbeb4e",
        "highlight": "#fbeb4e",
        "select_bg": "#333333",
        "border": "#fbeb4e"
    }
}

FONT_MAIN = ("Segoe UI", 10)
FONT_HEADER = ("Segoe UI", 20, "bold")
FONT_SUBHEADER = ("Segoe UI", 12)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_ITALIC = ("Segoe UI", 9, "italic")

class ToolTip(object):
    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(self.tooltip, text=self.text, justify='left',
                         background="#ffffe0", foreground="#000000",
                         relief='solid', borderwidth=1,
                         font=("Segoe UI", 9))
        label.pack(ipadx=5, ipady=2)

    def leave(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class TimedWarningDialog(tk.Frame):
    def __init__(self, parent, title, message, duration, config_key, config):
        super().__init__(parent)
        self.config = config
        self.config_key = config_key
        self.duration = duration
        self.remaining = duration
        self.parent = parent
        
        # Configure the dialog frame itself (centered box)
        self.configure(bg='#2d2d2d', bd=2, relief='raised')
        self.place(relx=0.5, rely=0.5, anchor='center', width=600, height=450)
        
        # Title
        title_label = tk.Label(self, text=title, font=("Segoe UI", 12, "bold"), bg='#2d2d2d', fg='#ffffff')
        title_label.pack(pady=(20, 10))
        
        # Message
        # Message
        msg_label = tk.Label(self, text=message, wraplength=550, justify="center", anchor="center", font=FONT_MAIN, bg='#2d2d2d', fg='#ffffff')
        msg_label.pack(pady=(0, 20), padx=20, expand=True, fill="both")
        
        # Timer label
        self.timer_label = tk.Label(self, text=f"You can close this dialog in {self.remaining} seconds...", font=FONT_ITALIC, bg='#2d2d2d', fg='#cccccc')
        self.timer_label.pack(pady=10)
        
        # Checkbox
        # Checkbox
        checkbox_fg = "#ffffff" # Always white on dark background
        self.dont_show_var = tk.BooleanVar(value=False)
        self.check = tk.Checkbutton(self, text="Don't show this again", variable=self.dont_show_var, font=FONT_MAIN, 
                                    bg='#2d2d2d', fg=checkbox_fg, 
                                    selectcolor='#2d2d2d', activebackground='#2d2d2d', activeforeground=checkbox_fg,
                                    highlightthickness=0, bd=0, state="disabled",
                                    disabledforeground="#aaaaaa")
        self.check.pack(pady=10)
        
        # OK button (disabled initially)
        # Grayed out style for disabled state
        self.ok_btn = tk.Button(self, text="OK", command=self.on_ok, state="disabled", font=FONT_MAIN, relief="flat", cursor="hand2", width=10, 
                                bg='#444444', fg='#888888',
                                highlightthickness=0, bd=0, highlightbackground='#2d2d2d')
        self.ok_btn.pack(pady=15)
        
        # Disable interaction with parent
        self.grab_set()
        self.focus_set()
        
        # Start countdown
        self.update_timer()
    
    def update_timer(self):
        if self.remaining > 0:
            self.timer_label.config(text=f"You can close this dialog in {self.remaining} seconds...")
            self.remaining -= 1
            self.after(1000, self.update_timer)
        else:
            self.timer_label.config(text="You may now close this dialog.")
            self.check.config(state="normal")
            self.ok_btn.config(state="normal", bg='#0e639c', fg=BUTTON_TEXT_COLOR)
    
    def on_ok(self):
        if self.dont_show_var.get():
            self.config.set(self.config_key, False)
        self.destroy()

class LRCApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lyridan")
        self.geometry("1000x700")
        self.minsize(900, 600)
        
        # Set window icon
        try:
            # Get the correct base path for both script and frozen executable
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                base_path = sys._MEIPASS
            else:
                # Running as script
                base_path = os.path.dirname(__file__)
            
            icon_path = os.path.join(base_path, 'lyridanlogo.ico')
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception as e:
            print(f"Could not load icon: {e}")
        
        # Initialize config
        self.config = Config()
        
        self.current_theme = self.config.get('theme', 'Dark')
        self.colors = THEMES[self.current_theme]
        
        self.apply_global_palette()
        
        self.configure(bg=self.colors["bg"])
        
        self.container = tk.Frame(self, bg=self.colors["bg"])
        self.container.place(relx=0.5, rely=0.5, anchor="center", width=900, height=600)
        
        self.frames = {}
        
        for F in (LandingPage, LRCFrame, RocksmithFrame, OptionsFrame):
            page_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            
        self.show_frame("LandingPage")
        
    def apply_global_palette(self):
        self.tk_setPalette(
            background=self.colors["bg"], 
            foreground=self.colors["fg"],
            activeBackground=self.colors["btn_active_bg"],
            activeForeground=self.colors["btn_active_fg"],
            selectColor=self.colors["select_bg"],
            selectBackground=self.colors["select_bg"],
            selectForeground=self.colors["fg"]
        )

    def show_frame(self, page_name, data=None):
        frame = self.frames[page_name]
        frame.tkraise()
        frame.update_theme(self.colors)
        if data:
            frame.load_data(data)

    def apply_theme(self, theme_name):
        self.current_theme = theme_name
        self.colors = THEMES[theme_name]
        
        self.apply_global_palette()
        self.configure(bg=self.colors["bg"])
        self.container.configure(bg=self.colors["bg"])
        
        for frame in self.frames.values():
            frame.update_theme(self.colors)

class LandingPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg=controller.colors["bg"])
        
        # Top Bar
        self.top_bar = tk.Frame(self, bg=controller.colors["bg"])
        self.top_bar.pack(fill="x", padx=20, pady=15)
        
        self.options_btn = tk.Button(self.top_bar, text="Options", command=self.open_options, font=FONT_MAIN, relief="flat", padx=10, cursor="hand2")
        self.options_btn.pack(side="right")
        
        # Content Frame
        self.content_frame = tk.Frame(self, bg=controller.colors["bg"])
        self.content_frame.pack(fill="both", expand=True)
        
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(1, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)
        
        # Left Side
        self.lrc_frame = tk.Frame(self.content_frame, bg=controller.colors["frame_bg"], bd=0)
        self.lrc_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
        self.lrc_label = tk.Label(self.lrc_frame, text="LRC Syllabizer", font=FONT_HEADER)
        self.lrc_label.pack(pady=(60, 20))
        
        self.lrc_desc = tk.Label(self.lrc_frame, text="Romanize & Syllabize .lrc files\nExport to .txt", font=FONT_SUBHEADER)
        self.lrc_desc.pack(pady=10)
        
        self.lrc_btn = tk.Button(self.lrc_frame, text="Select .lrc File", command=self.select_lrc, font=FONT_SUBHEADER, height=2, relief="flat", cursor="hand2")
        self.lrc_btn.pack(pady=30, padx=60, fill="x")
        
        self.lrc_drop_label = tk.Label(self.lrc_frame, text="Drag & Drop .lrc here", font=FONT_ITALIC)
        self.lrc_drop_label.pack(pady=10, fill="both", expand=True)
        
        # Right Side
        self.rs_frame = tk.Frame(self.content_frame, bg=controller.colors["frame_bg"], bd=0)
        self.rs_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        self.rs_label = tk.Label(self.rs_frame, text="Rocksmith Creator", font=FONT_HEADER)
        self.rs_label.pack(pady=(60, 20))
        
        self.rs_desc = tk.Label(self.rs_frame, text="Create Rocksmith Vocal XML\nfrom .ttml / .ttmf files", font=FONT_SUBHEADER)
        self.rs_desc.pack(pady=10)
        
        self.rs_btn = tk.Button(self.rs_frame, text="Select .ttml File", command=self.select_rs, font=FONT_SUBHEADER, height=2, relief="flat", cursor="hand2")
        self.rs_btn.pack(pady=30, padx=60, fill="x")
        
        self.rs_drop_label = tk.Label(self.rs_frame, text="Drag & Drop .ttml here", font=FONT_ITALIC)
        self.rs_drop_label.pack(pady=10, fill="both", expand=True)
        
        self.lrc_frame.drop_target_register(DND_FILES)
        self.lrc_frame.dnd_bind('<<Drop>>', self.drop_lrc)
        self.rs_frame.drop_target_register(DND_FILES)
        self.rs_frame.dnd_bind('<<Drop>>', self.drop_rs)

    def open_options(self):
        self.controller.show_frame("OptionsFrame", data="LandingPage")
        
    def update_theme(self, colors):
        self.configure(bg=colors["bg"])
        self.top_bar.configure(bg=colors["bg"])
        self.content_frame.configure(bg=colors["bg"])
        self.options_btn.configure(bg=colors["btn_bg"], fg=colors["btn_fg"], activebackground=colors["btn_active_bg"], activeforeground=colors["btn_active_fg"])
        
        self.lrc_frame.configure(bg=colors["frame_bg"])
        self.rs_frame.configure(bg=colors["frame_bg"])
        
        for widget in self.lrc_frame.winfo_children():
            if isinstance(widget, tk.Label):
                widget.configure(bg=colors["frame_bg"], fg=colors["fg"])
            elif isinstance(widget, tk.Button):
                widget.configure(bg=colors["btn_bg"], fg=colors["btn_fg"], activebackground=colors["btn_active_bg"], activeforeground=colors["btn_active_fg"])
                
        for widget in self.rs_frame.winfo_children():
            if isinstance(widget, tk.Label):
                widget.configure(bg=colors["frame_bg"], fg=colors["fg"])
            elif isinstance(widget, tk.Button):
                widget.configure(bg=colors["btn_bg"], fg=colors["btn_fg"], activebackground=colors["btn_active_bg"], activeforeground=colors["btn_active_fg"])

    def select_lrc(self):
        file_path = filedialog.askopenfilename(filetypes=[("LRC Files", "*.lrc"), ("All Files", "*.*")])
        if file_path:
            self.controller.show_frame("LRCFrame", data=file_path)

    def drop_lrc(self, event):
        file_path = event.data.strip('{}')
        if file_path.lower().endswith('.lrc'):
            self.controller.show_frame("LRCFrame", data=file_path)
        else:
            messagebox.showerror("Error", "Please drop an .lrc file here.")

    def select_rs(self):
        file_path = filedialog.askopenfilename(filetypes=[("TTML Files", "*.ttml *.ttmf"), ("All Files", "*.*")])
        if file_path:
            self.controller.show_frame("RocksmithFrame", data=file_path)

    def drop_rs(self, event):
        file_path = event.data.strip('{}')
        if file_path.lower().endswith(('.ttml', '.ttmf')):
            self.controller.show_frame("RocksmithFrame", data=file_path)
        else:
            messagebox.showerror("Error", "Please drop a .ttml or .ttmf file here.")

class LRCFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.current_file_path = None
        self.current_lines = []
        
        self.top_bar = tk.Frame(self)
        self.top_bar.pack(fill="x", padx=20, pady=15)
        
        self.back_btn = tk.Button(self.top_bar, text="< Back", command=lambda: controller.show_frame("LandingPage"), font=FONT_MAIN, relief="flat", padx=10, cursor="hand2")
        self.back_btn.pack(side="left")
        
        self.save_btn = tk.Button(self.top_bar, text="Save Output", command=self.save_file, state="disabled", font=FONT_MAIN, relief="flat", padx=10, cursor="hand2")
        self.save_btn.pack(side="left", padx=10)
        
        self.options_btn = tk.Button(self.top_bar, text="Options", command=self.open_options, font=FONT_MAIN, relief="flat", padx=10, cursor="hand2")
        self.options_btn.pack(side="right")
        
        self.content_frame = tk.Frame(self)
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        self.left_frame = tk.Frame(self.content_frame)
        self.left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        tk.Label(self.left_frame, text="Original", font=FONT_BOLD).pack(anchor="w", pady=(0, 5))
        self.text_original = scrolledtext.ScrolledText(self.left_frame, width=40, height=20, font=("Consolas", 10), relief="flat", bd=0)
        self.text_original.pack(fill="both", expand=True)
        
        self.right_frame = tk.Frame(self.content_frame)
        self.right_frame.pack(side="right", fill="both", expand=True, padx=(10, 0))
        tk.Label(self.right_frame, text="Syllabized", font=FONT_BOLD).pack(anchor="w", pady=(0, 5))
        self.text_syllabized = scrolledtext.ScrolledText(self.right_frame, width=40, height=20, font=("Consolas", 10), relief="flat", bd=0)
        self.text_syllabized.pack(fill="both", expand=True)
        
        self.controls_frame = tk.Frame(self)
        self.controls_frame.pack(fill="x", padx=20, pady=20)
        
        tk.Label(self.controls_frame, text="Separator:", font=FONT_MAIN).pack(side="left")
        self.separator_var = tk.StringVar(value="+")
        tk.Radiobutton(self.controls_frame, text="+", variable=self.separator_var, value="+", command=self.process_current_file, font=FONT_MAIN).pack(side="left", padx=5)
        tk.Radiobutton(self.controls_frame, text="-", variable=self.separator_var, value="-", command=self.process_current_file, font=FONT_MAIN).pack(side="left", padx=5)
        tk.Radiobutton(self.controls_frame, text="Custom", variable=self.separator_var, value="custom", command=self.toggle_custom_separator, font=FONT_MAIN).pack(side="left", padx=5)
        
        self.custom_sep_entry = tk.Entry(self.controls_frame, width=8, state="disabled", font=FONT_MAIN, relief="flat", bd=1)
        self.custom_sep_entry.pack(side="left", padx=5)
        self.custom_sep_entry.bind("<KeyRelease>", lambda e: self.process_current_file())
        
        self.romanize_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.controls_frame, text="Romanize/Transliterate", variable=self.romanize_var, command=self.process_current_file, font=FONT_MAIN).pack(side="left", padx=20)
        
        self.capitalize_var = tk.BooleanVar(value=True)
        self.cap_check = tk.Checkbutton(self.controls_frame, text="Capitalize First Word", variable=self.capitalize_var, command=self.process_current_file, font=FONT_MAIN)
        self.cap_check.pack(side="left", padx=10)

    def update_theme(self, colors):
        self.configure(bg=colors["bg"])
        self.top_bar.configure(bg=colors["bg"])
        self.content_frame.configure(bg=colors["bg"])
        self.left_frame.configure(bg=colors["bg"])
        self.right_frame.configure(bg=colors["bg"])
        self.controls_frame.configure(bg=colors["bg"])
        
        def update_recursive(widget):
            try:
                if isinstance(widget, (tk.Label, tk.Radiobutton, tk.Checkbutton)):
                    widget.configure(bg=colors["bg"], fg=colors["fg"], selectcolor=colors["bg"], activebackground=colors["bg"], activeforeground=colors["fg"])
                elif isinstance(widget, tk.Button):
                    widget.configure(bg=colors["btn_bg"], fg=colors["btn_fg"], activebackground=colors["btn_active_bg"], activeforeground=colors["btn_active_fg"])
                elif isinstance(widget, tk.Entry):
                    widget.configure(bg=colors["entry_bg"], fg=colors["entry_fg"], insertbackground=colors["fg"], 
                                     highlightbackground=colors["border"], highlightcolor=colors["highlight"], highlightthickness=1,
                                     disabledbackground=colors["entry_bg"], disabledforeground=colors["entry_fg"])
                elif isinstance(widget, scrolledtext.ScrolledText):
                    widget.configure(bg=colors["text_bg"], fg=colors["text_fg"], insertbackground=colors["fg"], selectbackground=colors["select_bg"],
                                     highlightbackground=colors["border"], highlightcolor=colors["highlight"], highlightthickness=1)
            except: pass
            for child in widget.winfo_children():
                update_recursive(child)
        update_recursive(self)

    def load_data(self, file_path):
        self.current_file_path = file_path
        self.save_btn.config(state="normal")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.current_lines = content.splitlines()
            self.text_original.delete(1.0, tk.END)
            self.text_original.insert(tk.END, content)
            
            all_caps = True
            has_text = False
            for line in self.current_lines:
                import re
                match = re.match(r'^(\[.*?\])(.*)', line)
                if match:
                    text = match.group(2).strip()
                    if text:
                        has_text = True
                        if not text[0].isupper():
                            all_caps = False
                            break
            if has_text and all_caps:
                self.capitalize_var.set(False)
                self.cap_check.config(state="disabled")
            else:
                self.cap_check.config(state="normal")
                
            sample_text = "".join(self.current_lines[:10])
            lang = syllabize.detect_language(sample_text)
            if lang == 'mixed':
                messagebox.showwarning("Mixed Content", "Detected both Japanese and Russian characters. Processing might be inaccurate.")
            self.process_current_file()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file: {e}")

    def toggle_custom_separator(self):
        if self.separator_var.get() == "custom":
            self.custom_sep_entry.config(state="normal")
        else:
            self.custom_sep_entry.config(state="disabled")
        self.process_current_file()

    def process_current_file(self):
        if not self.current_lines:
            return
        sep = self.separator_var.get()
        if sep == "custom":
            sep = self.custom_sep_entry.get()
            if len(sep) > 20:
                sep = sep[:20]
                self.custom_sep_entry.delete(0, tk.END)
                self.custom_sep_entry.insert(0, sep)
        romanize = self.romanize_var.get()
        capitalize = self.capitalize_var.get()
        processed_lines = []
        for line in self.current_lines:
            processed = syllabize.process_line(line, separator=sep, romanize=romanize, capitalize=capitalize)
            processed_lines.append(processed)
        self.text_syllabized.delete(1.0, tk.END)
        self.text_syllabized.insert(tk.END, "\n".join(processed_lines))

    def save_file(self):
        if not self.current_file_path:
            return
        
        # Show warning if enabled
        if self.controller.config.get('warnings.lrc_save', True):
            dialog = TimedWarningDialog(
                self.controller.container, 
                "Important Information", 
                "This tool is not intended as a complete replacement of syllabization and romanization/transliteration.\n\n"
                "Incorrect syllabization and romanization/transliteration may occur.\n\n"
                "Please verify the accuracy of the results prior to implementing it in a Rocksmith chart.",
                5,
                'warnings.lrc_save',
                self.controller.config
            )
            # Wait for dialog to close
            self.wait_window(dialog)
        
        base = os.path.splitext(os.path.basename(self.current_file_path))[0]
        output_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")], initialfile=f"{base} Syllabized.txt")
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(self.text_syllabized.get(1.0, tk.END))
                messagebox.showinfo("Success", "File saved successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")

    def open_options(self):
        self.controller.show_frame("OptionsFrame", data="LRCFrame")

class RocksmithFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.ttml_path = None
        self.beatmap_path = None
        
        self.top_bar = tk.Frame(self)
        self.top_bar.pack(fill="x", padx=20, pady=15)
        
        self.back_btn = tk.Button(self.top_bar, text="< Back", command=lambda: controller.show_frame("LandingPage"), font=FONT_MAIN, relief="flat", padx=10, cursor="hand2")
        self.back_btn.pack(side="left")
        
        self.options_btn = tk.Button(self.top_bar, text="Options", command=self.open_options, font=FONT_MAIN, relief="flat", padx=10, cursor="hand2")
        self.options_btn.pack(side="right")
        
        self.content_frame = tk.Frame(self)
        self.content_frame.pack(fill="both", expand=True, padx=40, pady=20)
        
        tk.Label(self.content_frame, text="Rocksmith XML Creator", font=FONT_HEADER).pack(pady=(0, 30))
        
        tk.Label(self.content_frame, text="Lyrics File (.ttml / .ttmf):", font=FONT_BOLD).pack(anchor="w")
        self.ttml_entry = tk.Entry(self.content_frame, width=50, font=FONT_MAIN, relief="flat", bd=1)
        self.ttml_entry.pack(fill="x", pady=5)
        tk.Button(self.content_frame, text="Browse...", command=self.browse_ttml, font=FONT_MAIN, relief="flat", cursor="hand2").pack(anchor="e", pady=(0, 20))
        
        tk.Label(self.content_frame, text="Rocksmith Arrangement File synced to the beat (eg. \"PART REAL_GUITAR_RS2.xml\"):", font=FONT_BOLD).pack(anchor="w")
        self.beatmap_entry = tk.Entry(self.content_frame, width=50, font=FONT_MAIN, relief="flat", bd=1)
        self.beatmap_entry.pack(fill="x", pady=5)
        tk.Button(self.content_frame, text="Browse...", command=self.browse_beatmap, font=FONT_MAIN, relief="flat", cursor="hand2").pack(anchor="e", pady=(0, 20))
        
        # Options
        self.offset_var = tk.BooleanVar(value=True)
        self.offset_check = tk.Checkbutton(self.content_frame, text="Add 10s Offset", variable=self.offset_var, font=FONT_MAIN)
        self.offset_check.pack(anchor="w", pady=(10, 5))
        ToolTip(self.offset_check, "10 seconds of silence added to start of the song audio are required for Rocksmith CDLCs to function correctly and to follow charting standards.")
        
        self.empty_measure_var = tk.BooleanVar(value=False)
        self.empty_measure_check = tk.Checkbutton(self.content_frame, text="Account For 1st Empty Measure", variable=self.empty_measure_var, font=FONT_MAIN)
        self.empty_measure_check.pack(anchor="w", pady=5)
        ToolTip(self.empty_measure_check, "Accounts for an empty measure at the beginning of the chart which is required by charting standards. Adds the duration of one measure to the offset.")
        
        self.gen_btn = tk.Button(self.content_frame, text="Generate Rocksmith XML", command=self.generate, font=FONT_SUBHEADER, height=2, relief="flat", cursor="hand2")
        self.gen_btn.pack(fill="x", pady=30)
        
        self.status_label = tk.Label(self.content_frame, text="", font=FONT_MAIN)
        self.status_label.pack()

    def update_theme(self, colors):
        self.configure(bg=colors["bg"])
        self.top_bar.configure(bg=colors["bg"])
        self.content_frame.configure(bg=colors["bg"])
        
        def update_recursive(widget):
            try:
                if isinstance(widget, (tk.Label, tk.Checkbutton)):
                    widget.configure(bg=colors["bg"], fg=colors["fg"], selectcolor=colors["bg"], activebackground=colors["bg"], activeforeground=colors["fg"])
                elif isinstance(widget, tk.Button):
                    widget.configure(bg=colors["btn_bg"], fg=colors["btn_fg"], activebackground=colors["btn_active_bg"], activeforeground=colors["btn_active_fg"])
                elif isinstance(widget, tk.Entry):
                    widget.configure(bg=colors["entry_bg"], fg=colors["entry_fg"], insertbackground=colors["fg"],
                                     highlightbackground=colors["border"], highlightcolor=colors["highlight"], highlightthickness=1,
                                     disabledbackground=colors["entry_bg"], disabledforeground=colors["entry_fg"])
            except: pass
            for child in widget.winfo_children():
                update_recursive(child)
        update_recursive(self)

    def load_data(self, file_path):
        self.ttml_path = file_path
        self.ttml_entry.delete(0, tk.END)
        self.ttml_entry.insert(0, file_path)

    def browse_ttml(self):
        path = filedialog.askopenfilename(filetypes=[("TTML Files", "*.ttml *.ttmf"), ("All Files", "*.*")])
        if path:
            self.load_data(path)

    def browse_beatmap(self):
        path = filedialog.askopenfilename(filetypes=[("XML Files", "*.xml"), ("All Files", "*.*")])
        if path:
            self.beatmap_path = path
            self.beatmap_entry.delete(0, tk.END)
            self.beatmap_entry.insert(0, path)

    def generate(self):
        ttml = self.ttml_entry.get()
        beatmap = self.beatmap_entry.get()
        offset = 10.0 if self.offset_var.get() else 0.0
        empty_measure = self.empty_measure_var.get()
        
        if not ttml:
            messagebox.showerror("Error", "Please select a lyrics file.")
            return
        if not beatmap:
            messagebox.showerror("Error", "Please select a Rocksmith Arrangement File with beatmap.")
            return
            
        try:
            data = syllabize.extract_ttml_data(ttml)
            if not data:
                messagebox.showerror("Error", "No lyrics found in TTML file.")
                return
            output_path = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML Files", "*.xml")], initialfile="vocals_rs.xml")
            if output_path:
                # Show warning if enabled
                if self.controller.config.get('warnings.rocksmith_export', True):
                    dialog = TimedWarningDialog(
                        self.controller.container,
                        "Important Information",
                        "This tool is not intended as a complete replacement of creating an accurate Rocksmith Vocal Arrangement file.\n\n"
                        "It is recommended to use this tool as a starting point and manually adjust the timing and syllabization as needed.\n\n"
                        "Romanization may be incorrect, and syllabizations and timing accuracy for words or syllabes are dependent on the provided lyric file, and can vary by song or source.\n\n"
                        "Please verify the accuracy of the results prior to implementing it in a Rocksmith chart.",
                        10,
                        'warnings.rocksmith_export',
                        self.controller.config
                    )
                    self.wait_window(dialog)
                
                success = syllabize.export_rocksmith_xml(data, output_path, offset, beatmap, empty_measure)
                if success:
                    self.status_label.config(text="Export Successful!", fg="green")
                    messagebox.showinfo("Success", "Rocksmith XML generated successfully!")
                else:
                    self.status_label.config(text="Export Failed.", fg="red")
                    messagebox.showerror("Error", "Failed to generate XML.")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

    def open_options(self):
        self.controller.show_frame("OptionsFrame", data="RocksmithFrame")

class OptionsFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.return_to = "LandingPage"
        
        self.top_bar = tk.Frame(self)
        self.top_bar.pack(fill="x", padx=20, pady=15)
        
        self.back_btn = tk.Button(self.top_bar, text="< Back", command=self.go_back, font=FONT_MAIN, relief="flat", padx=10, cursor="hand2")
        self.back_btn.pack(side="left")
        
        self.content_frame = tk.Frame(self)
        self.content_frame.pack(fill="both", expand=True, padx=40, pady=20)
        
        tk.Label(self.content_frame, text="Options", font=FONT_HEADER).pack(pady=(0, 30))
        
        # Theme section
        tk.Label(self.content_frame, text="Theme", font=FONT_BOLD).pack(pady=(20, 10))
        self.theme_var = tk.StringVar(value=self.controller.current_theme)
        tk.Radiobutton(self.content_frame, text="Dark", variable=self.theme_var, value="Dark", command=self.change_theme, font=FONT_MAIN).pack()
        tk.Radiobutton(self.content_frame, text="Light", variable=self.theme_var, value="Light", command=self.change_theme, font=FONT_MAIN).pack()
        tk.Radiobutton(self.content_frame, text="Lyridan Dark", variable=self.theme_var, value="Lyridan Dark", command=self.change_theme, font=FONT_MAIN).pack()
        
        # Warnings section
        tk.Label(self.content_frame, text="Warnings", font=FONT_BOLD).pack(pady=(20, 10))
        self.reset_btn = tk.Button(self.content_frame, text="Reset Warning Acknowledgments", 
                                     command=self.reset_warnings, font=FONT_MAIN, relief="flat", cursor="hand2")
        self.reset_btn.pack(pady=10)
        
        # Footer with GitHub link
        footer_frame = tk.Frame(self.content_frame)
        footer_frame.pack(side="bottom", pady=20)
        
        tk.Label(footer_frame, text="Made by Elevatorisbest using Antigravity IDE, 2025, version 1.1.0", font=("Segoe UI", 9)).pack()
        
        github_link = tk.Label(footer_frame, text="GitHub", font=("Segoe UI", 9, "underline"), fg="#007acc", cursor="hand2")
        github_link.pack()
        github_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/Elevatorisbest/Lyridan"))

    def update_theme(self, colors):
        self.configure(bg=colors["bg"])
        self.top_bar.configure(bg=colors["bg"])
        self.content_frame.configure(bg=colors["bg"])
        
        def update_recursive(widget):
            try:
                if isinstance(widget, (tk.Label, tk.Radiobutton)):
                    # Preserve GitHub link color
                    if hasattr(widget, 'cget') and 'underline' in str(widget.cget('font')):
                        widget.configure(bg=colors["bg"])
                    else:
                        widget.configure(bg=colors["bg"], fg=colors["fg"], selectcolor=colors["bg"], activebackground=colors["bg"], activeforeground=colors["fg"])
                elif isinstance(widget, tk.Button):
                    widget.configure(bg=colors["btn_bg"], fg=colors["btn_fg"], activebackground=colors["btn_active_bg"], activeforeground=colors["btn_active_fg"])
                elif isinstance(widget, tk.Frame):
                    widget.configure(bg=colors["bg"])
            except: pass
            for child in widget.winfo_children():
                update_recursive(child)
        update_recursive(self)

    def load_data(self, data):
        if data:
            self.return_to = data

    def go_back(self):
        self.controller.show_frame(self.return_to)

    def change_theme(self):
        self.controller.config.set('theme', self.theme_var.get())
        self.controller.apply_theme(self.theme_var.get())
    
    def reset_warnings(self):
        self.controller.config.reset_warnings()
        messagebox.showinfo("Success", "Warning acknowledgments have been reset.")

if __name__ == "__main__":
    app = LRCApp()
    app.mainloop()
