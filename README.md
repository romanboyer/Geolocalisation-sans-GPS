GeoLoRa est un système de suivi de position basse consommation qui n'utilise pas de GPS. Il repose sur le principe du WiFi Fingerprinting : l'objet scanne les réseaux WiFi environnants et envoie les adresses MAC les plus puissantes via un réseau LoRaWAN (The Things Network) à un serveur qui estime la position par trilatération pondérée.

Matériel

Carte de développement ESP32 avec connectivité LoRa (ex: TTGO LoRa32).
Couverture réseau LoRaWAN (Gateway à proximité).

Logiciel

Python 3.9+
Compte The Things Network (TTN)
Compte Ngrok (Gratuit)

Le projet est divisé en quatre couches principales :

Hardware (Edge) : Un ESP32 + Module LoRa scanne les réseaux WiFi (MAC + RSSI) et transmet les 2 meilleurs points d'accès.
Réseau : Transmission des paquets via le protocole LoRaWAN (The Things Network).

Backend (Python/FastAPI) : 
- Reçoit les webhooks de TTN
- Interroge une base de données locale (SQLite) contenant la cartographie des réseaux WiFi (données Wigle).
- Calcule la position (Algorithme WCL) et applique un lissage de trajectoire.

Frontend (Streamlit) : Dashboard de visualisation temps réel avec cartographie et logs système.


