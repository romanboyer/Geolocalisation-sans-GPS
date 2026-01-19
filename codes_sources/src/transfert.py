import pandas as pd

# 1. Chargement des données
# Fichier "Ce que j'ai déjà" (Format Cible)
df_target = pd.read_csv('wigle_jussieu.csv')

# Fichier "Ce que je veux modifier" (Format WiGLE)
# 'skiprows=1' ignore la première ligne de métadonnées (WigleWifi-1.6...)
df_wigle = pd.read_csv('wigle_all_jussieu.csv', skiprows=1)

# 2. Mapping : Dictionnaire de correspondance [Source] -> [Cible]
colonnes_mapping = {
    'MAC': 'netid',
    'SSID': 'ssid',
    'CurrentLatitude': 'trilat',
    'CurrentLongitude': 'trilong',
    'FirstSeen': 'lasttime'
}

# Renommage des colonnes du fichier WiGLE
df_wigle = df_wigle.rename(columns=colonnes_mapping)

# 3. Filtrage et Typage
# On ne garde que les colonnes présentes dans le fichier cible
# Cela élimine automatiquement AuthMode, Channel, RSSI, etc.
df_wigle = df_wigle[df_target.columns]

# Harmonisation du format de date pour correspondre à "2022-02-21T04:18:27.000Z"
# WiGLE est par défaut sans 'T' ni 'Z'
df_wigle['lasttime'] = pd.to_datetime(df_wigle['lasttime'])
df_wigle['lasttime'] = df_wigle['lasttime'].dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')

# 4. Fusion
df_final = pd.concat([df_target, df_wigle], ignore_index=True)

# 5. Export
df_final.to_csv('fusion_complete.csv', index=False)