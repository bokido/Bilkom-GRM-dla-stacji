import streamlit as st
import json
from bilkom_client import BilkomClient, StationMapper

st.set_page_config(page_title="BILKOM GRM Analyzer", layout="wide")
st.title("BILKOM GRM Analyzer (wersja web)")

station_mapper = StationMapper()

def get_station_name(epa_num):
    return station_mapper.epa_to_name.get(epa_num, epa_num)

def get_link():
    try:
        with open("web_link.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

link = st.text_input("Wklej link z BILKOM:", value=get_link(), key="link")

if 'results' not in st.session_state:
    st.session_state['results'] = None
    st.session_state['seats_sorted'] = None
    st.session_state['seat_properties'] = None
    st.session_state['columns'] = None
    st.session_state['all_wagons'] = None
    st.session_state['show_props'] = None
    st.session_state['station_info'] = None

if st.button("Analizuj miejsca"):
    bilkom = BilkomClient()
    params = bilkom.parse_url(link)
    if not all([params['from_station'], params['to_station'], params['date'], params['train_number']]):
        st.error(f"Brak wymaganych parametrów w linku: {params}")
        st.stop()
    stations, stops, req1, resp1 = bilkom.get_train_stations(
        params['from_station'],
        params['to_station'],
        params['train_number'],
        params['date']
    )
    if len(stations) < 2:
        st.error("Za mało stacji na trasie!")
        st.stop()
    # Mapa EPA -> info o stacji
    station_info = {}
    for stop in stops:
        epa = str(stop.get('stationNumber'))
        station_info[epa] = {
            'name': get_station_name(epa),
            'code': epa,
            'arrival': stop.get('plannedArrivalTime', ''),
            'departure': stop.get('plannedDepartureTime', '')
        }
    results = {}
    all_seats = set()
    seat_properties = {}
    progress_bar = st.progress(0)
    for i in range(len(stations) - 1):
        from_epa = stations[i]
        to_epa = stations[i + 1]
        seat_status, req2, resp2 = bilkom.get_carriages_for_section(
            from_epa,
            to_epa,
            params['train_number'],
            params['date']
        )
        col_name = f"{from_epa}-{to_epa}"
        results[col_name] = seat_status
        all_seats.update(seat_status.keys())
        # seat_properties zbieramy tylko z pierwszego odcinka
        if i == 0:
            try:
                carriages_json = json.loads(resp2)
                for carriage in carriages_json.get('carriages', []):
                    wagon = carriage.get('carriageNumber')
                    for spot in carriage.get('spots', []):
                        seat_key = f"{wagon}-{spot.get('number')}"
                        seat_properties[seat_key] = spot.get('properties', [])
            except Exception as e:
                st.warning(f"Błąd dekodowania JSON: {e}")
        progress_bar.progress((i + 1) / (len(stations) - 1))
    progress_bar.empty()
    def seat_sort_key(seat):
        wagon, number = seat.split('-')
        return (int(wagon), int(number))
    seats_sorted = sorted([seat for seat in all_seats if seat.split('-')[0] in selected_wagons], key=seat_sort_key)
    all_wagons = sorted({seat.split('-')[0] for seat in seats_sorted}, key=int)
    pretty_columns = []
    for col in results.keys():
        epa = col.split('-')[0]
        info = station_info.get(epa, {'name':epa, 'code':epa, 'arrival':'', 'departure':''})
        pretty_columns.append(info)
    st.session_state['results'] = results
    st.session_state['seats_sorted'] = seats_sorted
    st.session_state['seat_properties'] = seat_properties
    st.session_state['columns'] = pretty_columns
    st.session_state['all_wagons'] = all_wagons
    st.session_state['show_props'] = None
    st.session_state['station_info'] = station_info

if st.session_state['results']:
    results = st.session_state['results']
    seats_sorted = st.session_state['seats_sorted']
    seat_properties = st.session_state['seat_properties']
    columns = st.session_state['columns']
    all_wagons = st.session_state['all_wagons']
    station_info = st.session_state['station_info']
    default_wagons = all_wagons[:1] if all_wagons else []
    selected_wagons = st.multiselect("Pokaż wagony:", all_wagons, default=default_wagons, key="wagony")
    seats_sorted = [seat for seat in seats_sorted if seat.split('-')[0] in selected_wagons]

    # Generowanie tabeli HTML
    html = """
    <style>
    .grm-table { border-collapse: collapse; width: 100%; }
    .grm-table th, .grm-table td { border: 1px solid #ddd; padding: 4px; text-align: center; }
    .grm-table th { background: #f5f5f5; font-size: 13px; font-weight: bold; }
    .grm-dot { width: 18px; height: 18px; border-radius: 50%; display: inline-block; margin: 0 2px; }
    .grm-seat { cursor: pointer; font-weight: bold; }
    .grm-seat.class1 { color: #F44336; }
    .grm-table thead th.rotate { height: 90px; white-space: nowrap; }
    .grm-table thead th.rotate > div { transform: rotate(-90deg); width: 20px; }
    </style>
    <table class='grm-table'>
      <thead>
        <tr>
          <th>Miejsce</th>
"""
    for info in columns:
        arrival = info['arrival'][11:16] if info['arrival'] else ""
        departure = info['departure'][11:16] if info['departure'] else ""
        godziny = f"<div style='font-size:11px; font-weight:normal;'>{arrival} / {departure}</div>" if arrival or departure else ""
        html += f"<th class='rotate'><div>{info['name']}</div>{godziny}</th>"
    html += "</tr></thead><tbody>"
    for seat in seats_sorted:
        props = seat_properties.get(seat, [])
        is_class1 = "CLASS_1" in props
        seat_class = "grm-seat class1" if is_class1 else "grm-seat"
        html += f"<tr><td class='{seat_class}' onclick=\"window.location.hash='seat_{seat}'\">{seat}</td>"
        for col_idx, info in enumerate(columns):
            epa_num = info['code']
            col_key = None
            for k in results.keys():
                if k.startswith(epa_num+"-"):
                    col_key = k
                    break
            status = results[col_key].get(seat, "unknown") if col_key else "unknown"
            color = {"AVAILABLE": "#4CAF50", "RESERVED": "#F44336", "BLOCKED": "#9E9E9E", "unknown": "#E0E0E0"}.get(status.upper(), "#E0E0E0")
            html += f"<td><span class='grm-dot' style='background:{color}'></span></td>"
        html += "</tr>"
    html += "</tbody></table>"
    st.markdown(html, unsafe_allow_html=True)

    # Wyświetlanie właściwości miejsca po kliknięciu (hash w URL)
    import streamlit.components.v1 as components
    components.html("""
    <script>
    window.addEventListener('hashchange', function() {
      const hash = window.location.hash;
      if(hash.startsWith('#seat_')) {
        const seat = hash.replace('#seat_', '');
        window.parent.postMessage({seat: seat}, '*');
      }
    });
    </script>
    """, height=0)
    import streamlit as st2
    if 'show_props' not in st.session_state:
        st.session_state['show_props'] = None
    import streamlit_javascript as st_js
    seat_clicked = st_js.st_javascript("""
    function getSeatFromHash() {
      if(window.location.hash.startsWith('#seat_')) {
        return window.location.hash.replace('#seat_', '');
      }
      return '';
    }
    getSeatFromHash();
    """)
    if seat_clicked and seat_clicked in seat_properties:
        props = seat_properties.get(seat_clicked, [])
        st.info(f"Właściwości miejsca {seat_clicked}:\n\n" + "\n".join([f"- {p}" for p in props]) if props else "Brak dodatkowych właściwości.") 