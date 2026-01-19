import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional, List
from pyngrok import ngrok, conf
import sys
import os
import aiosqlite
from contextlib import asynccontextmanager
from datetime import datetime
import math

# --- CONFIGURATION ---
DATABASE_FILE = "../src/wifi_scans.db"  
LOG_BUFFER = [] 

# --- FONCTION DE LOGGING ---
def log_event(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    LOG_BUFFER.append(formatted_msg)
    if len(LOG_BUFFER) > 20:
        LOG_BUFFER.pop(0)

# --- MODÈLES DE DONNÉES (Pour 3 APs) ---
class DecodedPayload(BaseModel):
    AP1_MAC: str
    AP1_RSSI: int
    AP2_MAC: str
    AP2_RSSI: int
    # AP3 est Optional pour la robustesse
    AP3_MAC: Optional[str] = None
    AP3_RSSI: Optional[int] = None

class UplinkMessage(BaseModel):
    decoded_payload: Optional[DecodedPayload] = Field(None, alias="decoded_payload")
    f_port: int

class EndDeviceIDs(BaseModel):
    device_id: str
    dev_eui: str

class TTNWebhookData(BaseModel):
    end_device_ids: EndDeviceIDs
    received_at: str
    uplink_message: UplinkMessage

class PositionResponse(BaseModel):
    id: int
    timestamp: str
    device_id: str
    est_lat: float
    est_lon: float
    sources: int

# --- GESTION BASE DE DONNÉES ---
async def init_db():
    # On ne touche pas à 'known_aps' car on l'a déjà avec nos 5000 points.
    # On s'assure juste que la table d'historique 'scans' existe.
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                ap1_mac TEXT, ap1_rssi INTEGER,
                ap2_mac TEXT, ap2_rssi INTEGER,
                ap3_mac TEXT, ap3_rssi INTEGER,
                est_lat REAL, est_lon REAL, known_aps_count INTEGER
            )
        """)
        await db.commit()
    log_event("Serveur démarré. Connexion BDD OK.")

async def save_scan_to_db(data: TTNWebhookData, estimated_pos: Optional[dict]):
    payload = data.uplink_message.decoded_payload
    device_id = data.end_device_ids.device_id
    timestamp = data.received_at
    
    # --- LISSAGE DE POSITION (Moyenne Mobile Exponentielle) ---
    final_lat, final_lon, sources = None, None, 0
    
    if estimated_pos:
        new_lat = estimated_pos['lat']
        new_lon = estimated_pos['lon']
        sources = estimated_pos['sources']
        
        # Récupération de la dernière position valide pour ce device
        try:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                async with db.execute(
                    "SELECT est_lat, est_lon FROM scans WHERE device_id = ? AND est_lat IS NOT NULL ORDER BY id DESC LIMIT 1", 
                    (device_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        last_lat, last_lon = row
                        # Alpha: Facteur de lissage (0.4 = compromis réactivité/stabilité)
                        alpha = 0.4
                        final_lat = (alpha * new_lat) + ((1 - alpha) * last_lat)
                        final_lon = (alpha * new_lon) + ((1 - alpha) * last_lon)
                    else:
                        final_lat, final_lon = new_lat, new_lon
        except Exception:
            final_lat, final_lon = new_lat, new_lon

    # Insertion en base
    query = """
        INSERT INTO scans (device_id, timestamp, ap1_mac, ap1_rssi, ap2_mac, ap2_rssi, ap3_mac, ap3_rssi, est_lat, est_lon, known_aps_count) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        device_id, timestamp, 
        payload.AP1_MAC, payload.AP1_RSSI, 
        payload.AP2_MAC, payload.AP2_RSSI, 
        payload.AP3_MAC, payload.AP3_RSSI,
        final_lat, final_lon, sources
    )
    
    try:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(query, params)
            await db.commit()
    except Exception as e:
        log_event(f"ERREUR SQL: {e}")

# --- ALGORITHME DE TRILATÉRATION ---
async def get_estimated_position(payload: DecodedPayload) -> Optional[dict]:
    # --- LOG DEBUG 1: CE QU'ON A REÇU ---
    log_event("------------------------------------------------")
    log_event(f"🔍 DEBUG START: Analyse du payload...")
    log_event(f"   AP1: {payload.AP1_MAC} ({payload.AP1_RSSI} dBm)")
    log_event(f"   AP2: {payload.AP2_MAC} ({payload.AP2_RSSI} dBm)")
    if payload.AP3_MAC:
        log_event(f"   AP3: {payload.AP3_MAC} ({payload.AP3_RSSI} dBm)")
    else:
        log_event(f"   AP3: Non reçu")

    # Liste des APs reçus
    potential_aps = [
        {"mac": payload.AP1_MAC, "rssi": payload.AP1_RSSI},
        {"mac": payload.AP2_MAC, "rssi": payload.AP2_RSSI}
    ]
    if payload.AP3_MAC:
        potential_aps.append({"mac": payload.AP3_MAC, "rssi": payload.AP3_RSSI})
    
    weighted_lat_sum = 0
    weighted_lon_sum = 0
    total_weight = 0
    known_aps_found = 0

    A_ref = -50.0 
    n_index = 3.0   

    try:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            # --- LOG DEBUG 2: VÉRIF RAPIDE DE LA BDD ---
            async with db.execute("SELECT count(*) FROM known_aps") as cursor:
                count = await cursor.fetchone()
                log_event(f"🔍 DEBUG BDD: La table 'known_aps' contient {count[0]} lignes.")
            
            for i, ap in enumerate(potential_aps):
                mac_brute = ap["mac"]
                # Nettoyage et mise en majuscule pour maximiser les chances
                mac_clean = mac_brute.strip().upper()
                
                log_event(f"   > Test AP #{i+1}: '{mac_clean}' (Brut: '{mac_brute}')")

                # Requête SQL pour chercher l'AP
                query = "SELECT lat, lon FROM known_aps WHERE UPPER(bssid) = ?"
                
                async with db.execute(query, (mac_clean,)) as cursor:
                    row = await cursor.fetchone()
                    
                    if row:
                        known_aps_found += 1
                        lat, lon = row
                        rssi = ap["rssi"]
                        
                        # Calculs
                        val_rssi = max(min(rssi, -10), -100)
                        exponent = (A_ref - val_rssi) / (10 * n_index)
                        distance = 10 ** exponent
                        # si distance < 1m, on met 1m pour éviter des poids infinis
                        distance = max(distance, 1.0) 
                        weight = 1.0 / (distance ** 2)

                        total_weight += weight
                        weighted_lat_sum += lat * weight
                        weighted_lon_sum += lon * weight
                        
                        log_event(f"     TROUVÉ en BDD ! Coords: ({lat:.4f}, {lon:.4f})")
                        log_event(f"     Distance Est.: {distance:.2f}m | Poids: {weight:.4f}")
                    else:
                        log_event(f"     NON TROUVÉ. Cette MAC n'est pas dans votre BDD.")
                        # On regarde si ça ressemble à quelque chose
                        async with db.execute("SELECT bssid FROM known_aps LIMIT 1") as sample_cursor:
                            sample = await sample_cursor.fetchone()
                            if sample:
                                log_event(f"     Info: Exemple de format dans BDD: '{sample[0]}'")

    except Exception as e:
        log_event(f"ERREUR CRITIQUE DANS LA BOUCLE: {e}")
        return None

    log_event(f"DEBUG SUMMARY: {known_aps_found} APs trouvés sur {len(potential_aps)} scannés.")

    if total_weight > 0:
        final_lat = weighted_lat_sum / total_weight
        final_lon = weighted_lon_sum / total_weight
        log_event(f"RÉSULTAT: ({final_lat}, {final_lon})")
        return {
            "lat": final_lat, 
            "lon": final_lon, 
            "sources": known_aps_found
        }
    
    log_event("RÉSULTAT: Échec du calcul (Poids total = 0)")
    return None

    # On renvoie une position si on a trouvé au moins 1 AP connu (idéalement 3)
    # Avec 1 seul AP, on renvoie sa position exacte (fallback)
    if total_weight > 0:
        return {
            "lat": weighted_lat_sum / total_weight, 
            "lon": weighted_lon_sum / total_weight, 
            "sources": known_aps_found
        }
    return None

# --- API ENDPOINTS ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/ttn/uplink")
async def receive_ttn_data(data: TTNWebhookData):
    if not data.uplink_message.decoded_payload:
        return {"status": "empty payload"}
    
    log_event(f"Paquet reçu de {data.end_device_ids.device_id}")

    # 1. Calcul de la position
    est_pos = await get_estimated_position(data.uplink_message.decoded_payload)
    
    if est_pos:
        log_event(f"POS: {est_pos['lat']:.5f}, {est_pos['lon']:.5f} (basé sur {est_pos['sources']} APs)")
    else:
        log_event("POS: Impossible (APs inconnus dans la BDD)")

    # 2. Sauvegarde
    await save_scan_to_db(data, est_pos)
    
    return {"status": "ok"}

@app.get("/api/latest-position", response_model=Optional[PositionResponse])
async def get_latest_position():
    query = """
        SELECT id, timestamp, device_id, est_lat, est_lon, known_aps_count 
        FROM scans 
        WHERE est_lat IS NOT NULL 
        ORDER BY id DESC LIMIT 1
    """
    async with aiosqlite.connect(DATABASE_FILE) as db:
        async with db.execute(query) as cursor:
            row = await cursor.fetchone()
            if row: 
                return PositionResponse(
                    id=row[0], timestamp=row[1], device_id=row[2], 
                    est_lat=row[3], est_lon=row[4], sources=row[5]
                )
    return None

@app.get("/api/logs")
async def get_logs():
    return {"logs": LOG_BUFFER}

@app.get("/api/trajectory")
async def get_trajectory():
    """ Renvoie les 100 dernières positions pour tracer le chemin """
    query = """
        SELECT est_lat, est_lon 
        FROM scans 
        WHERE est_lat IS NOT NULL 
        ORDER BY id DESC LIMIT 100
    """
    async with aiosqlite.connect(DATABASE_FILE) as db:
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            # On renvoie une liste de listes : [[lat, lon], [lat, lon], ...]
            # On inverse pour avoir l'ordre chronologique (du plus vieux au plus récent)
            return [ [row[0], row[1]] for row in rows ][::-1]

if __name__ == "__main__":
    # NGROK AUTH TOKEN
    ngrok.set_auth_token("35bFUn8xTjEGtgZFejY8goFPtsF_6aLBFL8FvCm4rrYXzeyT3") 
    
    # Configuration Ngrok
    conf.get_default().ngrok_path = os.path.join(os.path.dirname(__file__), "ngrok")
    public_url = ngrok.connect(8000).public_url
    print(f"--- URL PUBLIQUE TTN : {public_url}/ttn/uplink ---")
    
    uvicorn.run(app, host="127.0.0.1", port=8000)