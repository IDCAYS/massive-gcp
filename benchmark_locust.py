#!/usr/bin/env python3
import subprocess
import csv
import time
import os
import sys
import requests

def get_nb_instances():
    """Récupère le nombre d'instances actives sur App Engine via gcloud."""
    try:
        cmd = ["gcloud", "app", "instances", "list", "--format=value(id)"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
            return len(lines)
        return "N/A"
    except Exception:
        return "N/A"

def kill_all_instances():
    """Supprime toutes les instances actives sur App Engine pour forcer un reset."""
    print(">>> Suppression des instances en cours...")
    try:
        # Récupère service, version et id pour pouvoir supprimer précisément
        cmd = ["gcloud", "app", "instances", "list", "--format=value(service,version,id)"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
            for line in lines:
                parts = line.split()
                if len(parts) == 3:
                    svc, ver, inst_id = parts
                    subprocess.run(["gcloud", "app", "instances", "delete", inst_id, "--service", svc, "--version", ver, "--quiet"], capture_output=True, check=False)
    except Exception as e:
        print(f"Erreur kill instances: {e}")

def run_locust_step(url, users, run_id):
    """Lance Locust en mode headless pour une configuration et extrait les stats."""
    print(f"\n>>> Test: {users} utilisateurs, Run: {run_id}")
    
    # Paramètres
    duration = "30s" # Durée de chaque test pour stabiliser la mesure
    spawn_rate = users # On lance tous les utilisateurs immédiatement
    output_prefix = f"locust_results_{users}_{run_id}"
    locust_file = "/home/julien_rebours02/massive-gcp/locustfile.py"
    
    cmd = [
        "locust",
        "-f", locust_file,
        "--headless",
        "-u", str(users),
        "-r", str(spawn_rate),
        "--run-time", duration,
        "--csv", output_prefix,
        "--host", url,
        "--only-summary"
    ]
    
    # On lance Locust
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # On attend la moitié du temps pour laisser l'autoscaler réagir avant de compter les instances
    time.sleep(15)
    nb_instances = get_nb_instances()
    
    # On attend la fin du test
    process.wait()
    
    avg_time = "0ms"
    failed = 0
    stats_file = f"{output_prefix}_stats.csv"
    
    if os.path.exists(stats_file):
        with open(stats_file, mode='r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # On récupère la ligne 'Aggregated' qui contient la moyenne globale
                if row['Name'] == "Aggregated":
                    avg_time = f"{float(row['Average Response Time']):.1f}ms"
                    failed = 1 if int(row['Failure Count']) > 0 else 0
        
        # Nettoyage des fichiers CSV générés par Locust pour ce run
        for f in os.listdir('.'):
            if f.startswith(output_prefix):
                os.remove(f)
                
    return [users, avg_time, run_id, failed, nb_instances]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 benchmark_locust.py https://tinyinsta2026.ew.r.appspot.com/")
        sys.exit(1)

    target_url = sys.argv[1].rstrip('/')
    config_levels = [1, 10, 20, 50, 100, 1000]
    
    # Warm-up : Réveil de l'instance pour éviter le cold start au premier test
    print(">>> Réveil de l'instance (warm-up)...")
    try:
        requests.get(target_url, timeout=30)
        time.sleep(5)
    except Exception as e:
        print(f"Note: Erreur lors du warm-up : {e}")

    output_csv = "conc.csv"
    with open(output_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["PARAM", "AVG_TIME", "RUN", "FAILED", "NB INSTANCES"])
        
        for users in config_levels:
            for run in range(1, 4):
                row = run_locust_step(target_url, users, run)
                writer.writerow(row)
                f.flush()
                kill_all_instances()
                # Pause pour stabiliser l'environnement et laisser GCP traiter les suppressions
                time.sleep(15)

    print(f"\nExpérience terminée. Les résultats sont dans {output_csv}")
