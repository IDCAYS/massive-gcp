#!/usr/bin/env python3
import subprocess
import csv
import time
import os
import sys
import requests
from google.cloud import datastore

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

def warm_up(url):
    """Réveil de l'instance pour éviter le cold start avant une mesure."""
    print(">>> Warm-up (réveil de l'instance)...")
    try:
        requests.get(url, timeout=30)
        time.sleep(5) 
    except Exception as e:
        print(f"Note: Échec du warm-up : {e}")

def reset_follows_in_datastore(prefix, count):
    """Réinitialise les abonnements à vide directement dans Datastore pour éviter l'accumulation."""
    print(f">>> Nettoyage Datastore : réinitialisation des abonnements pour les utilisateurs '{prefix}'...")
    client = datastore.Client()
    all_keys = [client.key('User', f"{prefix}{i}") for i in range(1, count + 1)]
    
    # Traitement par lots de 500 (limite Datastore)
    for i in range(0, len(all_keys), 500):
        batch_keys = all_keys[i:i+500]
        entities = client.get_multi(batch_keys)
        for entity in entities:
            entity['follows'] = []
        if entities:
            client.put_multi(entities)

def trigger_seed(url, users, posts, follows, token):
    """Appelle l'endpoint /admin/seed pour configurer l'état de la base."""
    print(f">>> Configuration : {users} users, {posts} nouveaux posts, fan-out cible {follows}...")
    data = {
        'users': users,
        'posts': posts,
        'follows_min': follows,
        'follows_max': follows,
        'token': token
    }
    try:
        resp = requests.post(f"{url}/admin/seed", data=data, timeout=600)
        if resp.status_code == 200:
            print(f"Seed Success: {resp.json()}")
        else:
            print(f"Seed Error: Status {resp.status_code}")
    except Exception as e:
        print(f"Seed Exception (l'opération peut continuer en arrière-plan) : {e}")

def run_locust_step(url, concurrent_users, param_value, run_id):
    """Lance Locust et extrait les statistiques de performance pour un palier donné."""
    print(f"\n>>> Test Concurrence: {concurrent_users}, Fan-out (PARAM): {param_value}, Run: {run_id}")
    
    duration = "60s" # Augmenté pour stabiliser la moyenne des temps de réponse
    spawn_rate = 5   # Plus progressif pour laisser l'autoscaler réagir sans saturer le CPU
    output_prefix = f"locust_fanout_{param_value}_{run_id}"
    locust_file = "/home/julien_rebours02/massive-gcp/locustfile.py"
    
    cmd = [
        "locust",
        "-f", locust_file,
        "--headless",
        "-u", str(concurrent_users),
        "-r", str(spawn_rate),
        "--run-time", duration,
        "--csv", output_prefix,
        "--host", url,
        "--only-summary"
    ]
    
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # On attend que l'autoscaler réagisse à la charge avant de compter les instances
    time.sleep(30)
    nb_instances = get_nb_instances()
    
    process.wait()
    
    avg_time = "0ms"
    failed = 0
    stats_file = f"{output_prefix}_stats.csv"
    
    if os.path.exists(stats_file):
        with open(stats_file, mode='r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Name'] == "Aggregated":
                    avg_time = f"{float(row['Average Response Time']):.1f}ms"
                    failed = 1 if int(row['Failure Count']) > 0 else 0
        
        # Nettoyage des fichiers temporaires Locust
        for f_name in os.listdir('.'):
            if f_name.startswith(output_prefix):
                os.remove(f_name)
                
    return [param_value, avg_time, run_id, failed, nb_instances]

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 benchmark_fanout.py https://tinyinsta2026.ew.r.appspot.com/ julieninsta")
        sys.exit(1)

    target_url = sys.argv[1].rstrip('/')
    seed_token = sys.argv[2]
    
    # Paramètres de l'expérience
    nb_users = 1000
    concurrent_users = 50
    fanout_levels = [20, 40, 60]
    
    output_csv = "fanout.csv"
    
    with open(output_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["PARAM", "AVG_TIME", "RUN", "FAILED", "NB INSTANCES"])
        

        for i, follows in enumerate(fanout_levels):
            # On vide les abonnements existants directement en base avant de demander le seed
            reset_follows_in_datastore('user', nb_users)
            
            # On ne rajoute plus de posts (0), on fait varier uniquement le nombre d'abonnés (PARAM)
            trigger_seed(target_url, nb_users, 0, follows, seed_token)
            
            for run in range(1, 4):
                warm_up(target_url)
                result = run_locust_step(target_url, concurrent_users, follows, run)
                writer.writerow(result)
                f.flush()
                kill_all_instances()
                # Pause pour stabiliser l'environnement et laisser GCP traiter les suppressions
                time.sleep(15)

    print(f"\nExpérience terminée. Résultats enregistrés dans {output_csv}")