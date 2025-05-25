import customtkinter as ctk
import tkinter as tk
from typing import Dict, List

class ResultsViewer(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.selected_wagons = set()
        self.all_wagons = set()
        self.seat_properties = {}  # seat_key -> properties
        self._last_table = None
        self._last_columns = None
        self._last_seat_properties = None
        # Konfiguracja siatki
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        # Chipsy do filtrowania wagonów
        self.chips_frame = ctk.CTkFrame(self)
        self.chips_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        # Tworzenie canvas z paskiem przewijania (zwiększona wysokość)
        self.canvas = tk.Canvas(self, bg=self._apply_appearance_mode(self._fg_color), height=800)  # było domyślnie, teraz 800
        self.scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self.canvas.yview)
        self.scrollable_frame = ctk.CTkFrame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.scrollbar.grid(row=1, column=1, sticky="ns")

    def display_results(self, table: dict, columns: list, seat_properties: dict = None):
        self._last_table = table
        self._last_columns = columns
        self._last_seat_properties = seat_properties
        self.seat_properties = seat_properties or {}
        # Zbierz wszystkie wagony
        self.all_wagons = set()
        for seat in table.keys():
            wagon, _ = seat.split('-')
            self.all_wagons.add(wagon)
        if not self.selected_wagons:
            self.selected_wagons = set(self.all_wagons)
        # Chipsy
        for widget in self.chips_frame.winfo_children():
            widget.destroy()
        for wagon in sorted(self.all_wagons, key=int):
            chip = ctk.CTkButton(
                self.chips_frame,
                text=f"Wagon {wagon}",
                fg_color="#1976D2" if wagon in self.selected_wagons else "#B0BEC5",
                text_color="#fff" if wagon in self.selected_wagons else "#263238",
                command=lambda w=wagon: self.toggle_wagon_and_refresh(w),
                width=80,
                height=28,
                corner_radius=12
            )
            chip.pack(side=tk.LEFT, padx=4, pady=2)
        # Czyszczenie poprzednich wyników
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        if not table or not columns:
            return
        # Nagłówki kolumn: tylko pierwszy numer stacji z pary
        for i, col in enumerate(columns):
            first_station = col.split('-')[0]
            label = ctk.CTkLabel(
                self.scrollable_frame,
                text=first_station,
                font=("Arial", 12, "bold")
            )
            label.grid(row=0, column=i+1, padx=5, pady=5)
        # Wiersze: sortuj po wagonie i miejscu (oba int)
        def seat_sort_key(seat):
            wagon, number = seat.split('-')
            return (int(wagon), int(number))
        sorted_seats = [seat for seat in sorted(table.keys(), key=seat_sort_key) if seat.split('-')[0] in self.selected_wagons]
        for row_idx, seat in enumerate(sorted_seats, 1):
            wagon, number = seat.split('-')
            props = self.seat_properties.get(seat, [])
            is_class1 = "CLASS_1" in props
            seat_label = ctk.CTkLabel(
                self.scrollable_frame,
                text=seat,
                font=("Arial", 12, "bold" if is_class1 else "normal"),
                text_color="#F44336" if is_class1 else "#fff",
                cursor="hand2"
            )
            seat_label.grid(row=row_idx, column=0, padx=5, pady=2)
            seat_label.bind("<Button-1>", lambda e, s=seat: self.show_properties(s))
            for col_idx, col in enumerate(columns):
                status = table[seat].get(col, "unknown")
                color = self._get_status_color(status)
                status_label = ctk.CTkLabel(
                    self.scrollable_frame,
                    text="",
                    fg_color=color,
                    corner_radius=5,
                    width=40,
                    height=25
                )
                status_label.grid(row=row_idx, column=col_idx+1, padx=2, pady=2)
    def toggle_wagon_and_refresh(self, wagon):
        if wagon in self.selected_wagons:
            self.selected_wagons.remove(wagon)
        else:
            self.selected_wagons.add(wagon)
        # Odśwież widok natychmiast
        self.display_results(self._last_table, self._last_columns, self._last_seat_properties)
    def _get_status_color(self, status: str) -> str:
        colors = {
            "AVAILABLE": "#4CAF50",  # Zielony
            "RESERVED": "#F44336",  # Czerwony
            "BLOCKED": "#9E9E9E",   # Szary
            "unknown": "#E0E0E0"     # Jasnoszary
        }
        return colors.get(status.upper(), colors["unknown"])
    def show_properties(self, seat):
        props = self.seat_properties.get(seat, [])
        msg = f"Właściwości miejsca {seat}:\n\n" + "\n".join(props) if props else "Brak dodatkowych właściwości."
        tk.messagebox.showinfo("Properties", msg) 