#include <WiFi.h>
#include <string.h> // Nécessaire pour strcpy

// Variables globales pour stocker l'emplacement
char bâtiment[20];
char salle[10];

void setup() {
  // Initialisation de la communication série à 115200 bauds
  Serial.begin(115200);

  // Copie des chaînes de caractères dans les variables (style C)
  strcpy(bâtiment, "Escanglon");
  strcpy(salle, "324");

  // Configuration de l'ESP32 en mode station pour le scan
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  // Affiche l'en-tête du CSV une seule fois au démarrage
  printf("Bâtiment,Salle,BSSID,RSSI,SSID\n");
}

void loop() {
  // Lance le scan et récupère le nombre de réseaux
  int nombreReseaux = WiFi.scanNetworks();

  if (nombreReseaux > 0) {
    // Boucle pour afficher les détails de chaque réseau au format CSV
    for (int i = 0; i < nombreReseaux; i++) {
      // Format: Bâtiment,Salle,Adresse MAC,Puissance Signal,Nom du réseau
      printf("%s,%s,%s,%d,%s\n",
             bâtiment,
             salle,
             WiFi.BSSIDstr(i).c_str(),  // Adresse MAC (BSSID)
             WiFi.RSSI(i),              // Puissance du signal
             WiFi.SSID(i).c_str()       // Nom du réseau (SSID)
            );
    }
  }
  
  // Pause de 10 secondes entre les scans pour ne pas avoir trop de données redondantes
  delay(10000);
}