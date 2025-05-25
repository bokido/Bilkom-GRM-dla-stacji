import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from bilkom_client import BilkomClient, StationMapper
from results_viewer import ResultsViewer
import traceback
import logging
import json
import subprocess
import webbrowser

# Konfiguracja logowania do pliku
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

class BilkomAnalyzer(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Konfiguracja głównego okna
        self.title("BILKOM GRM Analyzer")
        self.geometry("1200x900")

        # Konfiguracja motywu
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Inicjalizacja klienta BILKOM
        self.bilkom_client = BilkomClient()
        self.station_mapper = StationMapper()

        # Tworzenie głównego kontenera
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Etykieta i pole wprowadzania
        self.url_label = ctk.CTkLabel(
            self.main_frame, 
            text="Wklej link z BILKOM:",
            font=("Roboto", 14)
        )
        self.url_label.pack(pady=(0, 10))

        self.url_entry = ctk.CTkEntry(
            self.main_frame,
            width=800,
            height=40,
            font=("Roboto", 12)
        )
        self.url_entry.pack(pady=(0, 20))

        # Przycisk analizy
        self.analyze_button = ctk.CTkButton(
            self.main_frame,
            text="Analizuj miejsca",
            command=self.analyze_url,
            font=("Roboto", 12),
            height=40
        )
        self.analyze_button.pack(pady=(0, 20))

        # Przycisk uruchomienia w przeglądarce
        self.web_button = ctk.CTkButton(
            self.main_frame,
            text="Uruchom w przeglądarce",
            command=self.run_in_browser,
            font=("Roboto", 12),
            height=40
        )
        self.web_button.pack(pady=(0, 20))

        # Obszar wyników
        self.results_viewer = ResultsViewer(self.main_frame)
        self.results_viewer.pack(fill="both", expand=True)

        # Panel do logowania zapytań i odpowiedzi
        self.api_log_label = ctk.CTkLabel(self.main_frame, text="Log zapytań i odpowiedzi API:", font=("Roboto", 12, "bold"))
        self.api_log_label.pack(pady=(10, 0))
        self.api_log_text = ctk.CTkTextbox(self.main_frame, width=1100, height=200, font=("Roboto", 10))
        self.api_log_text.pack(pady=(0, 10))
        self.api_log_text.configure(state="disabled")

    def log_api(self, title, request_data, response_data=None):
        self.api_log_text.configure(state="normal")
        if title.startswith("CARRIAGE"):
            self.api_log_text.insert(tk.END, f"\n--- {title} ---\n")
            self.api_log_text.insert(tk.END, f"Zapytanie:\n{request_data}\n")
        else:
            self.api_log_text.insert(tk.END, f"\n--- {title} ---\n")
            self.api_log_text.insert(tk.END, f"Zapytanie:\n{request_data}\n")
            if response_data:
                self.api_log_text.insert(tk.END, f"Odpowiedź:\n{response_data}\n")
        self.api_log_text.see(tk.END)
        self.api_log_text.configure(state="disabled")

    def analyze_url(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Błąd", "Proszę wprowadzić link z BILKOM")
            return

        try:
            params = self.bilkom_client.parse_url(url)
            if not all([params['from_station'], params['to_station'], params['date'], params['train_number']]):
                raise ValueError(f"Brak wymaganych parametrów w linku: {params}")

            # Pobierz listę stacji (epaNumber)
            stations, req1, resp1 = self.bilkom_client.get_train_stations(
                params['from_station'],
                params['to_station'],
                params['train_number'],
                params['date']
            )
            self.log_api("SCHEMA (stacje)", req1, resp1)

            if len(stations) < 2:
                raise ValueError("Za mało stacji na trasie!")

            # Dla każdej pary kolejnych stacji pobierz status miejsc
            results = {}  # {kolumna: {wagon-miejsce: status}}
            all_seats = set()
            seat_properties = {}  # seat_key -> properties
            for i in range(len(stations) - 1):
                from_epa = stations[i]
                to_epa = stations[i + 1]
                seat_status, req2, resp2 = self.bilkom_client.get_carriages_for_section(
                    from_epa,
                    to_epa,
                    params['train_number'],
                    params['date']
                )
                col_name = f"{from_epa}-{to_epa}"
                results[col_name] = seat_status
                all_seats.update(seat_status.keys())
                # Zbieraj properties dla miejsc
                try:
                    carriages_json = json.loads(resp2)
                    for carriage in carriages_json.get('carriages', []):
                        wagon = carriage.get('carriageNumber')
                        for spot in carriage.get('spots', []):
                            seat_key = f"{wagon}-{spot.get('number')}"
                            seat_properties[seat_key] = spot.get('properties', [])
                except Exception as e:
                    logging.error(f"Błąd dekodowania JSON z odpowiedzi CARRIAGE: {e}")
                self.log_api(f"CARRIAGE {col_name}", req2)

            # Budujemy tabelę: wiersze = wagon-miejsce, kolumny = kolejne odcinki
            def seat_sort_key(seat):
                wagon, number = seat.split('-')
                return (int(wagon), int(number))
            seats_sorted = sorted(all_seats, key=seat_sort_key)
            table = {seat: {} for seat in seats_sorted}
            for col in results:
                for seat in seats_sorted:
                    table[seat][col] = results[col].get(seat, "unknown")

            # Log do pliku
            logging.info(f"Tabela: miejsc={len(seats_sorted)}, kolumn={len(results)}")
            # Wyświetl tabelę
            def get_station_name(epa_num):
                return self.station_mapper.epa_to_name.get(epa_num, epa_num)
            pretty_columns = [f"{get_station_name(col.split('-')[0])} ({col.split('-')[0]})" for col in results.keys()]
            self.results_viewer.display_results(table, pretty_columns, seat_properties)
            # Obsługa chipsów (odświeżanie po kliknięciu)
            self.results_viewer.bind("<<RefreshResults>>", lambda e: self.results_viewer.display_results(table, pretty_columns, seat_properties))
        except Exception as e:
            error_msg = f"Wystąpił błąd: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            messagebox.showerror("Błąd", error_msg)

    def run_in_browser(self):
        url = self.url_entry.get().strip()
        # Zapisz link do pliku tymczasowego
        with open("web_link.txt", "w", encoding="utf-8") as f:
            f.write(url)
        # Uruchom streamlit w tle
        subprocess.Popen(["streamlit", "run", "web_app.py"])
        # Otwórz przeglądarkę
        webbrowser.open_new_tab("http://localhost:8501")

if __name__ == "__main__":
    app = BilkomAnalyzer()
    app.mainloop() 