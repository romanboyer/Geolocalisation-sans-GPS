#include <WiFi.h>
#include <HardwareSerial.h>

// --- Configuration TTN ---
const char* devEui = "70B3D57ED0073214";
const char* appEui = "0000000000000000";
const char* appKey = "17A7F515799E841AE2567D0866FACC96"; 

// --- Configuration LoRa-E5 ---
#define LORA_TX 17
#define LORA_RX 16
HardwareSerial LoRaSerial(2);

// --- Intervalle d'envoi ---
const unsigned long LORAWAN_TX_INTERVAL = 15000; // 15 secondes
bool isJoined = false;

// Fonction de connexion 
bool joinNetwork() {
    Serial.println("Tentative de connexion au réseau...");
    LoRaSerial.println("AT+JOIN");
    unsigned long joinStartTime = millis();
    String response = "";
    while (millis() - joinStartTime < 30000) { 
        if (LoRaSerial.available()) {
            char c = LoRaSerial.read();
            Serial.write(c);
            response += c;
            if (response.indexOf("Joined") > -1 || response.indexOf("joined") > -1) {
                Serial.println("\nConnexion au réseau réussie !");
                return true;
            }
        }
    }
    Serial.println("\nÉchec de la connexion.");
    return false;
}

// Fonction d'envoi 
bool sendData(const String& hexPayload) {
    Serial.println("Envoi LoRaWAN : AT+MSGHEX=" + hexPayload);
    LoRaSerial.println("AT+MSGHEX=" + hexPayload);
    String response = "";
    unsigned long startTime = millis();
    while (millis() - startTime < 10000) { 
        if (LoRaSerial.available()) {
            char c = LoRaSerial.read();
            Serial.write(c);
            response += c;
        }
    }
    Serial.println();
    if (response.indexOf("Please join network first") > -1) return false;
    return true;
}

void setup() {
    Serial.begin(115200);
    LoRaSerial.begin(9600, SERIAL_8N1, LORA_RX, LORA_TX);
    
    // Config LoRa
    LoRaSerial.println("AT"); delay(200);
    LoRaSerial.println("AT+ID=DevEui,\"" + String(devEui) + "\""); delay(200);
    LoRaSerial.println("AT+ID=AppEui,\"" + String(appEui) + "\""); delay(200);
    LoRaSerial.println("AT+KEY=APPKEY,\"" + String(appKey) + "\""); delay(200);
    LoRaSerial.println("AT+MODE=LWOTAA"); delay(200);
    LoRaSerial.println("AT+DR=EU868"); delay(200);
    LoRaSerial.println("AT+CLASS=A"); delay(200);

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);
}

void macStringToBytes(const String& macStr, uint8_t* byte_array) {
    sscanf(macStr.c_str(), "%hhx:%hhx:%hhx:%hhx:%hhx:%hhx", 
           &byte_array[0], &byte_array[1], &byte_array[2], 
           &byte_array[3], &byte_array[4], &byte_array[5]);
}

void loop() {
    if (!isJoined) {
        isJoined = joinNetwork();
        if (!isJoined) {
            delay(LORAWAN_TX_INTERVAL);
            return; 
        }
    }

    Serial.println("\n--- SCAN WIFI ---");
    //int n = WiFi.scanNetworks();
    // false : scan bloquant (on attend la fin)
    // true  : afficher les réseaux cachés (utile pour tout voir)
    // true  : MODE PASSIF (Le plus important !)
    // 300   : temps d'écoute par canal en millisecondes
    int n = WiFi.scanNetworks(false, true, true, 300);
    
    // Besoin de 3 APs minimum pour une bonne trilatération
    if (n < 3) {
        Serial.println("Moins de 3 réseaux trouvés. Attente...");
        delay(LORAWAN_TX_INTERVAL);
        return;
    }

    // Recherche des 3 meilleurs signaux
    // On stocke les indices des réseaux triés par RSSI décroissant
    int indices[n];
    for(int i=0; i<n; i++) indices[i] = i;

    // Tri simple (Bubble sort) des indices basé sur le RSSI
    for(int i=0; i<n-1; i++) {
        for(int j=0; j<n-i-1; j++) {
            if(WiFi.RSSI(indices[j]) < WiFi.RSSI(indices[j+1])) {
                int temp = indices[j];
                indices[j] = indices[j+1];
                indices[j+1] = temp;
            }
        }
    }

    // Récupération des 3 meilleurs
    int best_indices[3] = {indices[0], indices[1], indices[2]};
    
    // Construction du payload : 3 APs * (6 bytes MAC + 1 byte RSSI) = 21 bytes
    uint8_t payload[21]; 
    
    for (int i = 0; i < 3; i++) {
        String bssid = WiFi.BSSIDstr(best_indices[i]);
        int rssi = WiFi.RSSI(best_indices[i]);
        
        Serial.printf("AP%d: %s, RSSI: %d\n", i+1, bssid.c_str(), rssi);
        
        // Offset de 7 octets pour chaque AP (0, 7, 14)
        macStringToBytes(bssid, &payload[i * 7]);
        payload[(i * 7) + 6] = (int8_t)rssi;
    }

    String hexPayload = "";
    for (int i = 0; i < 21; i++) {
        char hex[3];
        sprintf(hex, "%02X", payload[i]);
        hexPayload += hex;
    }
    
    if (sendData(hexPayload)) {
        Serial.println("Données envoyées.");
    } else {
        isJoined = false; 
    }

    delay(LORAWAN_TX_INTERVAL);
}