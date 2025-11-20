import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import syllabize
import os

# Theme Definitions
THEMES = {
    "Dark": {
        "bg": "#2b2b2b",
        "fg": "#ffffff",
        "text_bg": "#3c3f41",
        "text_fg": "#ffffff",
        "entry_bg": "#3c3f41",
        "entry_fg": "#ffffff",
        "btn_bg": "#3c3f41",
        "btn_fg": "#ffffff",
        "frame_bg": "#2b2b2b",
        "label_bg": "#2b2b2b",
        "label_fg": "#ffffff",
        "select_bg": "#4b6eaf",
        "select_fg": "#ffffff"
    },
    "Light": {
        "bg": "#f0f0f0",
        "fg": "#000000",
        "text_bg": "#ffffff",
        "text_fg": "#000000",
        "entry_bg": "#ffffff",
        "entry_fg": "#000000",
        "btn_bg": "#e1e1e1",
        "btn_fg": "#000000",
        "frame_bg": "#f0f0f0",
        "label_bg": "#f0f0f0",
        "label_fg": "#000000",
        "select_bg": "#0078d7",
        "select_fg": "#ffffff"
    }
}

class LRCApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LRC Syllabizer")
        self.root.geometry("900x750")
        
        self.current_lines = []
        self.current_content = ""
        self.detected_lang = "other"
        self.current_theme = "Dark" # Default
        
        # Variables
        self.separator_var = tk.StringVar(value="plus")
        self.romanize_var = tk.BooleanVar(value=True)
        self.capitalize_var = tk.BooleanVar(value=True)
        self.custom_sep_var = tk.StringVar()
        self.theme_var = tk.StringVar(value="Dark")
        
        # --- Start Screen ---
        self.start_frame = tk.Frame(self.root)
        self.start_frame.pack(fill='both', expand=True)
        
        self.drop_label = tk.Label(self.start_frame, text="Drag & Drop .lrc File Here\n\nOR\n\nClick to Select File", 
                                   font=("Arial", 20), relief="groove", cursor="hand2")
        self.drop_label.pack(fill='both', expand=True, padx=50, pady=50)
        
        # Bind events
        self.drop_label.bind("<Button-1>", lambda e: self.select_file())
        
        # Drag and Drop registration
        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind('<<Drop>>', self.on_drop)
        
        # --- Main Screen (Initially Hidden) ---
        self.main_frame = tk.Frame(self.root)
        
        # Control Frame
        self.control_frame = tk.Frame(self.main_frame)
        self.control_frame.pack(pady=10, fill='x', padx=10)
        
        # File Info & Reset
        self.file_info_frame = tk.Frame(self.control_frame)
        self.file_info_frame.pack(side=tk.TOP, fill='x', pady=5)
        
        # Left side buttons
        self.save_btn = tk.Button(self.file_info_frame, text="Save Output", command=self.save_file)
        self.save_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.reset_btn = tk.Button(self.file_info_frame, text="Open Different File", command=self.reset_to_start)
        self.reset_btn.pack(side=tk.LEFT, padx=10)
        
        # Center Label (File Name)
        self.file_label = tk.Label(self.file_info_frame, text="No file selected", font=("Arial", 10, "bold"))
        self.file_label.pack(side=tk.LEFT, padx=20)
        
        # Right side Options button
        self.options_btn = tk.Button(self.file_info_frame, text="Options", command=self.open_options)
        self.options_btn.pack(side=tk.RIGHT, padx=10)

        # Settings Frame
        self.settings_frame = tk.LabelFrame(self.control_frame, text="Settings")
        self.settings_frame.pack(side=tk.TOP, pady=10, fill='x')
        
        # Separator Options
        self.sep_subframe = tk.Frame(self.settings_frame)
        self.sep_subframe.pack(side=tk.TOP, fill='x', padx=5, pady=5)
        
        self.sep_label = tk.Label(self.sep_subframe, text="Separator:")
        self.sep_label.pack(side=tk.LEFT)
        
        self.rb_plus = tk.Radiobutton(self.sep_subframe, text="+ (Ultra Star)", variable=self.separator_var, value="plus", command=self.update_output)
        self.rb_plus.pack(side=tk.LEFT, padx=5)
        self.rb_minus = tk.Radiobutton(self.sep_subframe, text="-", variable=self.separator_var, value="minus", command=self.update_output)
        self.rb_minus.pack(side=tk.LEFT, padx=5)
        self.rb_custom = tk.Radiobutton(self.sep_subframe, text="Custom", variable=self.separator_var, value="custom", command=self.on_separator_change)
        self.rb_custom.pack(side=tk.LEFT, padx=5)
        
        vcmd = (self.root.register(self.validate_custom_sep), '%P')
        self.custom_sep_entry = tk.Entry(self.sep_subframe, textvariable=self.custom_sep_var, validate='key', validatecommand=vcmd, state='disabled', width=20)
        self.custom_sep_entry.pack(side=tk.LEFT, padx=5)
        self.custom_sep_entry.bind('<KeyRelease>', lambda e: self.update_output())
        
        # Language Options
        self.opt_subframe = tk.Frame(self.settings_frame)
        self.opt_subframe.pack(side=tk.TOP, fill='x', padx=5, pady=5)
        
        self.romanize_check = tk.Checkbutton(self.opt_subframe, text="Romanize/Transliterate", variable=self.romanize_var, command=self.update_output)
        self.romanize_check.pack(side=tk.LEFT, padx=5)
        
        self.capitalize_check = tk.Checkbutton(self.opt_subframe, text="Capitalize First Word", variable=self.capitalize_var, command=self.update_output)
        self.capitalize_check.pack(side=tk.LEFT, padx=5)
        
        # Content Area
        self.content_frame = tk.Frame(self.main_frame)
        self.content_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Left Column
        self.left_frame = tk.Frame(self.content_frame)
        self.left_frame.pack(side=tk.LEFT, fill='both', expand=True, padx=(0, 5))
        self.lbl_orig = tk.Label(self.left_frame, text="Original LRC:")
        self.lbl_orig.pack(anchor='w')
        self.original_text = scrolledtext.ScrolledText(self.left_frame, width=40, height=25)
        self.original_text.pack(fill='both', expand=True)
        
        # Right Column
        self.right_frame = tk.Frame(self.content_frame)
        self.right_frame.pack(side=tk.LEFT, fill='both', expand=True, padx=(5, 0))
        self.lbl_res = tk.Label(self.right_frame, text="Syllabized Output:")
        self.lbl_res.pack(anchor='w')
        self.result_text = scrolledtext.ScrolledText(self.right_frame, width=40, height=25)
        self.result_text.pack(fill='both', expand=True)
        
        # Apply Initial Theme
        self.apply_theme(self.current_theme)

    def on_drop(self, event):
        file_path = event.data
        if file_path.startswith('{') and file_path.endswith('}'):
            file_path = file_path[1:-1]
        self.load_file(file_path)

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("LRC Files", "*.lrc"), ("All Files", "*.*")])
        if file_path:
            self.load_file(file_path)

    def load_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            self.current_lines = lines
            self.file_label.config(text=os.path.basename(file_path))
            self.current_filename_base = os.path.splitext(os.path.basename(file_path))[0]
            
            # Detect Language
            full_text = "".join(lines)
            self.detected_lang = syllabize.detect_language(full_text)
            
            # Configure UI based on language
            self.configure_for_language(self.detected_lang)
            
            # Check Capitalization
            all_capitalized = True
            has_text = False
            import re
            for line in lines:
                match = re.match(r'^(\[.*?\])(.*)', line)
                if match:
                    text = match.group(2).strip()
                    if text:
                        has_text = True
                        if not text[0].isupper():
                            all_capitalized = False
                            break
            
            if has_text and all_capitalized:
                self.capitalize_var.set(True)
                self.capitalize_check.config(state='disabled', text="Capitalize First Word (Already Capitalized)")
            else:
                self.capitalize_var.set(True)
                self.capitalize_check.config(state='normal', text="Capitalize First Word")
            
            # Show content
            self.original_text.delete(1.0, tk.END)
            self.original_text.insert(tk.END, full_text)
            
            # Switch to main view
            self.start_frame.pack_forget()
            self.main_frame.pack(fill='both', expand=True)
            
            self.update_output()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process file: {e}")

    def configure_for_language(self, lang):
        if lang == 'japanese':
            self.romanize_check.config(text="Romanize Japanese (Kanji/Kana -> Romaji)")
            self.romanize_var.set(True)
        elif lang == 'russian':
            self.romanize_check.config(text="Transliterate Russian (Cyrillic -> Latin)")
            self.romanize_var.set(True)
        elif lang == 'mixed':
            msg = "Mixed content detected (Japanese & Russian).\n\nProceed with mixed mode?"
            if messagebox.askyesno("Mixed Content", msg):
                self.romanize_check.config(text="Romanize/Transliterate (Mixed)")
                self.romanize_var.set(True)
            else:
                self.romanize_check.config(text="Romanize/Transliterate (Mixed)")
                self.romanize_var.set(False)
        else:
            self.romanize_check.config(text="Romanize/Transliterate (Not Available)")
            self.romanize_var.set(False)
            self.romanize_check.config(state='disabled')
            return

        self.romanize_check.config(state='normal')

    def reset_to_start(self):
        self.main_frame.pack_forget()
        self.start_frame.pack(fill='both', expand=True)
        self.current_lines = []
        self.current_content = ""
        self.current_filename_base = ""

    def get_separator(self):
        choice = self.separator_var.get()
        if choice == "plus":
            return "+"
        elif choice == "minus":
            return "-"
        elif choice == "custom":
            sep = self.custom_sep_var.get()
            return sep if sep else "+"
        return "+"

    def update_output(self):
        if not self.current_lines:
            return
            
        sep = self.get_separator()
        romanize = self.romanize_var.get()
        capitalize = self.capitalize_var.get()
        
        processed_lines = []
        for line in self.current_lines:
            processed = syllabize.process_line(line.strip(), separator=sep, romanize=romanize, capitalize=capitalize)
            processed_lines.append(processed)
            
        full_text = "\n".join(processed_lines)
        
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, full_text)
        self.current_content = full_text

    def on_separator_change(self):
        if self.separator_var.get() == "custom":
            self.custom_sep_entry.config(state='normal')
        else:
            self.custom_sep_entry.config(state='disabled')
        self.update_output()

    def validate_custom_sep(self, P):
        if len(P) > 20:
            return False
        return True

    def save_file(self):
        if not self.current_content:
            messagebox.showwarning("Warning", "No content to save.")
            return
            
        default_name = f"{self.current_filename_base} Syllabized" if hasattr(self, 'current_filename_base') and self.current_filename_base else "output"
        
        file_path = filedialog.asksaveasfilename(initialfile=default_name, defaultextension=".txt", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.current_content)
                messagebox.showinfo("Success", f"Saved to {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")

    def open_options(self):
        if hasattr(self, 'opt_win') and self.opt_win.winfo_exists():
            self.opt_win.lift()
            return

        self.opt_win = tk.Toplevel(self.root)
        self.opt_win.title("Options")
        self.opt_win.geometry("300x250")
        
        # Apply current theme to options window
        colors = THEMES[self.current_theme]
        self.opt_win.config(bg=colors["bg"])
        
        tk.Label(self.opt_win, text="Theme", font=("Arial", 12, "bold"), 
                 bg=colors["bg"], fg=colors["fg"]).pack(pady=10)
        
        tk.Radiobutton(self.opt_win, text="Dark", variable=self.theme_var, value="Dark", 
                       command=lambda: self.apply_theme("Dark"),
                       bg=colors["bg"], fg=colors["fg"], selectcolor=colors["bg"], activebackground=colors["bg"], activeforeground=colors["fg"]).pack(anchor='w', padx=20)
        
        tk.Radiobutton(self.opt_win, text="Light", variable=self.theme_var, value="Light", 
                       command=lambda: self.apply_theme("Light"),
                       bg=colors["bg"], fg=colors["fg"], selectcolor=colors["bg"], activebackground=colors["bg"], activeforeground=colors["fg"]).pack(anchor='w', padx=20)
        
        # Footer
        tk.Label(self.opt_win, text="(Made by Antigravity, 2025)", font=("Arial", 8), 
                 bg=colors["bg"], fg=colors["fg"]).pack(side=tk.BOTTOM, pady=10)

    def apply_theme(self, theme_name):
        self.current_theme = theme_name
        colors = THEMES[theme_name]
        
        # Root
        self.root.config(bg=colors["bg"])
        
        # Options Window (if open)
        if hasattr(self, 'opt_win') and self.opt_win.winfo_exists():
            self.opt_win.config(bg=colors["bg"])
            for child in self.opt_win.winfo_children():
                self.update_widget_recursive(child, colors)

        # Update all widgets in root
        for child in self.root.winfo_children():
            self.update_widget_recursive(child, colors)
            
        # Specific overrides if needed
        self.drop_label.config(bg=colors["entry_bg"], fg=colors["entry_fg"])

    def update_widget_recursive(self, widget, colors):
        try:
            w_type = widget.winfo_class()
            
            if w_type == 'Frame' or w_type == 'Labelframe':
                widget.config(bg=colors["frame_bg"])
                if w_type == 'Labelframe':
                    widget.config(fg=colors["fg"])
            
            elif w_type == 'Label':
                widget.config(bg=colors["label_bg"], fg=colors["label_fg"])
                
            elif w_type == 'Button':
                widget.config(bg=colors["btn_bg"], fg=colors["btn_fg"])
                
            elif w_type == 'Entry':
                widget.config(bg=colors["entry_bg"], fg=colors["entry_fg"], insertbackground=colors["fg"])
                
            elif w_type == 'Text':
                widget.config(bg=colors["text_bg"], fg=colors["text_fg"], insertbackground=colors["fg"])
                
            elif w_type == 'Scrollbar':
                # Attempt to style scrollbar (may vary by OS)
                widget.config(bg=colors["btn_bg"], troughcolor=colors["bg"], activebackground=colors["select_bg"])

            elif w_type == 'Checkbutton' or w_type == 'Radiobutton':
                widget.config(bg=colors["bg"], fg=colors["fg"], selectcolor=colors["bg"], activebackground=colors["bg"], activeforeground=colors["fg"])
            
            # Recurse for children
            for child in widget.winfo_children():
                self.update_widget_recursive(child, colors)
                
        except Exception:
            pass

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = LRCApp(root)
    root.mainloop()
