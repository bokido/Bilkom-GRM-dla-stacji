import requests
from urllib.parse import urlparse, parse_qs
from typing import Dict, List, Tuple
import json
from datetime import datetime
import csv
import os

class BilkomClient:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://bilkom.pl"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def parse_url(self, url: str) -> Dict:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        return {
            'from_station': query_params.get('items[0].fromStation', [None])[0],
            'to_station': query_params.get('items[0].toStation', [None])[0],
            'date': query_params.get('items[0].date', [None])[0],
            'train_number': query_params.get('items[0].number', [None])[0]
        }

    def _format_date(self, date_str: str) -> str:
        """Konwertuje datę z formatu BILKOM na format ISO."""
        # Format wejściowy: DDMMYYYYHHMM
        day = date_str[0:2]
        month = date_str[2:4]
        year = date_str[4:8]
        hour = date_str[8:10]
        minute = date_str[10:12]
        
        return f"{year}-{month}-{day}T{hour}:{minute}:00"

    def get_train_stations(self, from_station: str, to_station: str, train_number: str, date: str) -> Tuple[List[str], list, str, str]:
        try:
            payload = {
                "stationFrom": int(from_station),
                "stationTo": int(to_station),
                "stationNumberingSystem": "HAFAS",
                "vehicleNumber": int(train_number),
                "departureDate": self._format_date(date),
                "arrivalDate": self._format_date(date),
                "type": "SCHEMA",
                "returnAllSectionsAvailableAtStationFrom": True,
                "returnBGMRecordsInfo": False
            }
            req_str = json.dumps(payload, ensure_ascii=False, indent=2)
            response = self.session.post(f"{self.base_url}/grm", json=payload, headers=self.headers)
            resp_str = response.text
            response.raise_for_status()
            data = response.json()
            # Pobieramy epaNumber ze stops[]
            stops = data.get('stops', [])
            stations = [str(stop.get('stationNumber')) for stop in stops if stop.get('stationNumber')]
            return stations, stops, req_str, resp_str
        except Exception as e:
            raise Exception(f"Błąd podczas pobierania listy stacji: {str(e)}")

    def get_seats_for_section(self, from_epa: str, to_epa: str, train_number: str, date: str) -> Tuple[dict, str, str]:
        try:
            payload = {
                "stationFrom": int(from_epa),
                "stationTo": int(to_epa),
                "stationNumberingSystem": "EPA",
                "vehicleNumber": int(train_number),
                "departureDate": self._format_date(date),
                "arrivalDate": self._format_date(date),
                "type": "SCHEMA",
                "returnAllSectionsAvailableAtStationFrom": True,
                "returnBGMRecordsInfo": False
            }
            req_str = json.dumps(payload, ensure_ascii=False, indent=2)
            response = self.session.post(f"{self.base_url}/grm", json=payload, headers=self.headers)
            resp_str = response.text
            response.raise_for_status()
            data = response.json()
            # Przetwarzanie miejsc
            seat_status = {}
            for carriage in data.get('carriages', []):
                wagon_number = carriage.get('carriageNumber')
                for seat in carriage.get('seats', []):
                    seat_number = seat.get('number')
                    status = seat.get('status')
                    seat_key = f"{wagon_number}-{seat_number}"
                    seat_status[seat_key] = status
            return seat_status, req_str, resp_str
        except Exception as e:
            raise Exception(f"Błąd podczas pobierania miejsc dla odcinka: {str(e)}")

    def get_grm_data(self, from_station: str, to_station: str, train_number: str, date: str) -> Tuple[Dict, str, str]:
        """Pobiera dane GRM dla danej pary stacji."""
        try:
            # Przygotowanie danych do zapytania
            payload = {
                "stationFrom": int(from_station),
                "stationTo": int(to_station),
                "stationNumberingSystem": "HAFAS",
                "vehicleNumber": int(train_number),
                "departureDate": self._format_date(date),
                "arrivalDate": self._format_date(date),
                "type": "CARRIAGE",
                "returnAllSectionsAvailableAtStationFrom": True,
                "returnBGMRecordsInfo": False
            }
            
            # Wykonanie zapytania
            req_str = json.dumps(payload, ensure_ascii=False, indent=2)
            response = self.session.post(
                f"{self.base_url}/grm",
                json=payload,
                headers=self.headers
            )
            resp_str = response.text
            response.raise_for_status()
            
            # Parsowanie odpowiedzi
            data = response.json()
            
            # Przetwarzanie danych GRM
            seat_status = {}
            for section in data.get('sections', []):
                for carriage in section.get('carriages', []):
                    wagon_number = carriage.get('number')
                    for seat in carriage.get('seats', []):
                        seat_number = seat.get('number')
                        status = seat.get('status')
                        
                        # Tworzenie klucza w formacie "wagon-miejsce"
                        seat_key = f"{wagon_number}-{seat_number}"
                        
                        # Mapowanie statusu
                        if status == 'available':
                            seat_status[seat_key] = 'free'
                        elif status == 'reserved':
                            seat_status[seat_key] = 'occupied'
                        elif status == 'blocked':
                            seat_status[seat_key] = 'blocked'
                        else:
                            seat_status[seat_key] = 'unknown'
            
            return seat_status, req_str, resp_str
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Błąd podczas pobierania danych GRM: {str(e)}")
        except json.JSONDecodeError as e:
            raise Exception(f"Błąd podczas parsowania odpowiedzi GRM: {str(e)}")
        except Exception as e:
            raise Exception(f"Nieoczekiwany błąd podczas pobierania danych GRM: {str(e)}")

    def get_carriages_for_section(self, from_epa: str, to_epa: str, train_number: str, date: str) -> Tuple[dict, str, str]:
        try:
            payload = {
                "stationFrom": int(from_epa),
                "stationTo": int(to_epa),
                "stationNumberingSystem": "EPA",
                "vehicleNumber": int(train_number),
                "departureDate": self._format_date(date),
                "arrivalDate": self._format_date(date),
                "type": "CARRIAGE",
                "returnAllSectionsAvailableAtStationFrom": True,
                "returnBGMRecordsInfo": False
            }
            req_str = json.dumps(payload, ensure_ascii=False, indent=2)
            response = self.session.post(f"{self.base_url}/grm", json=payload, headers=self.headers)
            resp_str = response.text
            response.raise_for_status()
            data = response.json()
            # Przetwarzanie miejsc
            seat_status = {}
            for carriage in data.get('carriages', []):
                wagon_number = carriage.get('carriageNumber')
                for spot in carriage.get('spots', []):
                    seat_number = spot.get('number')
                    status = spot.get('status')
                    seat_key = f"{wagon_number}-{seat_number}"
                    seat_status[seat_key] = status
            return seat_status, req_str, resp_str
        except Exception as e:
            raise Exception(f"Błąd podczas pobierania miejsc (CARRIAGE) dla odcinka: {str(e)}")

class StationMapper:
    def __init__(self, csv_path="sources/all_stations.csv"):
        self.epa_to_name = {}
        self.hafas_to_name = {}
        if not os.path.exists(csv_path):
            csv_path = os.path.join("__pycache__", csv_path)
        try:
            with open(csv_path, encoding="windows-1252", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row["NZ_16_ASCII"].strip()
                    hafas = row["HAFAS_ID"].strip()
                    epa = row["EPA_ID"].strip()
                    # EPA: jeśli krótszy niż 6 znaków, to 5100000+int(epa)
                    if epa:
                        if len(epa) < 6:
                            epa_num = str(5100000 + int(epa))
                        else:
                            epa_num = epa
                        self.epa_to_name[epa_num] = name
                    if hafas:
                        self.hafas_to_name[hafas] = name
            print("Mapowanie EPA na nazwy stacji:", self.epa_to_name)
        except Exception as e:
            print(f"Nie udało się wczytać bazy stacji: {e}") 