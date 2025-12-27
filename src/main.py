
import time
import threading
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
import os

console = Console()

try:
    import customtkinter as ctk
    from PIL import Image
    GUI_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    GUI_AVAILABLE = False
    console.print("[yellow]Warning: tkinter/customtkinter not found. Falling back to Terminal Dashboard.[/yellow]")

def simulate_boot():
    console.clear()
    console.print("[bold blue]OmniOS Phase 1: Kernel Initialization[/bold blue]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        t1 = progress.add_task("[cyan]Loading AI Core...", total=100)
        t2 = progress.add_task("[magenta]Initializing Neural Bridge...", total=100)
        t3 = progress.add_task("[green]Mounting COSMIC Desktop Extensions...", total=100)

        while not progress.finished:
            progress.update(t1, advance=0.5)
            progress.update(t2, advance=0.3)
            progress.update(t3, advance=0.4)
            time.sleep(0.01)

    console.print("[bold green]OmniOS Ready.[/bold green]")
    time.sleep(1)

def run_tui():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3)
    )
    
    layout["main"].split_row(
        Layout(name="sidebar", size=30),
        Layout(name="content")
    )

    def get_dashboard():
        content = Text()
        content.append("\n   Witaj w OmniOS (TUI Mode)\n", style="bold white")
        content.append("   Twoje środowisko natywnej sztucznej inteligencji.\n\n", style="italic gray")
        
        content.append("   [ CPU AI LOAD  ] [ 12% ]\n", style="cyan")
        content.append("   [ NEURAL RAM   ] [ 4.2 GB ]\n", style="magenta")
        content.append("   [ AGENT UPTIME ] [ 00:04:12 ]\n", style="yellow")
        
        return Panel(content, title="Dashboard", border_style="blue")

    layout["header"].update(Panel(Text("OmniOS v1.0.0-alpha", justify="center", style="bold blue")))
    layout["sidebar"].update(Panel(Text("\n 1. Dashboard\n\n 2. AI Agent\n\n 3. Settings\n\n 4. Exit", style="white"), title="Menu"))
    layout["content"].update(get_dashboard())
    layout["footer"].update(Panel(Text("Status: SYSTEM ONLINE | AI Active", justify="center", style="green")))

    with Live(layout, refresh_per_second=4, screen=True):
        time.sleep(5) # Show for a bit in this demo
        console.clear()
        console.print("[bold green]OmniOS TUI Session Active.[/bold green]")
        console.print("Dostępne komendy: [bold cyan]help, status, exit[/bold cyan]")
        while True:
            cmd = console.input("[bold blue]OmniOS[/bold blue] > ")
            if cmd.lower() in ['exit', 'quit']:
                break
            elif cmd.lower() == 'help':
                console.print("OmniOS AI System Help: ...")
            else:
                console.print(f"OmniOS AI: Przetwarzam komendę '{cmd}'...")

if GUI_AVAILABLE:
    class OmniOSApp(ctk.CTk):
        def __init__(self):
            super().__init__()
            # ... (rest of the class remains the same)
            self.title("OmniOS v1.0.0-alpha")
            self.geometry("1100x700")
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
            self.grid_columnconfigure(1, weight=1)
            self.grid_rowconfigure(0, weight=1)
            self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
            self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
            self.sidebar_frame.grid_rowconfigure(4, weight=1)
            self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="OmniOS", font=ctk.CTkFont(size=24, weight="bold"))
            self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
            self.status_indicator = ctk.CTkLabel(self.sidebar_frame, text="● SYSTEM ONLINE", text_color="#2ecc71", font=ctk.CTkFont(size=11))
            self.status_indicator.grid(row=1, column=0, padx=20, pady=(0, 20))
            self.sidebar_button_1 = ctk.CTkButton(self.sidebar_frame, text="Dashboard", command=self.show_dashboard)
            self.sidebar_button_1.grid(row=2, column=0, padx=20, pady=10)
            self.sidebar_button_2 = ctk.CTkButton(self.sidebar_frame, text="AI Agent", command=self.show_ai_agent)
            self.sidebar_button_2.grid(row=3, column=0, padx=20, pady=10)
            self.main_content = ctk.CTkFrame(self, corner_radius=15, fg_color="transparent")
            self.main_content.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
            self.show_dashboard()

        def show_dashboard(self):
            for widget in self.main_content.winfo_children(): widget.destroy()
            ctk.CTkLabel(self.main_content, text="Witaj w OmniOS", font=ctk.CTkFont(size=32, weight="bold")).pack(pady=(20, 10))
            ctk.CTkLabel(self.main_content, text="Twoje środowisko natywnej sztucznej inteligencji.", font=ctk.CTkFont(size=16)).pack(pady=(0, 30))
            stats_frame = ctk.CTkFrame(self.main_content, fg_color="transparent")
            stats_frame.pack(fill="x", padx=40)
            self.create_stat_card(stats_frame, "CPU AI LOAD", "12%", "#3498db").grid(row=0, column=0, padx=10, pady=10)
            self.create_stat_card(stats_frame, "NEURAL RAM", "4.2 GB", "#9b59b6").grid(row=0, column=1, padx=10, pady=10)
            self.create_stat_card(stats_frame, "AGENT UPTIME", "00:04:12", "#e67e22").grid(row=0, column=2, padx=10, pady=10)

        def create_stat_card(self, parent, title, value, color):
            card = ctk.CTkFrame(parent, width=200, height=120, border_width=2, border_color=color)
            card.grid_propagate(False)
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(15, 5))
            ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=24, weight="bold"), text_color=color).pack(pady=5)
            return card

        def show_ai_agent(self):
            for widget in self.main_content.winfo_children(): widget.destroy()
            ctk.CTkLabel(self.main_content, text="AI Command Center", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=20)
            self.chat_box = ctk.CTkTextbox(self.main_content, width=600, height=300)
            self.chat_box.pack(padx=20, pady=10)
            self.chat_box.insert("0.0", "System: AI Agent initialized and waiting for commands...\n\n")
            self.chat_box.configure(state="disabled")
            self.entry = ctk.CTkEntry(self.main_content, placeholder_text="Zadaj pytanie systemowi OmniOS...", width=500)
            self.entry.pack(side="left", padx=(100, 10), pady=20)
            self.send_btn = ctk.CTkButton(self.main_content, text="Wyślij", width=80, command=self.send_command)
            self.send_btn.pack(side="left", pady=20)

        def send_command(self):
            cmd = self.entry.get()
            if not cmd: return
            self.chat_box.configure(state="normal")
            self.chat_box.insert("end", f"Ty: {cmd}\n")
            self.entry.delete(0, "end")
            self.chat_box.insert("end", "OmniOS: Przetwarzam Twoje polecenie w kontekście systemu COSMIC...\n")
            self.chat_box.configure(state="disabled")
            self.chat_box.see("end")

if __name__ == "__main__":
    simulate_boot()
    if GUI_AVAILABLE:
        try:
            app = OmniOSApp()
            app.mainloop()
        except Exception as e:
            console.print(f"[red]Failed to start GUI: {e}[/red]")
            run_tui()
    else:
        run_tui()
