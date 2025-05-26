import streamlit as st
import json
from bilkom_client import BilkomClient, StationMapper
import streamlit.components.v1 as components

st.set_page_config(page_title="BILKOM GRM Analyzer", layout="wide")

# Dodaj przełącznik trybu ciemnego/jasnego
st.markdown("""
    <style>
        .stApp {
            background-color: var(--background-color);
            color: var(--text-color);
        }
        .stButton>button {
            background-color: var(--button-color);
            color: var(--button-text-color);
        }
        .stTextInput>div>div>input {
            background-color: var(--input-color);
            color: var(--input-text-color);
        }
    </style>
""", unsafe_allow_html=True)

# Dodaj przełącznik w menu
st.sidebar.markdown("### Ustawienia")
theme = st.sidebar.radio("Tryb", ["Jasny", "Ciemny"])
if theme == "Ciemny":
    st.markdown("""
        <style>
            :root {
                --background-color: #1E1E1E;
                --text-color: #FFFFFF;
                --button-color: #2C2C2C;
                --button-text-color: #FFFFFF;
                --input-color: #2C2C2C;
                --input-text-color: #FFFFFF;
            }
        </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
        <style>
            :root {
                --background-color: #FFFFFF;
                --text-color: #000000;
                --button-color: #F0F2F6;
                --button-text-color: #000000;
                --input-color: #FFFFFF;
                --input-text-color: #000000;
            }
        </style>
    """, unsafe_allow_html=True)

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
# Dodaj przycisk Kopiuj obok pola
components.html(f'''
    <button onclick="navigator.clipboard.writeText(document.querySelector('input[data-testid=\'stTextInput\']').value)" style="margin-left:8px;padding:6px 16px;border-radius:6px;border:1px solid #1976D2;background:#1976D2;color:#fff;cursor:pointer;">Kopiuj</button>
''', height=40)

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
    # --- PODSUMOWANIE ZAPYTANIA ---
    if stops and len(stops) > 1:
        first_stop = stops[0]
        last_stop = stops[-1]
        st.session_state['summary'] = {
            'train_number': params['train_number'],
            'from_station': str(first_stop.get('stationNumber')),
            'to_station': str(last_stop.get('stationNumber')),
            'from_station_name': get_station_name(str(first_stop.get('stationNumber'))),
            'to_station_name': get_station_name(str(last_stop.get('stationNumber'))),
            'date': params['date'],
        }
    else:
        st.session_state['summary'] = {
            'train_number': params['train_number'],
            'from_station': params['from_station'],
            'to_station': params['to_station'],
            'from_station_name': get_station_name(params['from_station']),
            'to_station_name': get_station_name(params['to_station']),
            'date': params['date'],
        }
    # --- Wyświetlanie listy wagonów z checkboxami i opisem trasy ---
    schema_json = None
    try:
        schema_json = json.loads(resp1)
    except Exception:
        pass
    wagons_schema = []
    if schema_json and 'carriages' in schema_json:
        for carriage in schema_json['carriages']:
            wagon_num = str(carriage.get('carriageNumber'))
            travel_plan = carriage.get('travelPlan', {})
            from_epa = str(travel_plan.get('fromStationNumber')) if travel_plan else None
            to_epa = str(travel_plan.get('toStationNumber')) if travel_plan else None
            wagons_schema.append({
                'wagon': wagon_num,
                'from_epa': from_epa,
                'to_epa': to_epa
            })
    # --- Wyświetlanie unikalnych relacji wagonów pod podsumowaniem ---
    if wagons_schema:
        # Grupowanie wagonów po relacji (from_epa, to_epa)
        relacje = {}
        for w in wagons_schema:
            key = (w['from_epa'], w['to_epa'])
            if key not in relacje:
                relacje[key] = []
            relacje[key].append(w['wagon'])
        st.markdown("**Wagony/relacje:**")
        st.markdown("<table style='width:100%;border-collapse:collapse;'>", unsafe_allow_html=True)
        for (from_epa, to_epa), wagons in relacje.items():
            from_name = get_station_name(from_epa)
            to_name = get_station_name(to_epa)
            wagony_str = ", ".join(sorted(wagons, key=int))
            col1, col2 = st.columns([4,1])
            col1.markdown(f"<b>{from_name}</b> → <b>{to_name}</b> &nbsp;&nbsp; wagony: {wagony_str}", unsafe_allow_html=True)
            if col2.button(f"Przelicz", key=f"recalc_{from_epa}_{to_epa}"):
                # Podmień w linku fromStation i toStation na HAFAS odpowiadające EPA
                mapper = station_mapper
                from_hafas = mapper.epa_to_hafas.get(from_epa)
                to_hafas = mapper.epa_to_hafas.get(to_epa)
                st.write(f"EPA from: {from_epa}, to: {to_epa} | HAFAS from: {from_hafas}, to: {to_hafas}")
                if from_hafas and to_hafas:
                    import re
                    new_link = re.sub(r'(items%5b0%5d.fromStation=)[^&]*', f'\\1{from_hafas}', link)
                    new_link = re.sub(r'(items%5b0%5d.toStation=)[^&]*', f'\\1{to_hafas}', new_link)
                    st.write(f"Nowy link: {new_link}")
                    st.session_state['link'] = new_link
                    st.experimental_rerun()
        st.markdown("</table>", unsafe_allow_html=True)
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
    seats_sorted = sorted(all_seats, key=seat_sort_key)
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

if 'summary' in st.session_state and st.session_state['summary']:
    s = st.session_state['summary']
    st.markdown(f"""
    <div style='border:2px solid #1976D2; border-radius:8px; padding:12px; margin-bottom:18px; background:#f5f8ff;'>
    <b>Podsumowanie trasy:</b><br>
    <b>Numer pociągu:</b> <code>{s['train_number']}</code><br>
    <b>Stacja początkowa:</b> <code>{s['from_station_name']}</code> ({s['from_station']})<br>
    <b>Stacja końcowa:</b> <code>{s['to_station_name']}</code> ({s['to_station']})<br>
    <b>Data wyjazdu:</b> <code>{s['date']}</code>
    </div>
    """, unsafe_allow_html=True)

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
    .grm-table th, .grm-table td { border: 1px solid #bbb; padding: 7px 4px; text-align: center; }
    .grm-table th { background: #f5f5f5; font-size: 12px; font-weight: bold; }
    .grm-dot { width: 18px; height: 18px; border-radius: 50%; display: inline-block; margin: 0 2px; }
    .grm-seat { cursor: pointer; font-weight: bold; }
    .grm-seat.class1 { color: #F44336; }
    .grm-table tbody tr:nth-child(even) { background: #f9f9f9; }
    .grm-table tbody tr:nth-child(odd) { background: #fff; }
    .grm-table tr { border-bottom: 2px solid #e0e0e0; }
    .grm-table thead th.rotate { height: 110px; min-width: 36px; max-width: 60px; vertical-align: bottom; padding: 2px 2px; }
    .grm-table thead th.rotate > div { transform: rotate(-75deg); font-size: 11px; white-space: normal; overflow: hidden; text-overflow: ellipsis; max-width: 60px; margin: 0 auto; }
    </style>
    <table class='grm-table'>
      <thead>
        <tr>
          <th>Miejsce</th>"""
    for info in columns:
        arrival = info['arrival'][11:16] if info['arrival'] else ""
        departure = info['departure'][11:16] if info['departure'] else ""
        godziny = f"<div style='font-size:10px; font-weight:normal;'>{arrival} / {departure}</div>" if arrival or departure else ""
        # Dodaj tooltip z pełną nazwą stacji
        html += f"<th class='rotate'><div title='{info['name']}'>{info['name']}</div>{godziny}</th>"
    html += "</tr>\n      </thead>\n      <tbody>"
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