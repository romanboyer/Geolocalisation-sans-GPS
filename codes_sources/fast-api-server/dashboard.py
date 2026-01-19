import streamlit as st
import requests
import pandas as pd
import time
import pydeck as pdk

# --- CONFIGURATION ---
BASE_URL = "http://127.0.0.1:8000"
API_URL_POS = f"{BASE_URL}/api/latest-position"
API_URL_LOGS = f"{BASE_URL}/api/logs"
API_URL_TRAJ = f"{BASE_URL}/api/trajectory" # On ajoute l'endpoint du tracé

# Configuration de la page
st.set_page_config(page_title="GeoLoRa Monitor", layout="wide")

# --- CSS MINIMALISTE ---
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    .log-line {
        font-family: monospace;
        font-size: 12px;
        color: #cccccc;
        border-bottom: 1px solid #333;
        padding: 2px 0;
    }
    </style>
""", unsafe_allow_html=True)

st.header("GeoLoRa - Monitoring Temps Réel")

# --- FONCTIONS FETCH ---
def fetch_data(url):
    try:
        r = requests.get(url, timeout=1)
        return r.json() if r.status_code == 200 else None
    except:
        return None

# --- PLACEHOLDERS ---
info_placeholder = st.empty()
map_placeholder = st.empty()
log_placeholder = st.empty()

# --- BOUCLE PRINCIPALE ---
while True:
    # 1. Récupération des données depuis le serveur
    pos_data = fetch_data(API_URL_POS)
    logs_data = fetch_data(API_URL_LOGS)
    traj_data = fetch_data(API_URL_TRAJ) # On récupère la liste [[lat, lon], ...] du serveur

    # 2. Gestion des données de position actuelle
    lat = pos_data.get('est_lat', 0) if pos_data else 0
    lon = pos_data.get('est_lon', 0) if pos_data else 0
    
    # 3. Affichage des Infos
    with info_placeholder.container():
        if lat != 0:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Latitude", f"{lat:.6f}")
            c2.metric("Longitude", f"{lon:.6f}")
            c3.metric("Sources WiFi", pos_data.get('sources', 0))
            c4.text(f"Dernier signal:\n{pos_data.get('timestamp', 'N/A')}")
        else:
            st.warning("Système en attente de signal LoRaWAN...")

    # 4. Configuration de la Carte
    view_lat = lat if lat != 0 else 48.8453
    view_lon = lon if lon != 0 else 2.3574
    
    view_state = pdk.ViewState(
        latitude=view_lat,
        longitude=view_lon,
        zoom=17,
        pitch=0,
        bearing=0
    )

    layers = []
    
    # --- COUCHE 1 : TRAJET (Ligne Jaune) ---
    # On vérifie si le serveur nous a renvoyé un historique
    if traj_data and len(traj_data) > 1:
        # PyDeck attend [Longitude, Latitude], mais le serveur envoie [Lat, Lon]
        # On doit inverser les coordonnées : p[1]=Lon, p[0]=Lat
        formatted_path = [ [p[1], p[0]] for p in traj_data ]
        
        layers.append(pdk.Layer(
            "PathLayer",
            data=[{"path": formatted_path}],
            get_path="path",
            get_color=[255, 255, 0], # Jaune
            width_min_pixels=3,
            opacity=0.8
        ))

    # --- COUCHE 2 : POSITION ACTUELLE (Point Rouge) ---
    if lat != 0:
        # Pour le Scatterplot, on crée un petit DataFrame 
        current_pt = pd.DataFrame([{"lon": lon, "lat": lat}])
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=current_pt,
            get_position="[lon, lat]",
            get_fill_color=[255, 0, 0], # Rouge
            get_radius=6,
            pickable=True,
            opacity=0.9
        ))

    # Rendu de la carte
    r = pdk.Deck(
        map_style="dark",
        initial_view_state=view_state,
        layers=layers,
        tooltip={"text": "Position"}
    )
    
    map_placeholder.pydeck_chart(r)

    # 5. Affichage des Logs
    with log_placeholder.container():
        with st.expander("VOIR LES LOGS SYSTÈME (DEBUG)", expanded=False):
            if logs_data and "logs" in logs_data:
                log_text = ""
                # On affiche les logs dans l'ordre inverse (plus récent en haut)
                for line in reversed(logs_data["logs"]):
                    log_text += f'<div class="log-line">{line}</div>'
                st.markdown(log_text, unsafe_allow_html=True)
            else:
                st.text("Aucun log disponible.")

    time.sleep(1)