"""
Plex media naming utility for StreamingCommunity.
Ensures all downloaded files follow Plex naming conventions for optimal library integration.
Incorporates TMDB IDs for better Plex matching when available.
"""

import os
import re
import logging
from typing import Optional, Tuple, Dict, Any
import datetime
import time
import shutil

# Import TMDB functionality
from StreamingCommunity.Lib.TMBD.tmdb import TheMovieDB
from StreamingCommunity.Lib.TMBD.obj_tmbd import Json_film

from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Util.os import os_manager


class PlexNaming:
    """
    Handles post-processing of downloaded files to follow Plex naming conventions.
    """
    
    def __init__(self, custom_root_path=None):
        """Initialize PlexNaming with configuration settings.
        
        Args:
            custom_root_path: Optional path to override the default root path from config.
        """
        # Mapped folders
        self.film_folder = os.path.normpath(config_manager.get('OUT_FOLDER', 'movie_folder_name'))
        self.serie_folder = os.path.normpath(config_manager.get('OUT_FOLDER', 'serie_folder_name'))
        self.anime_folder = os.path.normpath(config_manager.get('OUT_FOLDER', 'anime_folder_name'))
        self.anime_movie_folder = os.path.normpath(config_manager.get('OUT_FOLDER', 'anime_movie_folder_name'))
        
        # Root path - usa quello custom se fornito, altrimenti prende dal config
        if custom_root_path:
            self.root_path = custom_root_path
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Usando root path custom: {custom_root_path}\n")
        else:
            self.root_path = config_manager.get('OUT_FOLDER', 'root_path')
        
        # Whether to add site name to the path
        self.add_site_name = config_manager.get_bool("OUT_FOLDER", "add_siteName")
        
        # Whether to use TMDB IDs in file names
        # Verifica se la chiave esiste prima di ottenerla, altrimenti usa True come default
        try:
            self.use_tmdb_ids = config_manager.get_bool("OUT_FOLDER", "use_tmdb_ids")
        except:
            self.use_tmdb_ids = True
        
        # Initialize TheMovieDB API client
        self.tmdb_api = TheMovieDB("a800ed6c93274fb857ea61bd9e7256c5")
        
        # Configure logger
        self.logger = logging.getLogger("PlexNaming")
        
    def _remove_empty_folders(self, path):
        """
        Rimuove ricorsivamente le cartelle vuote a partire dal percorso specificato.
        
        Args:
            path: Il percorso da cui iniziare la rimozione delle cartelle vuote
        """
        try:
            # Controllo se il percorso esiste ancora (potrebbe essere già stato rimosso)
            if not os.path.exists(path):
                return
                
            # Se è un file, non fare nulla
            if not os.path.isdir(path):
                return
                
            # Prima controlla e pulisci tutte le sottocartelle
            for item in os.listdir(path):
                self._remove_empty_folders(os.path.join(path, item))
                
            # Ora controlla se questa cartella è vuota
            if len(os.listdir(path)) == 0:
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Rimuovo cartella vuota: {path}\n")
                os.rmdir(path)
                
        except Exception as e:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Errore rimuovendo cartella vuota {path}: {str(e)}\n")
                
    def _identify_media_type_via_tmdb(self, title: str, year: str = None) -> Dict[str, Any]:
        """
        Identifica il tipo di media (film, serie, anime) usando TMDB.
        
        Args:
            title: Titolo del media
            year: Anno di uscita, se disponibile
            
        Returns:
            Dizionario con informazioni sul tipo di media
        """
        with open("/tmp/plex_naming_debug.log", "a") as f:
            f.write(f"\n==== INIZIO IDENTIFICAZIONE TMDB ====\n")
            f.write(f"Identificazione tipo media via TMDB per: {title} ({year if year else 'anno sconosciuto'})\n")
        
        # Preparazione query di ricerca
        search_title = re.sub(r'(?i)[-_\s](ita|eng|sub|dub)(?:bed)?(?:_|$|[-\s])', '', title)
        search_title = search_title.replace('-', ' ').replace('_', ' ')
        search_title = re.sub(r'\s+', ' ', search_title).strip()
        
        search_query = search_title
        if year:
            search_query += f" {year}"
        
        with open("/tmp/plex_naming_debug.log", "a") as f:
            f.write(f"Query di ricerca preparata: '{search_query}'\n")
            
        try:
            # Prima prova a cercare come film
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Ricerca film su TMDB con query: {search_query}\n")
                
            movie_data = self.tmdb_api._make_request("search/movie", {"query": search_query}).get("results", [])
            
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Risultati film trovati: {len(movie_data)}\n")
                if movie_data:
                    top_movie = movie_data[0]
                    f.write(f"Primo risultato film: {top_movie.get('title')} ({top_movie.get('release_date', 'sconosciuto')[:4] if top_movie.get('release_date') else 'sconosciuto'}) ID: {top_movie.get('id')}\n")
            
            # Poi prova a cercare come serie TV
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Ricerca serie TV su TMDB con query: {search_query}\n")
                
            tv_data = self.tmdb_api._make_request("search/tv", {"query": search_query}).get("results", [])
            
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Risultati serie trovati: {len(tv_data)}\n")
                if tv_data:
                    top_tv = tv_data[0]
                    f.write(f"Primo risultato serie: {top_tv.get('name')} ({top_tv.get('first_air_date', 'sconosciuto')[:4] if top_tv.get('first_air_date') else 'sconosciuto'}) ID: {top_tv.get('id')}\n")
            
            # Se non ci sono risultati, non possiamo determinare il tipo via TMDB
            if not movie_data and not tv_data:
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Nessun risultato TMDB trovato per '{search_query}'\n")
                    f.write(f"==== FINE IDENTIFICAZIONE TMDB: FALLIMENTO ====\n")
                return None
                
            # Determina se è film o serie in base ai risultati migliori
            is_series = False
            result = None
            
            # Se abbiamo risultati per entrambi, scegli quello con punteggio di popolarità più alto
            if movie_data and tv_data:
                movie_popularity = movie_data[0].get('popularity', 0)
                tv_popularity = tv_data[0].get('popularity', 0)
                
                if tv_popularity > movie_popularity:
                    is_series = True
                    result = tv_data[0]
                else:
                    result = movie_data[0]
            elif tv_data:
                is_series = True
                result = tv_data[0]
            else:
                result = movie_data[0]
                
            # Se abbiamo un risultato, controlliamo se è un anime giapponese
            is_anime = False
            tmdb_id = result['id']
            
            # Per le serie TV, ottieni dettagli completi
            if is_series:
                details = self.tmdb_api._make_request(f"tv/{tmdb_id}")
                
                # Controlla origine e generi
                origin_country = details.get('origin_country', [])
                genres = [genre['name'].lower() for genre in details.get('genres', [])]
                
                # Controlla anche le keywords per riferimenti all'anime
                keywords = self.tmdb_api._make_request(f"tv/{tmdb_id}/keywords").get('results', [])
                keyword_names = [k['name'].lower() for k in keywords]
                
                # Determina se è un anime
                is_anime = ('JP' in origin_country or 'Japan' in origin_country or 
                           'animation' in genres or 'anime' in genres or
                           'anime' in keyword_names or 'japanese animation' in keyword_names)
                
            # Per i film, ottieni dettagli completi
            else:
                details = self.tmdb_api._make_request(f"movie/{tmdb_id}")
                
                # Controlla origine e generi
                production_countries = [c['iso_3166_1'] for c in details.get('production_countries', [])]
                genres = [genre['name'].lower() for genre in details.get('genres', [])]
                
                # Controlla anche le keywords per riferimenti all'anime
                keywords = self.tmdb_api._make_request(f"movie/{tmdb_id}/keywords").get('keywords', [])
                keyword_names = [k['name'].lower() for k in keywords]
                
                # Determina se è un anime
                is_anime = ('JP' in production_countries or 
                           'animation' in genres or 'anime' in genres or
                           'anime' in keyword_names or 'japanese animation' in keyword_names)
            
            # Crea il tipo di media basato sulle informazioni TMDB
            media_type = {}
            if is_anime:
                if is_series:
                    media_type = {"type": "anime_series", "is_series": True, "is_anime": True, "tmdb_id": tmdb_id}
                else:
                    media_type = {"type": "anime_movie", "is_series": False, "is_anime": True, "tmdb_id": tmdb_id}
            else:
                if is_series:
                    media_type = {"type": "series", "is_series": True, "is_anime": False, "tmdb_id": tmdb_id}
                else:
                    media_type = {"type": "movie", "is_series": False, "is_anime": False, "tmdb_id": tmdb_id}
            
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Tipo media determinato via TMDB: {media_type}\n")
                f.write(f"TMDB ID assegnato: {tmdb_id} per {result.get('title', result.get('name', 'unknown'))}\n")
                f.write(f"==== FINE IDENTIFICAZIONE TMDB: SUCCESSO ====\n")
            
            return media_type
        
        except Exception as e:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Errore durante identificazione TMDB: {str(e)}\n")
                f.write(f"Tentativo di recupero manuale del film su TMDB...\n")
            
            # Tentativo di recupero diretto del film anche in caso di errore
            try:
                # Pulizia del titolo per migliorare le chance di match
                search_title = title.replace('.', ' ').replace('-', ' ').replace('_', ' ')
                search_title = re.sub(r'\s+', ' ', search_title).strip()
                
                search_query = search_title
                if year:
                    search_query += f" {year}"
                
                # Ricerca diretta del film
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Ricerca di emergenza film: {search_query}\n")
                    
                data = self.tmdb_api._make_request("search/movie", {"query": search_query}).get("results", [])
                if data:
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Trovato film in ricerca emergenza: {data[0].get('title')} ({data[0].get('id')})\n")
                    
                    tmdb_id = data[0]['id']
                    media_type = {"type": "movie", "is_series": False, "is_anime": False, "tmdb_id": tmdb_id}
                    return media_type
            except Exception as recovery_error:
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Anche il tentativo di recupero è fallito: {str(recovery_error)}\n")
            
            # Se tutto fallisce, ritorniamo un tipo base senza ID TMDB
            return None
                
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Tipo media determinato: {media_type['type']}\n")
                f.write(f"TMDB IDs abilitati: {self.use_tmdb_ids}\n")
                # Log se abbiamo un TMDB ID dal processo di identificazione
                if 'tmdb_id' in media_type:
                    f.write(f"TMDB ID trovato nell'identificazione media: {media_type['tmdb_id']}\n")
                else:
                    f.write(f"ERRORE: Impossibile determinare il tipo di media per {file_path}\n")
                    # Aggiungiamo una verifica manuale per anime
                    if '/Anime/' in file_path:
                        f.write(f"Rilevamento manuale: percorso contiene /Anime/\n")
                        if '/Serie/' in file_path:
                            media_type = {"type": "anime_series", "is_series": True, "is_anime": True}
                            f.write(f"Forzato tipo media a: {media_type}\n")
            
            if not media_type:
                self.logger.warning(f"Could not determine media type for {file_path}")
                return file_path
                
            # Get file information
            file_info = self._extract_file_info(file_path, media_type)
            
            # Log delle informazioni estratte
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Informazioni file estratte: {file_info}\n")
            
            # Trasferisci TMDB ID se disponibile dal processo di identificazione del tipo media
            if 'tmdb_id' in media_type and self.use_tmdb_ids:
                file_info['tmdb_id'] = media_type['tmdb_id']
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"TMDB ID trasferito da media_type: {media_type['tmdb_id']}\n")
            
            # Try to enrich with TMDB metadata if enabled
            if self.use_tmdb_ids:
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Prima dell'arricchimento TMDB: {file_info}\n")
                    if 'tmdb_id' in file_info:
                        f.write(f"TMDB ID già presente: {file_info['tmdb_id']}\n")
                        
                self._enrich_with_tmdb_metadata(file_info, media_type)
                
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Dopo arricchimento TMDB: {file_info}\n")
                    if 'tmdb_id' in file_info:
                        f.write(f"TMDB ID dopo arricchimento: {file_info['tmdb_id']}\n")
                    else:
                        f.write(f"ATTENZIONE: Nessun TMDB ID presente dopo arricchimento\n")
            
            # Generate new file path based on Plex naming conventions
            new_path = self._generate_plex_path(file_path, file_info, media_type)
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Nuovo percorso generato: {new_path}\n")
            
            # Perform the rename operation if paths are different
            if new_path != file_path and new_path:
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Tentativo di rinomina: {file_path} -> {new_path}\n")
                    
                # Make sure parent directory exists
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                
                try:
                    # Ottieni la cartella originale prima dello spostamento
                    original_dir = os.path.dirname(file_path)
                    
                    # Rename the file
                    os.rename(file_path, new_path)
                    self.logger.info(f"Renamed {os.path.basename(file_path)} to {os.path.basename(new_path)}")
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"SUCCESSO: Rinominato in {new_path}\n")
                        
                    # Rimuovi le cartelle vuote dopo lo spostamento del file
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Controllo e rimozione cartelle vuote in: {original_dir}\n")
                    self._remove_empty_folders(original_dir)
                    
                    return new_path
                except Exception as rename_err:
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"ERRORE durante la rinomina: {str(rename_err)}\n")
                    raise rename_err
                
            return file_path
            
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {str(e)}")
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"ECCEZIONE: {str(e)}\n")
                import traceback
                f.write(traceback.format_exc())
            return file_path
    
    def _determine_media_type(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Determine media type based on file path.
        
        Returns a dict with:
            type: 'movie', 'series', 'anime_movie', 'anime_series'
            is_series: True if series, False if movie
            is_anime: True if anime, False otherwise
        """
        normalized_path = os.path.normpath(file_path)
        file_name = os.path.basename(normalized_path).lower()
        
        # Log per debug
        with open("/tmp/plex_naming_debug.log", "a") as f:
            f.write(f"Determinazione tipo media per: {file_path}\n")
            f.write(f"Root path configurato: {self.root_path}\n")
            f.write(f"File name: {file_name}\n")
        
        # Controllo diretto nel percorso per pattern comuni
        path_lower = normalized_path.lower()
        
        # Verifica se è un anime in base al percorso o nome file
        is_anime_path = ('/anime/' in path_lower or '/anime\\' in path_lower)
        anime_keywords = ['anime', 'japan', 'jap', 'jpn']
        
        # Lista di serie anime note per distinguerle dai film
        anime_series_names = ['demon slayer', 'one piece', 'naruto', 'attack on titan', 
                             'boku no hero', 'my hero', 'dragon ball', 'hunter x hunter',
                             'death note', 'sword art', 'fullmetal', 'jujutsu kaisen',
                             'pokemon', 'digimon', 'bleach', 'chainsaw man']
                             
        # Lista di film anime noti
        anime_movie_names = ['your name', 'weathering with you', 'spirited away', 
                            'princess mononoke', 'howl moving castle', 'akira',
                            'ghost in the shell', 'a silent voice', 'grave of the fireflies',
                            'my neighbor totoro', 'promare', 'jujutsu kaisen 0']
    
        # Controlli per anime
        is_anime_name = any(keyword in path_lower for keyword in anime_keywords)
        
        # Verifica se è un film anime noto - questa ha precedenza assoluta
        normalized_filename = file_name.replace('-', '').replace('_', '').replace('.', '').replace(' ', '').lower()
        is_anime_movie = any(name.replace(' ', '') in normalized_filename for name in anime_movie_names)
        
        # Se è un film anime noto, restituisci immediatamente questo tipo
        if is_anime_movie:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Film anime noto rilevato: {file_name}\n")
            return {"type": "anime_movie", "is_series": False, "is_anime": True}
        
        # Verifica per le serie anime note
        is_anime_series = any(name.replace(' ', '') in normalized_filename 
                              for name in anime_series_names)
        
        # Verifica se è una serie in base al nome o percorso
        is_series_path = ('/serie/' in path_lower or '/series/' in path_lower or '/serie\\' in path_lower or '/series\\' in path_lower)
        is_series_name = ('s01' in file_name or 's02' in file_name or 
                         'stagione' in file_name or 'season' in file_name or
                         '_ep_' in file_name or 'episodio' in file_name or
                         'episode' in file_name)
        
        with open("/tmp/plex_naming_debug.log", "a") as f:
            f.write(f"Analisi percorso: anime={is_anime_path}, serie={is_series_path}\n")
            f.write(f"Analisi nome: anime={is_anime_name}, anime series={is_anime_series}, serie={is_series_name}\n")
        
        # Prima prova il metodo standard usando root_path
        if self.root_path in normalized_path:
            relative_path = normalized_path.replace(self.root_path, '').lstrip(os.sep)
            parts = relative_path.split(os.sep)
            
            # Skip site name folder if present
            if self.add_site_name and parts:
                parts = parts[1:]
            
            if parts:
                # Determine media type
                if parts[0] == self.film_folder:
                    return {"type": "movie", "is_series": False, "is_anime": False}
                    
                elif parts[0] == self.serie_folder:
                    return {"type": "series", "is_series": True, "is_anime": False}
                    
                elif parts[0] == self.anime_folder:
                    if len(parts) > 1:
                        if parts[1] == "Film" or parts[1].lower() == "film":
                            return {"type": "anime_movie", "is_series": False, "is_anime": True}
                        elif parts[1] == "Serie" or parts[1].lower() == "serie":
                            return {"type": "anime_series", "is_series": True, "is_anime": True}
                    else:
                        # Se è nella cartella anime ma non specifica film/serie, assumiamo serie
                        return {"type": "anime_series", "is_series": True, "is_anime": True}
        
        # Prova a determinare il tipo tramite TMDB
        with open("/tmp/plex_naming_debug.log", "a") as f:
            f.write(f"Tentativo di identificazione tramite TMDB...\n")
        
        # Estrai un titolo plausibile dal nome del file
        possible_title = os.path.basename(file_path).lower()
        possible_title = re.sub(r'\.(mp4|avi|mkv|mov)$', '', possible_title)  # Rimuovi estensione
        possible_title = re.sub(r's\d+e\d+', '', possible_title)  # Rimuovi S01E01
        possible_title = re.sub(r'(?i)[-_\s](ita|eng|sub|dub)(?:bed)?(?:_|$|[-\s])', '', possible_title)  # Rimuovi tag lingua
        possible_title = possible_title.replace('.', ' ').replace('-', ' ').replace('_', ' ')
        possible_title = re.sub(r'\s+', ' ', possible_title).strip()
        
        # Estrai anno se presente
        year_match = re.search(r'(19|20)\d{2}', file_name)
        year = year_match.group(0) if year_match else None
        
        # Cerca di ottenere il tipo da TMDB
        tmdb_media_type = self._identify_media_type_via_tmdb(possible_title, year)
        
        # Se TMDB ha fornito un risultato valido, usalo
        if tmdb_media_type:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Usando tipo media da TMDB: {tmdb_media_type}\n")
                if 'tmdb_id' in tmdb_media_type:
                    f.write(f"TMDB ID trovato e sarà usato: {tmdb_media_type['tmdb_id']}\n")
                else:
                    f.write(f"ATTENZIONE: Nessun TMDB ID presente nel risultato!\n")
            return tmdb_media_type
            
        # Fallback basato su analisi euristica del percorso e nome file
        with open("/tmp/plex_naming_debug.log", "a") as f:
            f.write(f"TMDB non ha dato risultati, usando metodo fallback per determinare tipo media\n")
            
        # Verifica se è un film anime noto (priorità massima)
        if is_anime_movie:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Determinato come anime film (da lista film noti) tramite fallback\n")
            return {"type": "anime_movie", "is_series": False, "is_anime": True}
        
        # Se è un anime (da percorso, nome o lista serie anime note)
        if is_anime_path or is_anime_name or is_anime_series:
            # Determina se è una serie o un film
            if is_series_path or is_series_name:
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Determinato come anime serie tramite fallback\n")
                return {"type": "anime_series", "is_series": True, "is_anime": True}
            else:
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Determinato come anime film (da heuristica) tramite fallback\n")
                return {"type": "anime_movie", "is_series": False, "is_anime": True}
        
        # Se non è un anime ma è una serie
        elif is_series_path or is_series_name:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Determinato come serie normale tramite fallback\n")
            return {"type": "series", "is_series": True, "is_anime": False}
        
        # Default a film normale se non ci sono altri indicatori
        with open("/tmp/plex_naming_debug.log", "a") as f:
            f.write(f"Non riuscito a determinare tipo media con metodi specifici, usando fallback generico 'film'\n")
            
        # IMPORTANTE: Anziché restituire None, ritorniamo un tipo predefinito (film)
        # Questo evita l'errore contraddittorio nei log e assicura che il processo continui
        return {"type": "movie", "is_series": False, "is_anime": False}
    
    def _extract_file_info(self, file_path: str, media_type: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract title, year, season, episode from the file path and name.
        
        Returns a dict with available information:
            title: Media title
            year: Release year (if available)
            season: Season number (if series)
            episode: Episode number (if series)
            language: Language suffix (if present)
        """
        file_name = os.path.basename(file_path)
        parent_dir = os.path.basename(os.path.dirname(file_path))
        
        # Remove file extension
        name_without_ext = os.path.splitext(file_name)[0]
        
        # Inizializzazione info di base
        info = {
            "title": None,  
            "year": None,
            "season": None, 
            "episode": None,
            "language": None
        }
        
        # Aggiungi altri log per debug dell'estrazione info
        with open("/tmp/plex_naming_debug.log", "a") as f:
            f.write(f"Info file estratte: {info}\n")
        
        # Logging per debug
        with open("/tmp/plex_naming_debug.log", "a") as f:
            f.write(f"\nEXTRACT_FILE_INFO\n")
            f.write(f"File path: {file_path}\n")
            f.write(f"File name: {file_name}\n")
            f.write(f"Parent dir: {parent_dir}\n")
            f.write(f"Media type: {media_type}\n")
        
        # Extract language suffix if present (like -ita, -eng)
        language_match = re.search(r'[-_]([a-z]{2,3})(?:_|$|[-\s])', name_without_ext.lower())
        if language_match:
            info["language"] = language_match.group(1)
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Lingua rilevata: {info['language']}\n")
        
        # For series/anime series, try to extract season and episode first
        # since we'll need them per la pulizia del titolo
        if media_type["is_series"]:
            # Check for season folder like S1, Season 1, etc.
            season_folder_match = re.search(r'[Ss](?:eason|tagione)?[-\s_]*(\d+)', parent_dir)
            if season_folder_match:
                info["season"] = int(season_folder_match.group(1))
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Stagione rilevata dalla cartella: {info['season']}\n")
            else:
                # Try to extract season from filename for anime series
                season_match = re.search(r'[Ss](?:eason|tagione)?[-\s_]*(\d+)', name_without_ext)
                if season_match:
                    info["season"] = int(season_match.group(1))
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Stagione rilevata dal nome: {info['season']}\n")
                elif media_type["is_anime"]:
                    # Default to season 1 for anime if not specified
                    info["season"] = 1
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Stagione default per anime: 1\n")
                
            # Extract episode number - more comprehensive patterns
            ep_patterns = [
                r'[Ee][Pp]?[-\s_]*(\d+)',           # Standard EP01, E01, etc
                r'_EP_(\d+)',                        # _EP_01 format
                r'[-\s_](\d{1,3})(?:[-\s_]|$)',      # Space/dash followed by numbers
                r'Ep(?:isode)?\s*(\d+)',             # Episode 1, Ep 1 format
                r'Episodio\s*(\d+)',                # Italian: Episodio 1
                r'#(\d+)'                            # #01 format
            ]
            
            for pattern in ep_patterns:
                ep_match = re.search(pattern, name_without_ext)
                if ep_match:
                    info["episode"] = int(ep_match.group(1))
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Episodio rilevato con pattern '{pattern}': {info['episode']}\n")
                    break
        
        # Per film e anime film, estrai titolo dal nome del file
        if not media_type["is_series"]:
            # Estrai titolo rimuovendo eventuali tag tra parentesi e l'anno
            title = name_without_ext
            # Rimuovi l'anno tra parentesi
            title = re.sub(r'\s*\([12][0-9]{3}\)', '', title)
            # Rimuovi altri tag tra parentesi
            title = re.sub(r'\s*\([^)]+\)', '', title)
            # Pulisci il titolo
            title = title.strip()
            info["title"] = title
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Titolo film estratto dal nome file: {title}\n")
    
        # Per anime e serie, tenta di estrarre il titolo dal nome file se la cartella non è informativa
        elif media_type["is_series"] and (parent_dir.lower() in ["download", "downloads", "temp", "tmp"] or media_type["is_anime"]):
            # Prova a derivare il titolo dal nome file per anime o serie in cartelle temporanee
            extracted_title = name_without_ext
            
            # Rimuovi numero episodio dal titolo
            if info["episode"] is not None:
                for pattern in [
                    r'[Ee][Pp]?[-\s_]*\d+',
                    r'_EP_\d+',
                    r'Ep(?:isode)?\s*\d+',
                    r'Episodio\s*\d+',
                    r'#\d+'
                ]:
                    extracted_title = re.sub(pattern, '', extracted_title, flags=re.IGNORECASE)
            
            # Rimuovi stagione dal titolo se presente
            if info["season"] is not None:
                extracted_title = re.sub(r'[Ss](?:eason|tagione)?[-\s_]*\d+', '', extracted_title)
            
            # Rimuovi suffisso lingua se presente
            if info["language"]:
                extracted_title = re.sub(r'[-_]' + info["language"] + r'(?:_|$|[-\s])', '', extracted_title, flags=re.IGNORECASE)
                
            # Pulisci il titolo estratto
            extracted_title = extracted_title.replace('_', ' ').replace('-', ' ')
            extracted_title = re.sub(r'[^\w\s]', ' ', extracted_title)
            extracted_title = re.sub(r'\s+', ' ', extracted_title).strip()
            info["title"] = extracted_title
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Titolo serie estratto dal nome file: {extracted_title}\n")
    
        # Se il titolo non è stato determinato, usa la cartella principale invece delle sottocartelle
        if not info["title"] and media_type["is_series"]:
            # Per le serie TV, cerca di usare la cartella principale invece di sottocartelle come "S1", "S2"
            full_path_parts = file_path.split(os.sep)
            
            # Trova l'indice della cartella "Serie" o "Anime"
            serie_index = -1
            for i, part in enumerate(full_path_parts):
                if part.lower() in ['serie', 'anime']:
                    serie_index = i
                    break
            
            # Se troviamo la cartella Serie/Anime, prendi la cartella successiva come titolo serie
            if serie_index != -1 and serie_index + 1 < len(full_path_parts):
                potential_title = full_path_parts[serie_index + 1]
                # Evita cartelle come "S1", "S2", "Season 1", etc.
                if not re.match(r'^[Ss]\d+$|^Season\s*\d+$', potential_title):
                    info["title"] = potential_title
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Titolo serie estratto dal percorso: {info['title']}\n")
                else:
                    # Se la cartella successiva è una stagione, prova quella prima
                    if serie_index + 2 < len(full_path_parts):
                        # Questo non dovrebbe succedere normalmente, ma è un fallback
                        info["title"] = full_path_parts[serie_index + 1]
                    else:
                        info["title"] = parent_dir
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Titolo fallback usando parent dir: {info['title']}\n")
            else:
                # Fallback al parent_dir se non troviamo la struttura attesa
                info["title"] = parent_dir
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Titolo fallback usando nome cartella: {info['title']}\n")
        
        # Fallback per film se il titolo non è stato estratto
        elif not info["title"] and not media_type["is_series"]:
            info["title"] = parent_dir
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Titolo film fallback usando nome cartella: {info['title']}\n")
                     
        # For movies, try to extract year
        if not media_type["is_series"]:
            # Look for year pattern in parent directory name
            year_match = re.search(r'\((\d{4})\)', parent_dir)
            if not year_match:
                # Try to find year in the filename
                year_match = re.search(r'(?:\s|_|\()(\d{4})(?:\s|_|\))', name_without_ext)
                
            if year_match:
                info["year"] = year_match.group(1)
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Anno rilevato: {info['year']}\n")
            else:
                # Se non c'è un anno nel nome file, lascia None e lascia che TMDB lo recuperi
                info["year"] = None
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Anno non trovato nel nome file, verrà recuperato da TMDB se possibile\n")
        
        with open("/tmp/plex_naming_debug.log", "a") as f:
            f.write(f"Info estratte: {info}\n")
                
        return info
    
    def _generate_plex_path(self, original_path: str, info: Dict[str, Any], media_type: Dict[str, Any]) -> str:
        """
        Generate a file path that follows Plex naming conventions.
        
        Args:
            original_path: Original file path
            info: File information dict with title, year, season, episode, language
            media_type: Media type dict from _determine_media_type
            
        Returns:
            New file path following Plex naming conventions
        """
        try:
            # Log per debug
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"\nGENERATE_PLEX_PATH\n")
                f.write(f"Original path: {original_path}\n")
                f.write(f"Info: {info}\n")
                f.write(f"Media type: {media_type}\n")
            
            # Get file extension
            _, ext = os.path.splitext(original_path)
            
            # Base destination folder
            if media_type["type"] == "movie":
                dest_folder = os.path.join(self.root_path, self.film_folder)
            elif media_type["type"] == "series":
                dest_folder = os.path.join(self.root_path, self.serie_folder)
            elif media_type["type"] == "anime_movie":
                # Per gli anime film, controlliamo prima la configurazione specifica
                if self.anime_movie_folder and os.path.exists(os.path.join(self.root_path, self.anime_movie_folder)):
                    dest_folder = os.path.join(self.root_path, self.anime_movie_folder)
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Usando cartella anime_movie configurata: {dest_folder}\n")
                else:
                    # Altrimenti, usa Anime/Film
                    dest_folder = os.path.join(self.root_path, self.anime_folder, "Film")
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Usando cartella Anime/Film: {dest_folder}\n")
            elif media_type["type"] == "anime_series":
                # Per gli anime serie, evitiamo di aggiungere Serie/Serie
                if "serie" in self.anime_folder.lower() or "anime/serie" in os.path.join(self.root_path, self.anime_folder).lower():
                    # La cartella anime è già specifica per le serie anime
                    dest_folder = os.path.join(self.root_path, self.anime_folder)
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Evito duplicazione Serie/Serie: {dest_folder}\n")
                else:
                    # Aggiunge il suffisso Serie solo se necessario
                    dest_folder = os.path.join(self.root_path, self.anime_folder, "Serie")
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Aggiungo sottocartella Serie: {dest_folder}\n")
            else:
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Tipo media non riconosciuto: {media_type}\n")
                return original_path  # Unknown media type
                
            # Extract title from info
            title = info.get("title", "")
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Titolo originale: {title}\n")
            
            # Remove language suffix if present
            if info.get("language"):
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Rimuovendo suffisso lingua: {info['language']}\n")
                title = re.sub(r'[-_]' + info["language"] + r'(?:_|$|[-\s])', '', title, flags=re.IGNORECASE)
                title = re.sub(r'\([^)]*' + info["language"] + r'[^)]*\)', '', title, flags=re.IGNORECASE)
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Titolo dopo rimozione lingua: {title}\n")
            
            # Clean up title
            title = title.replace('_', ' ').replace('-', ' ')
            title = re.sub(r'[^\w\s()]', ' ', title)
            title = re.sub(r'\s+', ' ', title).strip()
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Titolo ripulito: {title}\n")
            
            if media_type["is_series"]:
                # Create series folder
                series_folder = os.path.join(dest_folder, title)
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Cartella serie: {series_folder}\n")
                
                # Add year to folder if available
                if info.get("year"):
                    series_folder = f"{series_folder} ({info['year']})"
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Cartella serie con anno: {series_folder}\n")
                
                # Add season folder
                season_num = info.get("season", 1)  # Default to season 1
                season_folder = os.path.join(series_folder, f"Season {season_num}")
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Numero stagione: {season_num}\n")
                    f.write(f"Cartella stagione: {season_folder}\n")
                
                # Generate episode filename
                if info.get("episode"):
                    ep_num = info["episode"]
                    ep_str = f"s{season_num:02d}e{ep_num:02d}"
                    
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Numero episodio: {ep_num}\n")
                        f.write(f"String episodio: {ep_str}\n")
                        if info.get("episode_title"):
                            f.write(f"Titolo episodio TMDB: {info['episode_title']}\n")
                    
                    # Costruisci il nome file con titolo episodio se disponibile
                    if info.get("episode_title"):
                        # Formato: "Serie - s01e01 - Titolo Episodio {tmdb-id}.ext"
                        if self.use_tmdb_ids and info.get("tmdb_id"):
                            filename = f"{title} - {ep_str} - {info['episode_title']} {{tmdb-{info['tmdb_id']}}}{ext}"
                        else:
                            filename = f"{title} - {ep_str} - {info['episode_title']}{ext}"
                    else:
                        # Formato standard senza titolo episodio
                        if self.use_tmdb_ids and info.get("tmdb_id"):
                            filename = f"{title} - {ep_str} {{tmdb-{info['tmdb_id']}}}{ext}"
                        else:
                            filename = f"{title} - {ep_str}{ext}"
                        
                    final_path = os.path.join(season_folder, filename)
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Nome file finale: {filename}\n")
                        f.write(f"Percorso finale: {final_path}\n")
                    return final_path
                else:
                    # No episode number, just use the title
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"ATTENZIONE: Nessun numero di episodio trovato, percorso non modificato!\n")
                    return original_path
            else:
                # Movie file - prima prepara la struttura della cartella film
                if info.get("year"):
                    movie_name = f"{title} ({info['year']})"
                else:
                    movie_name = title
                
                # Crea una sottocartella con lo stesso nome del film
                movie_folder = os.path.join(dest_folder, movie_name)
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Cartella film: {movie_folder}\n")
                
                # Crea il nome del file con lo stesso nome della cartella
                movie_filename = movie_name
                    
                # Add TMDB ID for better Plex matching
                if self.use_tmdb_ids and info.get("tmdb_id"):
                    movie_filename += f" {{tmdb-{info['tmdb_id']}}}"
                    
                movie_filename += ext
                final_path = os.path.join(movie_folder, movie_filename)
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Nome file film: {movie_filename}\n")
                    f.write(f"Percorso finale: {final_path}\n")
                return final_path
                
        except Exception as e:
            self.logger.error(f"Error generating Plex path: {str(e)}")
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"ERRORE generando percorso Plex: {str(e)}\n")
                import traceback
                f.write(traceback.format_exc())
            return original_path


    def process_downloaded_file(self, file_path: str) -> str:
        """
        Process a downloaded file and rename it according to Plex conventions.
        
        Args:
            file_path: Full path to the downloaded file
            
        Returns:
            New file path after renaming
        """
        try:
            # Logging per debug
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Processando file: {file_path}\n")
                f.write(f"Root path configurato: {self.root_path}\n")
                f.write(f"Cartelle configurate: Film={self.film_folder}, Serie={self.serie_folder}, Anime={self.anime_folder}\n")
                f.write(f"TMDB IDs abilitati: {self.use_tmdb_ids}\n")
            
            # Determine media type from path if available
            media_type = self._determine_media_type(file_path)
            if media_type is None:
                self.logger.error(f"Could not determine media type for {file_path}")
                return file_path
                
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Tipo media determinato: {media_type['type']}\n")
                # Log se abbiamo un TMDB ID dal processo di identificazione
                if 'tmdb_id' in media_type:
                    f.write(f"TMDB ID trovato nell'identificazione media: {media_type['tmdb_id']}\n")
            
            # Get file information
            file_info = self._extract_file_info(file_path, media_type)
            
            # Trasferisci TMDB ID se disponibile dal processo di identificazione del tipo media
            if 'tmdb_id' in media_type and self.use_tmdb_ids:
                file_info['tmdb_id'] = media_type['tmdb_id']
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"TMDB ID trasferito da media_type: {media_type['tmdb_id']}\n")
            
            # Try to enrich with TMDB metadata if enabled - USA IL NUOVO SISTEMA COMPLETO
            if self.use_tmdb_ids:
                # Prima prova il nuovo sistema di ricerca completa TMDB
                tmdb_success = self.search_and_enrich_with_tmdb(file_info, media_type)
                if not tmdb_success:
                    # Fallback al sistema vecchio se il nuovo fallisce
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Fallback al sistema TMDB precedente\n")
                    self._enrich_with_tmdb_metadata(file_info, media_type)
            
            # Generate new file path
            new_path = self._generate_plex_path(file_path, file_info, media_type)
            
            # If path is different, move the file
            if new_path != file_path:
                # Create parent directories if they don't exist
                parent_dir = os.path.dirname(new_path)
                os.makedirs(parent_dir, exist_ok=True)
                
                # Move file
                try:
                    shutil.move(file_path, new_path)
                    self.logger.info(f"Moved {file_path} to {new_path}")
                    
                    # Remove empty directories
                    old_dir = os.path.dirname(file_path)
                    self._remove_empty_folders(old_dir)
                    
                    return new_path
                except Exception as e:
                    self.logger.error(f"Error moving file: {str(e)}")
                    return file_path
            
            return new_path
            
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {str(e)}")
            return file_path
            
    def get_tv_details(self, tmdb_id: int) -> Dict[str, Any]:
        """
        Get TV show details from TMDB.
        
        Args:
            tmdb_id: TMDB ID of the TV show
            
        Returns:
            Dictionary with TV show details
        """
        try:
            tv_details = self.tmdb_api._make_request(f"tv/{tmdb_id}")
            return tv_details
        except Exception as e:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Errore recupero dettagli TV {tmdb_id}: {str(e)}\n")
            return None
    
    def get_episode_details(self, tmdb_id: int, season: int, episode: int) -> Dict[str, Any]:
        """
        Get episode details from TMDB.
        
        Args:
            tmdb_id: TMDB ID of the TV show
            season: Season number
            episode: Episode number
            
        Returns:
            Dictionary with episode details
        """
        try:
            episode_details = self.tmdb_api._make_request(f"tv/{tmdb_id}/season/{season}/episode/{episode}")
            return episode_details
        except Exception as e:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Errore recupero dettagli episodio {tmdb_id} S{season}E{episode}: {str(e)}\n")
            return None
    
    def search_and_enrich_with_tmdb(self, file_info: Dict[str, Any], media_type: Dict[str, Any]) -> bool:
        """
        Search for media on TMDB and enrich file_info with complete TMDB data.
        
        Args:
            file_info: Dictionary to enrich with TMDB data
            media_type: Media type information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"\n=== RICERCA TMDB COMPLETA ===\n")
                f.write(f"Titolo originale: {file_info.get('title')}\n")
                f.write(f"Tipo media: {media_type['type']}\n")
            
            # Estrai il titolo pulito per la ricerca
            search_title = file_info.get('title', '')
            if not search_title:
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Nessun titolo disponibile per la ricerca\n")
                return False
            
            # Pulisci il titolo per la ricerca
            search_title = re.sub(r'[^\w\s]', ' ', search_title)
            search_title = re.sub(r'\s+', ' ', search_title).strip()
            
            if media_type["is_series"]:
                # Ricerca serie TV
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Ricerca serie TV: {search_title}\n")
                
                search_results = self.tmdb_api._make_request("search/tv", {"query": search_title})
                results = search_results.get("results", [])
                
                if not results:
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Nessuna serie TV trovata per: {search_title}\n")
                    return False
                
                # Prendi il primo risultato (più rilevante)
                tv_show = results[0]
                tmdb_id = tv_show["id"]
                
                # Ottieni dettagli completi della serie
                tv_details = self.get_tv_details(tmdb_id)
                if not tv_details:
                    return False
                
                # Arricchisci file_info con dati TMDB
                file_info["tmdb_id"] = tmdb_id
                file_info["title"] = tv_details["name"]
                file_info["year"] = tv_details["first_air_date"][:4] if tv_details.get("first_air_date") else None
                file_info["tmdb_original_name"] = tv_details.get("original_name")
                file_info["tmdb_overview"] = tv_details.get("overview")
                
                # Se abbiamo informazioni su stagione ed episodio, ottieni dettagli episodio
                if file_info.get("season") and file_info.get("episode"):
                    episode_details = self.get_episode_details(tmdb_id, file_info["season"], file_info["episode"])
                    if episode_details:
                        file_info["episode_title"] = episode_details.get("name")
                        file_info["episode_overview"] = episode_details.get("overview")
                        file_info["episode_air_date"] = episode_details.get("air_date")
                
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Serie TV trovata: {file_info['title']} ({file_info.get('year')}) [TMDB: {tmdb_id}]\n")
                    if file_info.get("episode_title"):
                        f.write(f"Episodio: S{file_info.get('season', '?')}E{file_info.get('episode', '?')} - {file_info['episode_title']}\n")
                
            else:
                # Ricerca film
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Ricerca film: {search_title}\n")
                
                search_results = self.tmdb_api._make_request("search/movie", {"query": search_title})
                results = search_results.get("results", [])
                
                if not results:
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Nessun film trovato per: {search_title}\n")
                    return False
                
                # Prendi il primo risultato (più rilevante)
                movie = results[0]
                tmdb_id = movie["id"]
                
                # Ottieni dettagli completi del film
                movie_details = self.tmdb_api.get_movie_details(tmdb_id)
                if not movie_details:
                    return False
                
                # Arricchisci file_info con dati TMDB
                file_info["tmdb_id"] = tmdb_id
                file_info["title"] = movie_details.title
                file_info["year"] = movie_details.release_date[:4] if movie_details.release_date else None
                file_info["tmdb_original_title"] = movie_details.original_title
                file_info["tmdb_overview"] = movie_details.overview
                
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Film trovato: {file_info['title']} ({file_info.get('year')}) [TMDB: {tmdb_id}]\n")
            
            return True
            
        except Exception as e:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Errore nella ricerca TMDB: {str(e)}\n")
            return False
    
    def _enrich_with_tmdb_metadata(self, file_info: Dict[str, Any], media_type: Dict[str, Any]) -> None:
        """
        Try to enrich the file info with TMDB metadata, including IDs.
        
        Args:
            file_info: Dictionary with file information to be enriched
            media_type: Dictionary with media type information
        """
        try:
            # Logging per debug
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Arricchimento TMDB per: {file_info['title']}\n")
                if 'tmdb_id' in media_type:
                    f.write(f"TMDB ID già disponibile da media_type: {media_type['tmdb_id']}\n")
            
            title = file_info["title"]
            
            # Usa l'ID TMDB se già presente in media_type (dalla fase di identificazione)
            # Questo ha priorità assoluta per garantire coerenza
            if 'tmdb_id' in media_type and self.use_tmdb_ids:
                file_info["tmdb_id"] = media_type["tmdb_id"]
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"TMDB ID assegnato direttamente da media_type: {file_info['tmdb_id']}\n")
                    
                # Se l'ID è già presente, tentiamo di ottenere dettagli aggiuntivi
                if not media_type["is_series"]:  # Per i film
                    try:
                        movie_details = self.tmdb_api.get_movie_details(media_type["tmdb_id"])
                        if movie_details:
                            file_info["original_title"] = movie_details.title
                            file_info["year"] = movie_details.release_date[:4] if movie_details.release_date else file_info.get("year")
                    except Exception as e:
                        with open("/tmp/plex_naming_debug.log", "a") as f:
                            f.write(f"Errore recupero dettagli con ID esistente: {str(e)}\n")
                return
            
            # Fallback alla ricerca TMDB solo se non abbiamo già un ID
            # For movies
            if not media_type["is_series"]:
                # Use the title and year if available to search for the movie
                tmdb_id = None
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write(f"Inizio ricerca TMDB per film\n")
                    
                # Strategia 1: Ricerca con titolo originale e anno
                try:
                    search_query = title
                    if file_info.get("year"):
                        search_query += f" {file_info['year']}"
                    
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Strategia 1: Ricerca per titolo e anno: {search_query}\n")
                        
                    data = self.tmdb_api._make_request("search/movie", {"query": search_query}).get("results", [])
                    if data:
                        tmdb_id = data[0]["id"]
                        file_info["tmdb_id"] = tmdb_id
                        with open("/tmp/plex_naming_debug.log", "a") as f:
                            f.write(f"Strategia 1 riuscita: ID TMDB trovato {tmdb_id}\n")
                        self.logger.info(f"Found TMDB ID for '{title}': {tmdb_id}")
                        return
                except Exception as e:
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Strategia 1 fallita: {str(e)}\n")
                
                # Strategia 2: Ricerca con titolo pulito
                try:
                    # Pulizia accurata del titolo
                    clean_title = re.sub(r'[^\w\s]', ' ', title)
                    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                    search_query = clean_title
                    if file_info.get("year"):
                        search_query += f" {file_info['year']}"
                    
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Strategia 2: Ricerca con titolo pulito: {search_query}\n")
                    
                    data = self.tmdb_api._make_request("search/movie", {"query": search_query}).get("results", [])
                    if data:
                        tmdb_id = data[0]["id"]
                        file_info["tmdb_id"] = tmdb_id
                        with open("/tmp/plex_naming_debug.log", "a") as f:
                            f.write(f"Strategia 2 riuscita: ID TMDB trovato {tmdb_id}\n")
                        self.logger.info(f"Found TMDB ID with clean title for '{title}': {tmdb_id}")
                        return
                except Exception as e:
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Strategia 2 fallita: {str(e)}\n")
                
                # Strategia 3: Ricerca solo con titolo senza anno
                try:
                    # Ricerca solo con il titolo pulito, senza anno
                    clean_title = re.sub(r'[^\w\s]', ' ', title)
                    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                    
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Strategia 3: Ricerca solo con titolo senza anno: {clean_title}\n")
                        
                    data = self.tmdb_api._make_request("search/movie", {"query": clean_title}).get("results", [])
                    if data:
                        tmdb_id = data[0]["id"]
                        file_info["tmdb_id"] = tmdb_id
                        with open("/tmp/plex_naming_debug.log", "a") as f:
                            f.write(f"Strategia 3 riuscita: ID TMDB trovato {tmdb_id}\n")
                        self.logger.info(f"Found TMDB ID with title only for '{title}': {tmdb_id}")
                        return
                except Exception as e:
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Strategia 3 fallita: {str(e)}\n")
                
                # Strategia 4: Ricerca con parole chiave
                try:
                    # Estrai le parole chiave più significative (prime 2-3 parole)
                    words = title.split()
                    keywords = " ".join(words[:min(3, len(words))])
                    
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Strategia 4: Ricerca con parole chiave: {keywords}\n")
                        
                    data = self.tmdb_api._make_request("search/movie", {"query": keywords}).get("results", [])
                    if data:
                        tmdb_id = data[0]["id"]
                        file_info["tmdb_id"] = tmdb_id
                        with open("/tmp/plex_naming_debug.log", "a") as f:
                            f.write(f"Strategia 4 riuscita: ID TMDB trovato {tmdb_id}\n")
                        self.logger.info(f"Found TMDB ID with keywords for '{title}': {tmdb_id}")
                        return
                except Exception as e:
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Strategia 4 fallita: {str(e)}\n")
                
                with open("/tmp/plex_naming_debug.log", "a") as f:
                    f.write("ATTENZIONE: Nessun TMDB ID trovato dopo tutti i tentativi!\n")
                    
            # Per serie TV
            else:
                # Implementazione per arricchimento serie TV
                try:
                    # Pulizia pre-ricerca per migliorare il match
                    search_title = title
                    # Rimuovi suffissi comuni di anime
                    search_title = re.sub(r'(?i)[-_\s](ita|eng|sub|dub)(?:bed)?(?:_|$|[-\s])', '', search_title)
                    # Normalizza anime title format
                    search_title = search_title.replace('-', ' ').replace('_', ' ')
                    search_title = re.sub(r'\s+', ' ', search_title).strip()
                    
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Arricchimento serie TV: {search_title}\n")
                    
                    # Prova prima con suffisso "anime" per serie anime
                    if media_type["is_anime"]:
                        # Prova la ricerca con "anime" aggiunto se è un anime
                        with open("/tmp/plex_naming_debug.log", "a") as f:
                            f.write(f"Ricerca serie anime: {search_title} anime\n")
                        data = self.tmdb_api._make_request("search/tv", {"query": search_title + " anime"}).get("results", [])
                    else:
                        # Ricerca standard per serie TV
                        with open("/tmp/plex_naming_debug.log", "a") as f:
                            f.write(f"Ricerca serie standard: {search_title}\n")
                        data = self.tmdb_api._make_request("search/tv", {"query": search_title}).get("results", [])
                    
                    # Controlla i risultati
                    if data:
                        # Take the top result
                        tmdb_id = data[0]['id']
                        
                        # Get TV show details
                        tv_details = self.tmdb_api.get_tv_details(tmdb_id)
                        if tv_details:
                            file_info["tmdb_id"] = tmdb_id
                            file_info["original_title"] = tv_details.name
                            
                            if hasattr(tv_details, "first_air_date") and tv_details.first_air_date:
                                file_info["year"] = tv_details.first_air_date[:4]
                                
                            with open("/tmp/plex_naming_debug.log", "a") as f:
                                f.write(f"Serie TV arricchita con ID TMDB: {tmdb_id}\n")
                                
                            self.logger.info(f"Enhanced TV show '{title}' with TMDB ID: {tmdb_id}")
                            return
                        else:
                            with open("/tmp/plex_naming_debug.log", "a") as f:
                                f.write(f"Trovato ID TMDB {tmdb_id} ma impossibile ottenere dettagli\n")
                    else:
                        with open("/tmp/plex_naming_debug.log", "a") as f:
                            f.write(f"Nessun risultato trovato per la serie TV\n")
                except Exception as e:
                    self.logger.warning(f"Failed to get TMDB metadata for TV show '{title}': {str(e)}")
                    with open("/tmp/plex_naming_debug.log", "a") as f:
                        f.write(f"Errore nell'arricchimento della serie TV: {str(e)}\n")
        except Exception as e:
            self.logger.error(f"Error in _enrich_with_tmdb_metadata: {str(e)}")            
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Errore generale in arricchimento TMDB: {str(e)}\n")
                
        # Verifica finale presenza ID TMDB
        if 'tmdb_id' in file_info:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write(f"Arricchimento completato con successo, ID TMDB presente: {file_info['tmdb_id']}\n")
        else:
            with open("/tmp/plex_naming_debug.log", "a") as f:
                f.write("ATTENZIONE: Nessun TMDB ID presente dopo arricchimento\n")


# Singleton instance for use throughout the application
plex_naming = PlexNaming()


def post_process_media_file(file_path: str) -> str:
    """
    Post-process a media file to ensure proper Plex naming.
    This function should be called after a download is complete.
    
    Args:
        file_path: Full path to the downloaded media file
        
    Returns:
        New file path after renaming according to Plex conventions
    """
    print("[DEBUG] post_process_media_file chiamato per:", file_path)
    with open("/tmp/plex_naming_debug.log", "a") as f:
        f.write(f"\n\n[{datetime.datetime.now()}] Post-processing: {file_path}\n")
    result = plex_naming.process_downloaded_file(file_path)
    print("[DEBUG] Risultato post-processing:", result)
    return result
