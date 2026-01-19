import csv
import sqlite3
import os

# --- CONFIGURATION ---
DATABASE_FILE = "wifi_scans.db"
WIGLE_CSV = "fusion_complete.csv" 

# Noms des colonnes de votre CSV
BSSID_COLUMN_NAME = 'netid'
LAT_COLUMN_NAME = 'trilat'
LON_COLUMN_NAME = 'trilong'
# --- La colonne SSID a été supprimée ---

def import_data():
    
    if not os.path.exists(WIGLE_CSV):
        print(f"Erreur : Fichier '{WIGLE_CSV}' introuvable.")
        return

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Création de la table SANS la colonne 'ssid'
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS known_aps (
            bssid TEXT PRIMARY KEY,
            lat REAL,
            lon REAL
        )
    """)
    
    imported_count = 0
    skipped_missing_data = 0
    skipped_invalid_gps = 0
    skipped_duplicate = 0
    
    print(f"Début de l'importation depuis '{WIGLE_CSV}'...")
    
    try:
        with open(WIGLE_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for i, row in enumerate(reader):
                bssid = row.get(BSSID_COLUMN_NAME)
                lat = row.get(LAT_COLUMN_NAME)
                lon = row.get(LON_COLUMN_NAME)
                # On ne lit plus le SSID
                
                if not (bssid and lat and lon):
                    skipped_missing_data += 1
                    continue

                try:
                    lat_float = float(lat)
                    lon_float = float(lon)
                    
                    # Requête d'insertion SANS 'ssid'
                    cursor.execute(
                        "INSERT OR IGNORE INTO known_aps (bssid, lat, lon) VALUES (?, ?, ?)",
                        (bssid, lat_float, lon_float) # Paramètres sans 'ssid'
                    )
                    
                    if cursor.rowcount > 0:
                        imported_count += 1
                    else:
                        skipped_duplicate += 1
                            
                except (ValueError, TypeError):
                    skipped_invalid_gps += 1

    except Exception as e:
        print(f"Une erreur est survenue lors de la lecture du CSV : {e}")
    finally:
        conn.commit()
        conn.close()
    
    print("\n--- Importation Terminée ---")
    print(f"✅ Points d'accès ajoutés à la base : {imported_count}")
    print(f"ℹ️ Lignes ignorées (données manquantes) : {skipped_missing_data}")
    print(f"ℹ️ Lignes ignorées (GPS invalide) : {skipped_invalid_gps}")
    print(f"ℹ️ Lignes ignorées (doublons) : {skipped_duplicate}")

if __name__ == "__main__":
    import_data()