import pandas as pd
import matplotlib.pyplot as plt

# Charger les données depuis le fichier CSV
csv_path = '/home/julien_rebours02/massive-gcp/fanout.csv'
df = pd.read_csv(csv_path)

# Nettoyer la colonne AVG_TIME pour convertir les chaînes (ex: "136.1ms") en nombres
df['AVG_TIME_NUM'] = df['AVG_TIME'].str.replace('ms', '', regex=False).astype(float)

# Calculer la moyenne du temps de réponse pour chaque niveau de concurrence (PARAM)
avg_results = df.groupby('PARAM')['AVG_TIME_NUM'].mean().reset_index()

# Configuration du graphique
plt.figure(figsize=(10, 6))
plt.bar(avg_results['PARAM'].astype(str), avg_results['AVG_TIME_NUM'], color='skyblue', edgecolor='navy')

# Ajout des labels, titre et grille
plt.xlabel('Nombre de followee (PARAM)')
plt.ylabel('Temps de réponse moyen (ms)')
plt.title('Performance App Engine : Nombre de followee')
plt.grid(axis='y', linestyle='--', alpha=0.6)

# Sauvegarder l'image au format PNG
plt.savefig('/home/julien_rebours02/massive-gcp/results_barplot_fanout.png')