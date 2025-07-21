#!/usr/bin/env python3
import os
import re
import shutil

# Percorso delle cartelle che contengono file e cartelle duplicate
ANIME_FOLDER = "/mnt/e/Anime"

def fix_anime_structure():
    """Corregge la struttura delle cartelle duplicate in Anime/Serie/Serie"""
    print("Correzione struttura cartelle anime...")
    
    # Verifica e corregge la struttura "Serie/Serie/"
    serie_path = os.path.join(ANIME_FOLDER, "Serie", "Serie")
    if os.path.exists(serie_path):
        print(f"Trovato percorso duplicato: {serie_path}")
        
        # Sposta i contenuti un livello sopra
        for item in os.listdir(serie_path):
            src = os.path.join(serie_path, item)
            dst = os.path.join(ANIME_FOLDER, "Serie", item)
            
            if os.path.exists(dst):
                print(f"ATTENZIONE: {dst} esiste già, merge in corso...")
                # Se è una cartella, sposta i contenuti
                if os.path.isdir(src) and os.path.isdir(dst):
                    for sub_item in os.listdir(src):
                        sub_src = os.path.join(src, sub_item)
                        sub_dst = os.path.join(dst, sub_item)
                        if os.path.exists(sub_dst):
                            print(f"  Salta {sub_src}, destinazione esiste già")
                        else:
                            print(f"  Sposta {sub_src} -> {sub_dst}")
                            shutil.move(sub_src, sub_dst)
            else:
                print(f"Sposta {src} -> {dst}")
                shutil.move(src, dst)
        
        # Rimuovi la cartella duplicata se vuota
        if os.path.exists(serie_path) and len(os.listdir(serie_path)) == 0:
            print(f"Rimozione cartella vuota: {serie_path}")
            os.rmdir(serie_path)

def remove_empty_folders(path):
    """Rimuove ricorsivamente cartelle vuote a partire da un percorso"""
    if not os.path.isdir(path):
        return
        
    # Ricorsivamente rimuovi cartelle vuote nei sottopercorsi
    files = os.listdir(path)
    if len(files):
        for f in files:
            fullpath = os.path.join(path, f)
            if os.path.isdir(fullpath):
                remove_empty_folders(fullpath)

    # Se dopo la ricorsione la cartella è vuota, rimuovila
    files = os.listdir(path)
    if len(files) == 0:
        print(f"Rimozione cartella vuota: {path}")
        os.rmdir(path)

def fix_original_folders():
    """Rimuove le cartelle originali vuote dopo il rinomino dei file"""
    print("Rimozione cartelle originali vuote...")
    
    # Percorsi da controllare
    paths = [
        os.path.join(ANIME_FOLDER, "Serie"),
        os.path.join(ANIME_FOLDER)
    ]
    
    for path in paths:
        for item in os.listdir(path):
            # Controlla se la cartella ha un nome che sembra un file rinominato
            # (es. demon-slayer-ita)
            if "-" in item and os.path.isdir(os.path.join(path, item)):
                item_path = os.path.join(path, item)
                print(f"Controllo cartella originale: {item_path}")
                remove_empty_folders(item_path)

if __name__ == "__main__":
    print("Correzione struttura cartelle Plex...")
    
    # 1. Correggi la struttura Serie/Serie
    fix_anime_structure()
    
    # 2. Rimuovi cartelle originali vuote
    fix_original_folders()
    
    print("Completato!")
