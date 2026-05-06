#!/usr/bin/env python3
import sys
from google.cloud import datastore

def prune_posts(target_count=100000):
    """Supprime les posts excédentaires pour atteindre exactement target_count."""
    client = datastore.Client()

    print(f"Nettoyage de la base de données pour atteindre la cible de {target_count} posts...")
    
    deleted_total = 0
    batch_size = 500  # Limite maximale par opération delete_multi sur Datastore

    while True:
        # On utilise keys_only pour minimiser le transfert de données et éviter les timeouts
        query = client.query(kind='Post')
        query.keys_only()
        
        # On récupère uniquement les clés situées APRES le 100 000ème post
        # L'offset permet de "sauter" les posts que l'on veut conserver
        iterator = query.fetch(limit=batch_size, offset=target_count)
        keys_to_delete = [entity.key for entity in iterator]

        if not keys_to_delete:
            break

        client.delete_multi(keys_to_delete)
        deleted_total += len(keys_to_delete)
        print(f"Progression : {deleted_total} posts supprimés", end='\r')

    print(f"\nTerminé. {deleted_total} posts supprimés au total.")

if __name__ == "__main__":
    # Utilisation : python3 prune_posts.py [nombre_cible]
    target = 100000
    if len(sys.argv) > 1:
        try:
            target = int(sys.argv[1])
        except ValueError:
            pass
    prune_posts(target)

